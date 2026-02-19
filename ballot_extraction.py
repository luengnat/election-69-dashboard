#!/usr/bin/env python3
"""
Ballot data extraction using AI vision.

Contains: pdf_to_images, encode_image, detect_form_type, prompt builders,
extract_ballot_data_with_ai, parse_ocr_text_to_ballot_data,
extract_with_claude_vision, process_extracted_data.
"""

import os
import json
import subprocess
import base64
from pathlib import Path
from typing import Optional

from ballot_types import (
    FormType, VoteEntry, BallotData,
    THAI_NUMERALS, convert_thai_numerals, validate_vote_entry,
)

try:
    from crop_utils import detect_form_type_from_path, crop_page_image, FORM_TEMPLATES, _DEFAULT_TEMPLATE
    CROP_UTILS_AVAILABLE = True
except ImportError:
    CROP_UTILS_AVAILABLE = False

try:
    from ect_api import ect_data
    ECT_AVAILABLE = True
except ImportError:
    ECT_AVAILABLE = False

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False


def pdf_to_images_native(pdf_path: str, output_dir: str) -> list[str]:
    """
    Extract images from PDF at native resolution using PyMuPDF.

    This is more efficient than pdftoppm and maintains original quality.
    Best for PDFs that contain embedded scanned images.

    Args:
        pdf_path: Path to the PDF file
        output_dir: Directory to save output images

    Returns:
        List of paths to generated PNG images
    """
    if not PYMUPDF_AVAILABLE:
        raise ImportError("PyMuPDF not installed. Run: pip install PyMuPDF")

    if not os.path.isfile(pdf_path):
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")
    if not os.path.isdir(output_dir):
        raise NotADirectoryError(f"Output directory not found: {output_dir}")

    from PIL import Image
    import io

    doc = fitz.open(pdf_path)
    output_paths = []

    for page_num, page in enumerate(doc):
        # Get embedded images
        images = page.get_images()

        if images:
            # Extract the first (usually main) image at native resolution
            xref = images[0][0]
            base_image = doc.extract_image(xref)
            img_data = base_image["image"]

            # Save directly - no resampling
            img = Image.open(io.BytesIO(img_data))
            output_path = os.path.join(output_dir, f"page-{page_num + 1}.png")
            img.save(output_path, "PNG")
            output_paths.append(output_path)
        else:
            # No embedded image - render page at 150 DPI (reasonable default)
            mat = fitz.Matrix(150 / 72, 150 / 72)
            pix = page.get_pixmap(matrix=mat)
            output_path = os.path.join(output_dir, f"page-{page_num + 1}.png")
            pix.save(output_path)
            output_paths.append(output_path)

    doc.close()
    return output_paths


def pdf_to_images(pdf_path: str, output_dir: str, dpi: int = 300) -> list[str]:
    """
    Convert PDF to PNG images using pdftoppm.

    Args:
        pdf_path: Path to the PDF file
        output_dir: Directory to save output images
        dpi: Resolution for conversion (default 300)

    Returns:
        List of paths to generated PNG images

    Raises:
        FileNotFoundError: If PDF file or output directory doesn't exist
        ValueError: If dpi is out of range
        RuntimeError: If pdftoppm is not available
    """
    import shutil

    # Input validation
    if not os.path.isfile(pdf_path):
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")
    if not os.path.isdir(output_dir):
        raise NotADirectoryError(f"Output directory not found: {output_dir}")
    if not 50 <= dpi <= 600:
        raise ValueError(f"DPI must be between 50 and 600, got {dpi}")

    # Check pdftoppm is available
    if not shutil.which("pdftoppm"):
        raise RuntimeError("pdftoppm not found. Install poppler-utils.")

    output_prefix = "page"
    cmd = [
        "pdftoppm", "-png", "-r", str(dpi),
        pdf_path,
        os.path.join(output_dir, output_prefix)
    ]
    subprocess.run(cmd, check=True, capture_output=True)

    # Return list of generated images
    images = sorted(Path(output_dir).glob("page-*.png"))
    return [str(img) for img in images]


def encode_image(image_path: str) -> str:
    """Encode image to base64."""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


# Model used for OpenRouter vision calls. Override via OPENROUTER_MODEL env var.
# Good alternatives (free): google/gemma-3-27b-it:free, google/gemini-2.0-flash-lite:free
# Good alternatives (paid): google/gemini-flash-1.5, anthropic/claude-haiku
_OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "google/gemma-3-12b-it:free")


def _preprocess_image(image_path: str) -> bytes:
    """
    Preprocess a ballot image to improve OCR accuracy.

    Uses adaptive preprocessing if available, analyzing the image to apply
    optimal filters (contrast, sharpening, binarization) based on its
    characteristics (resolution, noise, contrast).

    Returns PNG bytes of the enhanced image, or the original file bytes
    if Pillow is unavailable or preprocessing fails.
    """
    try:
        from PIL import Image
        import io
        import adaptive_ocr
        
        with Image.open(image_path) as img:
            if img.mode != "RGB":
                img = img.convert("RGB")
                
            # Apply adaptive preprocessing
            # This analyzes the image and applies the best filter chain
            processed_img = adaptive_ocr.adaptive_preprocess_image(img)
            
            buf = io.BytesIO()
            processed_img.save(buf, format="PNG", optimize=True)
            return buf.getvalue()
            
    except ImportError:
        # Fallback to static processing if adaptive_ocr is missing
        try:
            from PIL import Image, ImageEnhance, ImageFilter
            import io

            with Image.open(image_path) as img:
                if img.mode != "RGB":
                    img = img.convert("RGB")
                # Boost contrast so handwritten ink stands out from paper
                img = ImageEnhance.Contrast(img).enhance(1.8)
                # Sharpen edges to make digit strokes crisper
                img = img.filter(ImageFilter.SHARPEN)
                buf = io.BytesIO()
                img.save(buf, format="PNG", optimize=True)
                return buf.getvalue()
        except Exception:
            pass
            
    except Exception as e:
        print(f"  Preprocessing error: {e}")
        pass

    with open(image_path, "rb") as f:
        return f.read()


def detect_form_type(image_path: str) -> tuple[Optional[FormType], str]:
    """
    Detect the form type from the image using AI.
    Returns (FormType, raw_response) tuple.

    Approach: Focus ONLY on the form number (5/16, 5/17, 5/18) and type marker (บช).
    Do not try to read vote counts at this stage.
    """
    import anthropic

    client = anthropic.Anthropic()

    with open(image_path, "rb") as f:
        image_data = base64.b64encode(f.read()).decode("utf-8")

    prompt = """Look at this THAI election ballot counting form.

FOCUS ONLY ON THE HEADER/TITLE AREA to identify:
1. The form number: Look for "ส.ส. 5/16" or "ส.ส. 5/17" or "ส.ส. 5/18"
2. Whether it has "(บช)" suffix indicating party-list form

FORM NUMBER IDENTIFICATION:
- Look at the top-right corner or header area
- Find the text that looks like "ส.ส. 5/16" or "ส.ส. 5/17" or "ส.ส. 5/18"

TYPE IDENTIFICATION:
- If you see "(บช)" or "บัญชีรายชื่อ" in the title = PARTY-LIST
- If you see "แบ่งเขตเลือกตั้ง" without "(บช)" = CONSTITUENCY

DO NOT try to read vote counts or other data. Just identify the form type.

Return ONLY valid JSON with NO markdown formatting:
{
    "form_code": "5/16" or "5/17" or "5/18",
    "is_party_list": true or false
}"""

    try:
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=256,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": image_data}},
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        )

        # Guard: Check for empty response
        if not message.content:
            print("Empty response from Claude API")
            return FormType.S5_17, "Empty response"

        response_text = message.content[0].text.strip()
        data = json.loads(_strip_json_fences(response_text))
        form_code = data.get("form_code", "5/17")
        is_party_list = data.get("is_party_list", False)

        # Map to FormType enum
        form_type_map = {
            ("5/16", False): FormType.S5_16,
            ("5/16", True): FormType.S5_16_BCH,
            ("5/17", False): FormType.S5_17,
            ("5/17", True): FormType.S5_17_BCH,
            ("5/18", False): FormType.S5_18,
            ("5/18", True): FormType.S5_18_BCH,
        }

        form_type = form_type_map.get((form_code, is_party_list), FormType.S5_17)
        return form_type, response_text

    except json.JSONDecodeError as e:
        print(f"JSON parse error detecting form type: {e}")
        return FormType.S5_17, f"JSON error: {e}"
    except Exception as e:
        print(f"Error detecting form type: {e}")
        return FormType.S5_17, str(e)


def get_constituency_prompt() -> str:
    """Prompt for constituency (แบ่งเขตเลือกตั้ง) forms."""
    return """IMPORTANT: This document is in THAI language. All text on this form is in Thai.

You are analyzing a THAI ELECTION BALLOT COUNTING FORM. This is an official document from Thailand's Election Commission (EC/กกต.).

═══════════════════════════════════════════════════════════════════
PART 1: FORM IDENTIFICATION (Look at TOP-RIGHT CORNER)
═══════════════════════════════════════════════════════════════════

Find the SQUARE BOX in the top-right area of the form. Inside this box is the form code.

The form code will be ONE of these:
- "ส.ส. 5/16" or "สส. ๕/๑๖" (Early voting - ลงคะแนนก่อนวันเลือกตั้ง)
- "ส.ส. 5/17" or "สส. ๕/๑๗" (Out-of-district - นอกเขตเลือกตั้ง)
- "ส.ส. 5/18" or "สส. ๕/๑๘" (By polling unit - รายหน่วย)

NOTE: Thai numerals: ๑=1, ๒=2, ๓=3, ๔=4, ๕=5, ๖=6, ๗=7, ๘=8, ๙=9, ๐=0

If the form title contains "(บช)" or "บัญชีรายชื่อ", it's a PARTY-LIST form.
If the form title says "แบ่งเขตเลือกตั้ง" without "(บช)", it's a CONSTITUENCY form.

═══════════════════════════════════════════════════════════════════
PART 2: LOCATION INFORMATION (Look at HEADER SECTION)
═══════════════════════════════════════════════════════════════════

1. PROVINCE (จังหวัด): Look for "จังหวัด" followed by the province name. Read EXACT Thai characters.
2. CONSTITUENCY NUMBER: Look for "เขตเลือกตั้งที่" or "เขต" followed by a number.
3. DISTRICT (อำเภอ): Look for "อำเภอ" followed by the district name.
4. POLLING UNIT: Look for "หน่วยเลือกตั้งที่" or "หน่วย" followed by a number.

═══════════════════════════════════════════════════════════════════
PART 3: VOTE TABLE (Look at MAIN BODY of the form)
═══════════════════════════════════════════════════════════════════

Each row contains:
┌────────────┬──────────────────┬─────────────────────────────────┐
│ ลำดับ      │ คะแนน (Numeric)  │ จำนวนคะแนน (Thai text)          │
│ (Number)   │ (Handwritten)    │ (Written in Thai words)         │
├────────────┼──────────────────┼─────────────────────────────────┤
│     1      │     [hand]       │ [Thai words like "หนึ่งร้อยห้าสิบ"]│
│     2      │     [hand]       │ [Thai words]                     │
└────────────┴──────────────────┴─────────────────────────────────┘

READING STRATEGY FOR VOTE COUNTS:
The Thai TEXT column (right side) is your PRIMARY source.
Thai words are more reliably read than handwritten digits.
1. Read Thai text → convert to number  (see reference below)
2. Verify against the handwritten numeric column
3. If both agree → use that value. If they differ → trust the Thai text.

THAI NUMBER WORD REFERENCE:
  ศูนย์=0  หนึ่ง=1  สอง=2  สาม=3  สี่=4  ห้า=5  หก=6  เจ็ด=7  แปด=8  เก้า=9
  สิบ=10  ร้อย=100  พัน=1,000  หมื่น=10,000
  Examples: หนึ่งร้อยห้าสิบสาม=153 | สี่สิบห้า=45 | สิบสอง=12 | ศูนย์=0

═══════════════════════════════════════════════════════════════════
PART 4: TOTALS SECTION (Look at BOTTOM of the form)
═══════════════════════════════════════════════════════════════════

1. บัตรดี / คะแนนเสียงที่ถูกต้อง = VALID votes
2. บัตรเสีย = INVALID votes
3. บัตรไม่ประสงค์ลงคะแนน = BLANK votes
4. รวม = TOTAL

═══════════════════════════════════════════════════════════════════
OUTPUT FORMAT - Return ONLY valid JSON, NO markdown:
═══════════════════════════════════════════════════════════════════

{
    "form_type": "ส.ส. 5/16",
    "is_party_list": false,
    "province": "แพร่",
    "constituency_number": 1,
    "district": "เมืองแพร่",
    "polling_unit": 2,
    "vote_counts": {
        "1": {"numeric": 153, "thai_text": "หนึ่งร้อยห้าสิบสาม"},
        "2": {"numeric": 4, "thai_text": "สี่"},
        "3": {"numeric": 95, "thai_text": "เก้าสิบห้า"}
    },
    "valid_votes": 252,
    "invalid_votes": 3,
    "blank_votes": 0,
    "total_votes": 255
}"""


def get_party_list_prompt() -> str:
    """Prompt for party-list (บัญชีรายชื่อ - บช) forms."""
    return """IMPORTANT: This document is in THAI language. All text on this form is in Thai.

You are analyzing a THAI ELECTION BALLOT COUNTING FORM. This is a PARTY-LIST form (บัญชีรายชื่อ) from Thailand's Election Commission.

═══════════════════════════════════════════════════════════════════
PART 1: FORM IDENTIFICATION
═══════════════════════════════════════════════════════════════════

The form code will be ONE of these (with "(บช)" suffix):
- "ส.ส. 5/16 (บช)" - Early voting, party-list
- "ส.ส. 5/17 (บช)" - Out-of-district, party-list
- "ส.ส. 5/18 (บช)" - By polling unit, party-list

NOTE: Thai numerals: ๑=1, ๒=2, ๓=3, ๔=4, ๕=5, ๖=6, ๗=7, ๘=8, ๙=9, ๐=0

═══════════════════════════════════════════════════════════════════
PART 2: LOCATION INFORMATION
═══════════════════════════════════════════════════════════════════

1. PROVINCE (จังหวัด): Look for "จังหวัด" followed by the province name.
2. CONSTITUENCY NUMBER: Look for "เขตเลือกตั้งที่" followed by a number.
3. DISTRICT (อำเภอ): Look for "อำเภอ" followed by the district name.
4. POLLING UNIT: Look for "หน่วยเลือกตั้งที่" followed by a number.

═══════════════════════════════════════════════════════════════════
PART 3: PARTY VOTE TABLE (57 parties total, may span multiple pages)
═══════════════════════════════════════════════════════════════════

Each row contains:
┌────────────┬──────────────────┬─────────────────────────────────┐
│ ลำดับ      │ คะแนน (Numeric)  │ จำนวนคะแนน (Thai text)          │
│ (Party #)  │ (Handwritten)    │ (Written in Thai words)         │
├────────────┼──────────────────┼─────────────────────────────────┤
│     1      │     [hand]       │ [Thai words]                     │
│     2      │     [hand]       │ [Thai words]                     │
│    ...     │     [hand]       │ [Thai words]                     │
│    57      │     [hand]       │ [Thai words]                     │
└────────────┴──────────────────┴─────────────────────────────────┘

READING STRATEGY FOR VOTE COUNTS:
The Thai TEXT column (right side) is your PRIMARY source.
Thai words are more reliably read than handwritten digits.
1. Read Thai text → convert to number  (see reference below)
2. Verify against the handwritten numeric column
3. If both agree → use that value. If they differ → trust the Thai text.

THAI NUMBER WORD REFERENCE:
  ศูนย์=0  หนึ่ง=1  สอง=2  สาม=3  สี่=4  ห้า=5  หก=6  เจ็ด=7  แปด=8  เก้า=9
  สิบ=10  ร้อย=100  พัน=1,000  หมื่น=10,000
  Examples: หนึ่งร้อยห้าสิบสาม=153 | สี่สิบห้า=45 | สิบสอง=12 | ศูนย์=0

IMPORTANT:
- There are 57 political parties numbered 1-57
- This page may show only SOME parties (e.g., 1-20, 21-40, 41-57)
- Note which party numbers are visible on THIS page
- Many parties may have 0 votes

═══════════════════════════════════════════════════════════════════
PART 4: TOTALS (Usually only on the LAST page)
═══════════════════════════════════════════════════════════════════

If this page has totals:
1. บัตรดี = VALID votes (sum of ALL party votes across all pages)
2. บัตรเสีย = INVALID votes
3. บัตรไม่ประสงค์ลงคะแนน = BLANK votes
4. รวม = TOTAL

If totals are not on this page, set them to null.

═══════════════════════════════════════════════════════════════════
OUTPUT FORMAT - Return ONLY valid JSON, NO markdown:
═══════════════════════════════════════════════════════════════════

{
    "form_type": "ส.ส. 5/16 (บช)",
    "is_party_list": true,
    "province": "นนทบุรี",
    "constituency_number": 1,
    "district": "เมืองนนทบุรี",
    "polling_unit": 1,
    "page_parties": "1-20",
    "party_votes": {
        "1": {"numeric": 12, "thai_text": "สิบสอง"},
        "2": {"numeric": 0, "thai_text": "ศูนย์"},
        "8": {"numeric": 45, "thai_text": "สี่สิบห้า"},
        "16": {"numeric": 23, "thai_text": "ยี่สิบสาม"}
    },
    "valid_votes": null,
    "invalid_votes": null,
    "blank_votes": null,
    "total_votes": null
}"""


def get_combined_prompt() -> str:
    """Combined prompt that auto-detects form type (constituency or party-list)."""
    return """IMPORTANT: This document is in THAI language. All text on this form is in Thai.

You are analyzing a THAI ELECTION BALLOT COUNTING FORM from Thailand's Election Commission.

═══════════════════════════════════════════════════════════════════
PART 1: DETERMINE FORM TYPE (Look at TOP-RIGHT CORNER)
═══════════════════════════════════════════════════════════════════

Find the SQUARE BOX in the top-right area. Inside is the form code:

CONSTITUENCY forms (แบ่งเขตเลือกตั้ง):
- "ส.ส. 5/16" - Early voting
- "ส.ส. 5/17" - Out-of-district
- "ส.ส. 5/18" - By polling unit

PARTY-LIST forms (บัญชีรายชื่อ - บช):
- "ส.ส. 5/16 (บช)" - Early voting, party-list
- "ส.ส. 5/17 (บช)" - Out-of-district, party-list
- "ส.ส. 5/18 (บช)" - By polling unit, party-list

KEY: If you see "(บช)" or "บัญชีรายชื่อ" in the form title → it's a PARTY-LIST form.
     If you see "แบ่งเขตเลือกตั้ง" without "(บช)" → it's a CONSTITUENCY form.

NOTE: Thai numerals: ๑=1, ๒=2, ๓=3, ๔=4, ๕=5, ๖=6, ๗=7, ๘=8, ๙=9, ๐=0

═══════════════════════════════════════════════════════════════════
PART 2: LOCATION INFORMATION
═══════════════════════════════════════════════════════════════════

1. PROVINCE (จังหวัด): Look for "จังหวัด" followed by the province name.
2. CONSTITUENCY NUMBER: Look for "เขตเลือกตั้งที่" followed by a number.
3. DISTRICT (อำเภอ): Look for "อำเภอ" followed by the district name.
4. POLLING UNIT: Look for "หน่วยเลือกตั้งที่" followed by a number.

═══════════════════════════════════════════════════════════════════
PART 3: VOTE TABLE
═══════════════════════════════════════════════════════════════════

FOR CONSTITUENCY forms:
- Table has numbered rows (1, 2, 3...) with HANDWRITTEN vote counts
- Each row: number | numeric vote | Thai text for the number
- Typically 2-10 candidates per district

FOR PARTY-LIST forms:
- Table has party numbers (1-57) with HANDWRITTEN vote counts
- Each row: party number | numeric vote | Thai text for the number
- This page may show only SOME parties (e.g., 1-20, 21-40)
- Many parties may have 0 votes
- Note which party numbers are on this page

CRITICAL: Read each handwritten digit carefully. Look at the COMPLETE number.

═══════════════════════════════════════════════════════════════════
PART 4: TOTALS (bottom of form)
═══════════════════════════════════════════════════════════════════

1. บัตรดี / คะแนนเสียงที่ถูกต้อง = VALID votes
2. บัตรเสีย = INVALID votes
3. บัตรไม่ประสงค์ลงคะแนน = BLANK votes
4. รวม = TOTAL

═══════════════════════════════════════════════════════════════════
OUTPUT FORMAT - Return ONLY valid JSON, NO markdown:
═══════════════════════════════════════════════════════════════════

For CONSTITUENCY form:
{
    "form_type": "ส.ส. 5/16",
    "is_party_list": false,
    "province": "แพร่",
    "constituency_number": 1,
    "district": "เมืองแพร่",
    "polling_unit": 2,
    "vote_counts": {
        "1": {"numeric": 153, "thai_text": "หนึ่งร้อยห้าสิบสาม"},
        "2": {"numeric": 4, "thai_text": "สี่"}
    },
    "valid_votes": 157,
    "invalid_votes": 3,
    "blank_votes": 0,
    "total_votes": 160
}

For PARTY-LIST form:
{
    "form_type": "ส.ส. 5/16 (บช)",
    "is_party_list": true,
    "province": "แพร่",
    "constituency_number": 1,
    "district": "เมืองแพร่",
    "polling_unit": 2,
    "page_parties": "1-20",
    "party_votes": {
        "1": {"numeric": 12, "thai_text": "สิบสอง"},
        "2": {"numeric": 0, "thai_text": "ศูนย์"},
        "8": {"numeric": 45, "thai_text": "สี่สิบห้า"}
    },
    "valid_votes": null,
    "invalid_votes": null,
    "blank_votes": null,
    "total_votes": null
}
"""


def _strip_json_fences(text: str) -> str:
    """Remove markdown code fences from JSON response text."""
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]
    return text.strip()


def is_ballot_consistent(data: BallotData) -> bool:
    """
    Check if the extracted ballot data is internally consistent.
    
    v2.1 Update: Prioritizes numeric consistency (sum check).
    Metadata like province is secondary.
    """
    if not data:
        return False
        
    # 1. Sum Check (HIGHEST PRIORITY)
    # If the handwritten numbers sum up to the reported total, 
    # the extraction is likely perfect regardless of metadata.
    calculated_sum = sum(data.vote_counts.values()) if data.form_category == "constituency" else sum(data.party_votes.values())
    sum_matches = (data.valid_votes > 0 and calculated_sum == data.valid_votes)
    
    if sum_matches:
        return True # Perfect numeric consistency
        
    # 2. Thai Text Validation Rate (Secondary)
    thai_val = data.confidence_details.get("thai_text_validation", {})
    if isinstance(thai_val, dict):
        # If we have a very low validation rate, it's risky
        if thai_val.get("rate", 1.0) < 0.5:
            return False
            
    # 3. Sum Mismatch (Trigger retry if sum doesn't match and we aren't highly confident)
    if data.valid_votes > 0 and calculated_sum != data.valid_votes:
        return False
        
    return True


def extract_ballot_data_with_ai(image_path: str, form_type: Optional[FormType] = None, is_retry: bool = False) -> Optional[BallotData]:
    """
    Extract ballot data using the configured ensemble of OCR backends.

    Backends run in parallel; per-position consensus voting resolves
    disagreements. Configure via the EXTRACTION_BACKENDS env var.
    
    v2.0: Includes a self-correction loop that retries once with aggressive
    preprocessing if the first pass is inconsistent.
    """
    from model_backends import EnsembleExtractor, build_backends_from_env
    
    # First Pass
    result = EnsembleExtractor(build_backends_from_env()).extract(image_path, form_type)
    
    # Check consistency
    if result and not is_retry and not is_ballot_consistent(result):
        filename = os.path.basename(image_path)
        print(f"  [Self-Correction] Pass 1 inconsistent for {filename}. Analying structure...")
        
        # Phase 19: VLM Layout Verification
        try:
            import layout_verifier
            from ballot_types import FormType
            
            layout = layout_verifier.verifier.verify(image_path)
            if layout:
                print(f"  [Self-Correction] VLM Analysis: {layout}")
                
                # Check for form type mismatch
                # Map string code (e.g. "5/18") to FormType enum if possible
                # This is a simplified mapping logic
                if layout.form_type_code:
                    for ft in FormType:
                        if layout.form_type_code in ft.value:
                            if form_type != ft:
                                print(f"  [Self-Correction] Updating FormType from {form_type} to {ft}")
                                form_type = ft
                            break
        except Exception as e:
            print(f"  [Self-Correction] Layout verification skipped: {e}")

        print(f"  [Self-Correction] Retrying with aggressive vision...")
        
        # Trigger aggressive preprocessing in adaptive_ocr via env var hint
        os.environ["ADAPTIVE_OCR_FORCE_AGGRESSIVE"] = "1"
        try:
            # Second Pass
            retry_result = EnsembleExtractor(build_backends_from_env()).extract(image_path, form_type)
            
            if retry_result:
                # If retry is better (more consistent), use it
                if is_ballot_consistent(retry_result) or retry_result.confidence_score > result.confidence_score:
                    print(f"  [Self-Correction] Retry successful. Confidence improved: {result.confidence_score:.2f} -> {retry_result.confidence_score:.2f}")
                    return retry_result
                else:
                    print(f"  [Self-Correction] Retry did not improve results. Keeping pass 1.")
        finally:
            # Cleanup hint
            if "ADAPTIVE_OCR_FORCE_AGGRESSIVE" in os.environ:
                del os.environ["ADAPTIVE_OCR_FORCE_AGGRESSIVE"]
                
    return result


def _extract_with_crops(image_path: str, form_type: FormType, api_key: str, model_id: str = _OPENROUTER_MODEL, base_url: str = "https://openrouter.ai/api/v1", timeout: int = 30) -> Optional[BallotData]:
    """
    Crop-aware extraction that sends only relevant regions to the API.

    This reduces token costs by ~70% by cropping to just the vote-count column
    and summary section instead of sending the full page.

    Args:
        image_path: Path to the ballot image
        form_type: The detected form type
        api_key: OpenRouter API key

    Returns:
        BallotData if extraction successful, None otherwise
    """
    import requests

    try:
        from crop_utils import crop_page_image, FORM_TEMPLATES, _DEFAULT_TEMPLATE
    except ImportError:
        print("  crop_utils not available for crop-aware extraction")
        return None

    try:
        from PIL import Image
    except ImportError:
        print("  Pillow not available for crop-aware extraction")
        return None

    # Select template based on form type
    template = FORM_TEMPLATES.get(form_type, _DEFAULT_TEMPLATE)

    # Determine if this is page 1 or a continuation page
    # Heuristic: check filename for "page-1" or similar patterns
    is_page_1 = True
    filename = os.path.basename(image_path).lower()
    if "page-" in filename and "page-1" not in filename and "page-01" not in filename:
        # e.g. "page-2.png", "page-02.png"
        import re
        match = re.search(r'page-(\d+)', filename)
        if match and int(match.group(1)) > 1:
            is_page_1 = False
    
    # Select appropriate region from template
    crop_region = template.vote_numbers_p1 if is_page_1 else template.vote_numbers_cont

    print(f"  Using crop template for {form_type.value}: Page 1={is_page_1}, Region={crop_region}")

    # Crop the vote-count column region
    try:
        vote_crop_path = crop_page_image(image_path, crop_region)
    except Exception as e:
        print(f"  Failed to crop vote region: {e}")
        return None

    try:
        # Preprocess and encode the cropped image for better OCR
        cropped_image_data = base64.b64encode(
            _preprocess_image(vote_crop_path)
        ).decode("utf-8")

        # Use a focused prompt for the cropped vote-count region
        prompt = get_vote_numbers_prompt()

        # Make API call with cropped image
        response = requests.post(
            url=f"{base_url.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/election-verification",
                "X-Title": "Thai Election Ballot OCR",
            },
            json={
                "model": model_id,
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{cropped_image_data}"}},
                        {"type": "text", "text": prompt},
                    ],
                }],
                "max_tokens": 1024,
            },
            timeout=timeout,
        )

        if response.status_code != 200:
            print(f"  Crop API error: {response.status_code}")
            return None

        result = response.json()
        response_text = result["choices"][0]["message"]["content"]

        # Parse the vote counts from the cropped region
        vote_data = json.loads(_strip_json_fences(response_text))

        # Build minimal ballot data from the extracted votes
        if isinstance(vote_data, list) and len(vote_data) > 0:
            vote_counts = {}
            vote_details = {}

            for entry in vote_data:
                position = entry.get("position", 0)
                numeric = entry.get("numeric", 0)
                thai_text = entry.get("thai", "")

                if position > 0:
                    vote_counts[position] = numeric
                    if thai_text:
                        from ballot_types import validate_vote_entry
                        vote_details[position] = validate_vote_entry(numeric, thai_text)

            # Calculate total from vote counts
            total_votes = sum(vote_counts.values())

            # Build polling station ID from form type
            station_id = f"Constituency-{form_type.value}"

            return BallotData(
                form_type=form_type.value,
                form_category="party_list" if form_type.is_party_list else "constituency",
                province="",  # Would need additional crops to extract
                constituency_number=0,
                district="",
                polling_unit=0,
                polling_station_id=station_id,
                vote_counts=vote_counts,
                vote_details=vote_details,
                party_votes={},
                party_details={},
                total_votes=total_votes,
                valid_votes=total_votes,
                invalid_votes=0,
                blank_votes=0,
                source_file=image_path,
                confidence_score=0.7,  # Lower confidence due to missing metadata
                confidence_details={"level": "MEDIUM", "crop_based": True},
            )

        return None

    except json.JSONDecodeError as e:
        print(f"  Crop extraction JSON error: {e}")
        return None
    except Exception as e:
        print(f"  Crop extraction failed: {e}")
        return None
    finally:
        # Clean up temporary crop file
        try:
            os.unlink(vote_crop_path)
        except (OSError, NameError):
            pass


def get_vote_numbers_prompt() -> str:
    """Prompt for extracting vote numbers from a cropped ballot region."""
    return """You are reading a CROPPED section of a Thai election ballot tally form.

This section shows the VOTE COUNT COLUMNS only. Each visible row has:
  LEFT:   position/candidate number (printed, e.g. 1, 2, 3…)
  MIDDLE: vote count as handwritten Arabic numerals
  RIGHT:  vote count written in Thai words (handwritten)

READING STRATEGY — follow this order for accuracy:
1. Read the Thai WORDS column (rightmost) FIRST — Thai text is more
   reliable than handwritten digits for AI vision.
2. Convert the Thai words to an integer using the reference below.
3. Cross-check against the handwritten numeric column (middle).
4. If both agree → use that value.
5. If they differ → trust the Thai words value.

THAI NUMBER WORDS (building blocks):
  ศูนย์=0  หนึ่ง=1  สอง=2  สาม=3  สี่=4  ห้า=5  หก=6  เจ็ด=7  แปด=8  เก้า=9
  สิบ=10  ร้อย=100  พัน=1,000  หมื่น=10,000  แสน=100,000

EXAMPLES:
  หนึ่งร้อยห้าสิบสาม = 153
  สี่สิบห้า           = 45
  สิบสอง              = 12
  สอง                 = 2
  ศูนย์               = 0
  สองพันสามร้อยสิบสอง = 2,312

THAI NUMERAL DIGITS (if any appear in the numeric column):
  ๐=0  ๑=1  ๒=2  ๓=3  ๔=4  ๕=5  ๖=6  ๗=7  ๘=8  ๙=9

IMPORTANT:
- Include EVERY row visible, even rows where the count is 0 (ศูนย์).
- Do not skip any position number.
- Return numeric values as plain integers (e.g. 153, not "153").

Return ONLY a JSON array — no markdown, no explanations, no code fences:
[
    {"position": 1, "numeric": 153, "thai": "หนึ่งร้อยห้าสิบสาม"},
    {"position": 2, "numeric": 45,  "thai": "สี่สิบห้า"},
    {"position": 3, "numeric": 0,   "thai": "ศูนย์"}
]"""


def get_summary_prompt() -> str:
    """Prompt for extracting summary totals from a cropped region."""
    return """
Extract vote totals from this Thai ballot summary section.
Return ONLY a JSON object:
{
    "total": {"n": 1234},
    "valid": {"n": 1200},
    "invalid": {"n": 20},
    "blank": {"n": 14}
}
"""


def extract_with_tesseract(image_path: str, form_type: Optional[FormType] = None) -> Optional[BallotData]:
    """
    Fallback extraction using local Tesseract OCR.

    This is a free, offline fallback when cloud AI APIs are unavailable.
    It provides basic text extraction and number parsing, though less
    accurate than AI vision for handwritten content.

    Args:
        image_path: Path to the ballot image
        form_type: Optional form type hint

    Returns:
        BallotData if extraction successful, None otherwise
    """
    try:
        from tesseract_ocr import TesseractOCR, is_available

        if not is_available():
            print("  Tesseract OCR not available")
            return None

        ocr = TesseractOCR()
        result = ocr.process_ballot(image_path)

        if not result:
            print("  Tesseract extraction failed")
            return None

        print(f"  Tesseract OCR confidence: {result.confidence:.1f}%")

        # Try to parse structured data from OCR text
        return parse_ocr_text_to_ballot_data(result.text, image_path, form_type)

    except ImportError:
        print("  tesseract_ocr module not available")
        return None
    except Exception as e:
        print(f"  Tesseract extraction error: {e}")
        return None


def parse_ocr_text_to_ballot_data(ocr_text: str, image_path: str, form_type: Optional[FormType] = None) -> Optional[BallotData]:
    """Parse OCR text output into structured ballot data using Claude."""
    import anthropic

    client = anthropic.Anthropic()

    prompt = f"""Below is the OCR output from a Thai election ballot counting form.
Extract the structured data from this OCR text.

OCR OUTPUT:
{ocr_text}

Extract the following:
1. form_code: "5/16", "5/17", or "5/18"
2. is_party_list: true if this is a party-list form (has "บช"), false otherwise
3. province: The Thai province name (after "จังหวัด")
4. district: The district/constituency info
5. vote_counts: Dictionary mapping candidate/party number to vote count
6. valid_votes, invalid_votes, blank_votes, total_votes: The totals from the bottom

Return ONLY valid JSON with NO markdown formatting:
{{
    "form_code": "5/16" or "5/17" or "5/18",
    "is_party_list": true or false,
    "province": "Thai province name",
    "district": "district info",
    "polling_unit": "unit number or null",
    "num_entries": count of vote rows,
    "vote_counts": {{
        "1": {{"numeric": vote_count, "thai_text": "Thai words if visible"}},
        ...
    }},
    "valid_votes": number or null,
    "invalid_votes": number or null,
    "blank_votes": number or null,
    "total_votes": number or null
}}"""

    try:
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2048,
            messages=[
                {"role": "user", "content": prompt}
            ],
        )

        response_text = message.content[0].text
        data = json.loads(_strip_json_fences(response_text))

        # Process the data (same logic as before)
        return process_extracted_data(data, image_path, form_type)

    except Exception as e:
        print(f"  Error parsing OCR text: {e}")
        return None


def extract_with_claude_vision(image_path: str, form_type: Optional[FormType] = None, model_id: str = "claude-sonnet-4-20250514") -> Optional[BallotData]:
    """Fallback to Claude Vision for extraction."""
    import anthropic

    client = anthropic.Anthropic()

    image_data = base64.b64encode(_preprocess_image(image_path)).decode("utf-8")

    # Detect form type if not provided - do this as part of extraction for consistency
    if form_type is None:
        # Use a combined prompt that detects form type AND extracts data
        prompt = """You are analyzing a THAI ELECTION BALLOT COUNTING FORM. This is an official document from Thailand's Election Commission (EC/กกต.).

═══════════════════════════════════════════════════════════════════
PART 1: FORM IDENTIFICATION (Look at TOP-RIGHT CORNER)
═══════════════════════════════════════════════════════════════════

Find the SQUARE BOX in the top-right area of the form. Inside this box is the form code.

The form code will be ONE of these:
- "ส.ส. 5/16" or "สส. ๕/๑๖" (Early voting - ลงคะแนนก่อนวันเลือกตั้ง)
- "ส.ส. 5/17" or "สส. ๕/๑๗" (Out-of-district - นอกเขตเลือกตั้ง)
- "ส.ส. 5/18" or "สส. ๕/๑๘" (By polling unit - รายหน่วย)

NOTE: Thai numerals look like this: ๑=1, ๒=2, ๓=3, ๔=4, ๕=5, ๖=6, ๗=7, ๘=8, ๙=9, ๐=0
So "๕/๑๗" means "5/17"

If the form title contains "(บช)" or "บัญชีรายชื่อ", it's a PARTY-LIST form.
If the form title says "แบ่งเขตเลือกตั้ง" without "(บช)", it's a CONSTITUENCY form.

═══════════════════════════════════════════════════════════════════
PART 2: LOCATION INFORMATION (Look at HEADER SECTION)
═══════════════════════════════════════════════════════════════════

Find these fields in the header area (usually near the top of the form):

1. PROVINCE (จังหวัด): Look for the word "จังหวัด" followed by the province name.
   Read the EXACT Thai characters. Do not guess or translate.

   Examples of Thai provinces:
   - แพร่ (Phrae)
   - เชียงใหม่ (Chiang Mai)
   - กรุงเทพมหานคร (Bangkok)
   - นครศรีธรรมราช (Nakhon Si Thammarat)
   - สุโขทัย (Sukhothai)

2. CONSTITUENCY/DISTRICT (เขตเลือกตั้ง): Look for "เขตเลือกตั้งที่" or "เขต" followed by a number.

3. DISTRICT NAME (อำเภอ): Look for "อำเภอ" followed by the district name.

4. POLLING UNIT (หน่วยเลือกตั้ง): Look for "หน่วยเลือกตั้งที่" or "หน่วย" followed by a number.

═══════════════════════════════════════════════════════════════════
PART 3: VOTE TABLE (Look at MAIN BODY of the form)
═══════════════════════════════════════════════════════════════════

The vote table is the main section of the form. It has multiple rows, one per candidate.

Each row contains these columns (left to right):
┌────────────┬──────────────────┬─────────────────────────────────┐
│ ลำดับ      │ คะแนน (Numeric)  │ จำนวนคะแนน (Thai text)          │
│ (Number)   │ (Handwritten)    │ (Written in Thai words)         │
├────────────┼──────────────────┼─────────────────────────────────┤
│     1      │     [hand]       │ [Thai words like "หนึ่งร้อยห้าสิบ"]│
│     2      │     [hand]       │ [Thai words]                     │
│    ...     │     [hand]       │ [Thai words]                     │
└────────────┴──────────────────┴─────────────────────────────────┘

CRITICAL INSTRUCTIONS FOR READING HANDWRITTEN NUMBERS:

1. Look at EACH handwritten digit individually
2. A "1" is a single vertical stroke
3. A "4" has a vertical line and horizontal line
4. A "7" has two strokes forming an angle
5. Read the COMPLETE number - don't stop early
6. If you see "153", read it as 153, not 15 or 53

CROSS-VALIDATION:
- The Thai text column should spell out the same number
- "หนึ่งร้อยห้าสิบสาม" = 153 (one hundred fifty three)
- "หนึ่งร้อยห้า" = 105 or 150 depending on context
- Use the Thai text to verify your numeric reading

═══════════════════════════════════════════════════════════════════
PART 4: TOTALS SECTION (Look at BOTTOM of the form)
═══════════════════════════════════════════════════════════════════

At the bottom of the form, find these total fields:

1. บัตรดี / คะแนนเสียงที่ถูกต้อง = VALID votes (sum of all candidate votes)
2. บัตรเสีย = INVALID votes
3. บัตรไม่ประสงค์ลงคะแนน = BLANK votes (voter didn't choose anyone)
4. รวม = TOTAL (should equal valid + invalid + blank)

═══════════════════════════════════════════════════════════════════
OUTPUT FORMAT
═══════════════════════════════════════════════════════════════════

Return ONLY valid JSON with NO markdown formatting, NO code blocks:

{
    "form_code": "5/16" or "5/17" or "5/18",
    "is_party_list": true or false,
    "province": "exact Thai province name",
    "constituency": constituency number,
    "district": "Thai district name",
    "polling_unit": unit number or null,
    "num_candidates": total number of candidate rows,
    "vote_counts": {
        "1": {"numeric": exact_handwritten_number, "thai_text": "Thai words from column 3"},
        "2": {"numeric": exact_handwritten_number, "thai_text": "Thai words from column 3"},
        "3": {"numeric": exact_handwritten_number, "thai_text": "Thai words from column 3"}
    },
    "valid_votes": number,
    "invalid_votes": number,
    "blank_votes": number,
    "total_votes": number
}"""
    else:
        # Use specific prompt based on known form type
        if form_type.is_party_list:
            prompt = get_party_list_prompt()
        else:
            prompt = get_constituency_prompt()

    try:
        message = client.messages.create(
            model=model_id,
            max_tokens=2048,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": image_data,
                            },
                        },
                        {
                            "type": "text",
                            "text": prompt,
                        },
                    ],
                }
            ],
        )

        # Parse JSON response
        response_text = message.content[0].text
        data = json.loads(_strip_json_fences(response_text))

        # Use shared processing function
        return process_extracted_data(data, image_path, form_type)

    except Exception as e:
        print(f"Error extracting data from {image_path}: {e}")
        return None


def process_extracted_data(data: dict, image_path: str, form_type: Optional[FormType] = None) -> Optional[BallotData]:
    """Process extracted data into a BallotData object with validation."""
    try:
        # Determine if party-list from either form_type or response data
        if form_type is not None:
            is_party_list = form_type.is_party_list
        else:
            is_party_list = data.get("is_party_list", False)

        # Handle constituency vs party-list forms differently
        vote_counts = {}
        vote_details = {}
        party_votes = {}
        party_details = {}
        candidate_info = {}  # NEW: Store candidate details for constituency forms

        if is_party_list:
            # Party-list form: use party_votes
            raw_party_votes = data.get("party_votes", {})
            for party_num, vote_data in raw_party_votes.items():
                if vote_data is None:
                    continue
                # Convert Thai numerals to Arabic (๑๒๓ -> 123)
                party_num = convert_thai_numerals(str(party_num))
                if isinstance(vote_data, dict):
                    numeric = vote_data.get("numeric", 0)
                    thai_text = vote_data.get("thai_text", "")
                    entry = validate_vote_entry(numeric, thai_text)
                    party_votes[str(party_num)] = numeric
                    party_details[str(party_num)] = entry
                else:
                    party_votes[str(party_num)] = int(vote_data)
        else:
            # Constituency form: use vote_counts
            raw_vote_counts = data.get("vote_counts", {})
            for candidate_num, vote_data in raw_vote_counts.items():
                if vote_data is None:
                    continue
                # Convert Thai numerals to Arabic
                candidate_num = convert_thai_numerals(str(candidate_num))
                if isinstance(vote_data, dict):
                    numeric = vote_data.get("numeric", 0)
                    thai_text = vote_data.get("thai_text", "")
                    entry = validate_vote_entry(numeric, thai_text)
                    vote_counts[int(candidate_num)] = numeric
                    vote_details[int(candidate_num)] = entry
                else:
                    vote_counts[int(candidate_num)] = int(vote_data)

        # Calculate sum for validation
        calculated_sum = sum(vote_counts.values()) if vote_counts else sum(party_votes.values())
        reported_valid = data.get("valid_votes", 0) or 0
        reported_invalid = data.get("invalid_votes", 0) or 0
        reported_blank = data.get("blank_votes", 0) or 0
        reported_total = data.get("total_votes", 0) or 0

        # Log validation results
        if vote_details:
            validated_count = sum(1 for e in vote_details.values() if e.is_validated)
            print(f"  Validated {validated_count}/{len(vote_details)} entries (numeric vs Thai text)")
        if party_details:
            validated_count = sum(1 for e in party_details.values() if e.is_validated)
            print(f"  Validated {validated_count}/{len(party_details)} entries (numeric vs Thai text)")

        # Check sum validation
        print(f"  Sum check: calculated={calculated_sum}, valid={reported_valid}, invalid={reported_invalid}, blank={reported_blank}, total={reported_total}")

        if reported_valid and calculated_sum != reported_valid:
            print(f"  WARNING: Sum != Valid votes! Sum: {calculated_sum}, Valid: {reported_valid}")
        elif reported_valid:
            print("  ✓ Sum matches valid votes")

        if reported_total and reported_valid:
            expected_total = reported_valid + reported_invalid + reported_blank
            if reported_total != expected_total:
                print(f"  WARNING: Total mismatch! Expected: {expected_total} (valid+invalid+blank), Reported: {reported_total}")
            else:
                print("  ✓ Total = Valid + Invalid + Blank")

        # Validate province name against ECT data
        province_name = data.get("province", "")
        if ECT_AVAILABLE and province_name:
            is_valid, canonical = ect_data.validate_province_name(province_name)
            if not is_valid:
                print(f"  WARNING: Province '{province_name}' not found in ECT data")
                all_provinces = ect_data.list_provinces()
                for prov in all_provinces:
                    if province_name in prov or prov in province_name:
                        print(f"  SUGGESTION: Did you mean '{prov}'?")
                        break
            else:
                print(f"  Province validated: {canonical}")

        # NEW: Match candidates for constituency forms
        if not is_party_list and ECT_AVAILABLE and province_name:
            constituency_number = data.get("constituency_number", data.get("constituency", 0))
            for position, vote_count in vote_counts.items():
                candidate = ect_data.get_candidate_by_thai_province(province_name, constituency_number, position)
                if candidate:
                    party = ect_data.get_party_for_candidate(candidate)
                    candidate_info[position] = {
                        "name": candidate.mp_app_name,
                        "party_id": candidate.mp_app_party_id,
                        "party_name": party.name if party else "Unknown",
                        "party_abbr": party.abbr if party else ""
                    }
                    print(f"  Position {position}: {candidate.mp_app_name} ({party.abbr if party else '?'}) - {vote_count} votes")
                else:
                    print(f"  WARNING: No candidate found for position {position}")
                    candidate_info[position] = {
                        "name": "Unknown",
                        "party_id": None,
                        "party_name": "Unknown",
                        "party_abbr": ""
                    }

        # NEW: Enrich party information for party-list forms
        party_info = {}  # NEW: Store party details for party-list forms
        if is_party_list and ECT_AVAILABLE:
            for party_num in party_votes.keys():
                party = ect_data.get_party(party_num)
                if party:
                    party_info[str(party_num)] = {
                        "name": party.name,
                        "abbr": party.abbr,
                        "color": party.color
                    }
                    print(f"  Party #{party_num}: {party.name} ({party.abbr})")
                else:
                    print(f"  WARNING: Party #{party_num} not found in ECT data")
                    party_info[str(party_num)] = {
                        "name": "Unknown",
                        "abbr": "",
                        "color": ""
                    }

        # Determine form_type string for output
        if form_type is not None:
            form_type_output = str(form_type.value)
        else:
            form_code = data.get("form_code", data.get("form_type", "5/17"))
            # Extract form code from form_type if it contains the full name
            if "5/16" in form_code:
                form_code = "5/16"
            elif "5/17" in form_code:
                form_code = "5/17"
            elif "5/18" in form_code:
                form_code = "5/18"
            form_type_output = data.get("form_type", f"ส.ส. {form_code}")
            if is_party_list and "(บช)" not in form_type_output:
                form_type_output += " (บช)"

        # Extract location info with new field names
        province = data.get("province", "")
        constituency_number = data.get("constituency_number", data.get("constituency", 0))
        district = data.get("district", "")
        polling_unit = data.get("polling_unit", 0)
        page_parties = data.get("page_parties", data.get("page_info", ""))

        # Build polling_station_id
        polling_station_id = f"{province}-เขต {constituency_number}"
        if district:
            polling_station_id += f" {district}"
        if polling_unit:
            polling_station_id += f"-{polling_unit}"

        # Calculate confidence score
        confidence_details = {}
        confidence_score = 0.0

        # Factor 1: Thai text validation (40% weight)
        all_details = vote_details if vote_details else party_details
        if all_details:
            validated_count = sum(1 for e in all_details.values() if e.is_validated)
            validation_rate = validated_count / len(all_details)
            confidence_details["thai_text_validation"] = {
                "weight": 0.4,
                "validated": validated_count,
                "total": len(all_details),
                "rate": validation_rate,
                "score": validation_rate * 0.4
            }
            confidence_score += validation_rate * 0.4

        # Factor 2: Sum validation (30% weight)
        sum_valid = (calculated_sum == reported_valid) if reported_valid else False
        confidence_details["sum_validation"] = {
            "weight": 0.3,
            "calculated_sum": calculated_sum,
            "reported_valid": reported_valid,
            "match": sum_valid,
            "score": 0.3 if sum_valid else 0.0
        }
        confidence_score += 0.3 if sum_valid else 0.0

        # Factor 3: Province validation (30% weight)
        province_valid = False
        if ECT_AVAILABLE and province:
            is_valid, _ = ect_data.validate_province_name(province)
            province_valid = is_valid
        confidence_details["province_validation"] = {
            "weight": 0.3,
            "province": province,
            "valid": province_valid,
            "score": 0.3 if province_valid else 0.0
        }
        confidence_score += 0.3 if province_valid else 0.0

        confidence_details["overall_score"] = confidence_score

        # Determine confidence level
        if confidence_score >= 0.9:
            confidence_level = "HIGH"
        elif confidence_score >= 0.7:
            confidence_level = "MEDIUM"
        elif confidence_score >= 0.5:
            confidence_level = "LOW"
        else:
            confidence_level = "VERY_LOW"

        confidence_details["level"] = confidence_level

        print(f"  Confidence: {confidence_level} ({confidence_score:.1%})")

        return BallotData(
            form_type=form_type_output,
            form_category="party_list" if is_party_list else "constituency",
            province=province,
            constituency_number=constituency_number if isinstance(constituency_number, int) else 0,
            district=district,
            polling_unit=polling_unit if isinstance(polling_unit, int) else 0,
            page_parties=page_parties,
            polling_station_id=polling_station_id,
            vote_counts=vote_counts,
            vote_details=vote_details,
            party_votes=party_votes,
            party_details=party_details,
            candidate_info=candidate_info,  # Include candidate info
            party_info=party_info,  # NEW: Include party info for party-list forms
            total_votes=reported_total or calculated_sum,
            valid_votes=reported_valid or calculated_sum,
            invalid_votes=reported_invalid,
            blank_votes=reported_blank,
            source_file=str(image_path),
            confidence_score=confidence_score,
            confidence_details=confidence_details,
        )

    except Exception as e:
        print(f"Error processing extracted data: {e}")
        return None


