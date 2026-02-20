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

_DRIVE_MAP_CACHE: Optional[dict] = None


def _load_drive_mapping() -> dict:
    """Load drive_file_mapping.json once for provenance linking."""
    global _DRIVE_MAP_CACHE
    if _DRIVE_MAP_CACHE is not None:
        return _DRIVE_MAP_CACHE
    mapping_path = Path("drive_file_mapping.json")
    if not mapping_path.exists():
        _DRIVE_MAP_CACHE = {}
        return _DRIVE_MAP_CACHE
    try:
        payload = json.loads(mapping_path.read_text(encoding="utf-8"))
        files = payload.get("files", {}) if isinstance(payload, dict) else {}
        _DRIVE_MAP_CACHE = files if isinstance(files, dict) else {}
    except Exception:
        _DRIVE_MAP_CACHE = {}
    return _DRIVE_MAP_CACHE


def _resolve_path(path: str) -> str:
    """Safely resolve a path to its absolute form."""
    try:
        return str(Path(path).expanduser().resolve())
    except Exception:
        return path


def _lookup_drive_source_for_pdf(pdf_path: str) -> dict:
    """Best-effort lookup from local PDF path to Drive source metadata."""
    pdf_abs = _resolve_path(pdf_path)
    files = _load_drive_mapping()
    by_name_match = None
    
    for drive_id, entry in files.items():
        if not isinstance(entry, dict):
            continue
            
        local_path = str(entry.get("local_path", "")).strip()
        if local_path and _resolve_path(local_path) == pdf_abs:
            return {
                "drive_id": drive_id,
                "drive_url": entry.get("drive_url", ""),
                "drive_name": entry.get("name", ""),
            }
            
        if entry.get("name") and Path(str(entry["name"])).name == Path(pdf_abs).name:
            by_name_match = {
                "drive_id": drive_id,
                "drive_url": entry.get("drive_url", ""),
                "drive_name": entry.get("name", ""),
            }
            
    return by_name_match or {}


def _write_image_provenance(image_path: str, pdf_path: str, page_number: int) -> None:
    """Write sidecar provenance for each generated PNG."""
    try:
        payload = {
            "source_pdf": str(Path(pdf_path).expanduser().resolve()),
            "source_pdf_name": Path(pdf_path).name,
            "pdf_page_number": int(page_number),
            "generated_image": str(Path(image_path).expanduser().resolve()),
        }
        payload.update(_lookup_drive_source_for_pdf(pdf_path))
        sidecar = f"{image_path}.source.json"
        Path(sidecar).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        # Provenance sidecar is best-effort; conversion should still succeed.
        pass


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
            _write_image_provenance(output_path, pdf_path, page_num + 1)
        else:
            # No embedded image - render page at 150 DPI (reasonable default)
            mat = fitz.Matrix(150 / 72, 150 / 72)
            pix = page.get_pixmap(matrix=mat)
            output_path = os.path.join(output_dir, f"page-{page_num + 1}.png")
            pix.save(output_path)
            output_paths.append(output_path)
            _write_image_provenance(output_path, pdf_path, page_num + 1)

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
    output_paths = [str(img) for img in images]
    for idx, path in enumerate(output_paths, start=1):
        _write_image_provenance(path, pdf_path, idx)
    return output_paths


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
        except Exception as e:
            print(f"  Static preprocessing fallback failed: {e}")
            
    except Exception as e:
        print(f"  Preprocessing failed: {e}")
    
    return image_path


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
    """Combined prompt that auto-detects form type - optimized to prevent hallucination."""
    return """You are analyzing a Thai election ballot counting form.

CRITICAL INSTRUCTION: Extract ONLY the data you actually see in this image. Do NOT invent or copy example values.

STEP 1 - Identify the form:
- Find the form code in the top-right box (e.g., ส.ส. 5/16, ส.ส. 5/17, ส.ส. 5/18)
- If it has (บช) suffix, set is_party_list to true

STEP 2 - Extract location:
- Province after "จังหวัด" (read the actual province name from the image)
- District after "อำเภอ"
- Constituency number after "เขตเลือกตั้งที่"

STEP 3 - Read the vote table carefully:
- Each row has: position number, handwritten vote count, Thai text
- Read EVERY row you can see
- Write the EXACT numbers you see handwritten
- Do NOT guess or estimate

STEP 4 - Find totals at bottom if present:
- Valid votes, Invalid votes, Blank votes, Total

Return ONLY valid JSON (no markdown, no explanation):
{
    "form_type": "the actual form code you see",
    "is_party_list": true or false,
    "province": "the actual province name you see",
    "constituency_number": the number you see,
    "district": "the actual district name you see",
    "vote_counts": {"N": {"numeric": X, "thai_text": "..."}},
    "valid_votes": number or null,
    "invalid_votes": number or null,
    "blank_votes": number or null,
    "total_votes": number or null
}

REMEMBER: Extract real data from THIS image only."""


def get_minimal_prompt() -> str:
    """Minimal prompt for simpler vision models (e.g., LM Studio glm-ocr).

    This prompt is shorter and more direct to avoid truncation with less capable models.
    Focus only on vote counts since text extraction is unreliable with these models.
    """
    return """OCR task: Read handwritten numbers from ballot table.

Instructions:
1. Look at the column with handwritten numbers (right side of table)
2. Each row has a position number (left) and vote count (right)
3. Read the VOTE COUNT numbers only

Output format (JSON only, no explanation):
{"vote_counts":{"1":NUM,"2":NUM,"3":NUM,...}}

Replace NUM with actual handwritten numbers you see. Include all rows visible."""


def _strip_json_fences(text: str) -> str:
    """Remove markdown code fences from JSON response text."""
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]
    return text.strip()


def _try_parse_lenient_json(text: str) -> Optional[dict]:
    """Try to parse JSON that may have minor syntax errors (missing quotes on keys)."""
    import re

    # First try standard parsing
    text = text.strip()
    try:
        data = json.loads(text)
        return _convert_string_numbers(data)
    except json.JSONDecodeError:
        pass

    # Try to fix common issues:
    # 1. Missing opening quotes on property names: form_type": -> "form_type":
    # 2. Unquoted property names: total_votes: -> "total_votes":
    # 3. Unquoted numeric keys: 1: -> "1":

    # Add quotes to unquoted property names (word followed by : with or without quote after)
    fixed = re.sub(r'(\w+)":', r'"\1":', text)  # word": -> "word":
    fixed = re.sub(r'(\w+):', r'"\1":', fixed)   # word: -> "word":

    # Add quotes to numeric keys
    fixed = re.sub(r'(\d+):', r'"\1":', fixed)

    try:
        data = json.loads(fixed)
        return _convert_string_numbers(data)
    except json.JSONDecodeError:
        pass

    # Last resort: try to extract the JSON object
    start = fixed.find('{')
    end = fixed.rfind('}')
    if start != -1 and end > start:
        try:
            data = json.loads(fixed[start:end+1])
            return _convert_string_numbers(data)
        except json.JSONDecodeError:
            pass

    return None


def _convert_string_numbers(data):
    """Convert string numbers to integers in nested dicts."""
    if isinstance(data, dict):
        result = {}
        for k, v in data.items():
            if isinstance(v, str) and v.strip().isdigit():
                result[k] = int(v)
            elif isinstance(v, str) and v.strip() == "":
                continue  # Skip empty strings
            elif isinstance(v, dict):
                result[k] = _convert_string_numbers(v)
            else:
                result[k] = v
        return result
    elif isinstance(data, list):
        return [_convert_string_numbers(item) for item in data]
    return data


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


def _verify_layout_and_update_form_type(image_path: str, form_type: Optional[FormType]) -> Optional[FormType]:
    """Phase 19: Use VLM to verify layout and correct form type if mismatched."""
    try:
        import layout_verifier
        from ballot_types import FormType
        
        layout = layout_verifier.verifier.verify(image_path)
        if layout and layout.form_type_code:
            for ft in FormType:
                if layout.form_type_code in ft.value and form_type != ft:
                    print(f"  [Self-Correction] Updating FormType to {ft}")
                    return ft
    except Exception as e:
        print(f"  [Self-Correction] Layout verification skipped: {e}")
    return form_type


def _retry_with_ensemble(image_path: str, form_type: Optional[FormType]) -> Optional[BallotData]:
    """Execute a second pass with aggressive vision preprocessing."""
    from model_backends import EnsembleExtractor, build_backends_from_env
    
    os.environ["ADAPTIVE_OCR_FORCE_AGGRESSIVE"] = "1"
    try:
        return EnsembleExtractor(build_backends_from_env()).extract(image_path, form_type)
    finally:
        if "ADAPTIVE_OCR_FORCE_AGGRESSIVE" in os.environ:
            del os.environ["ADAPTIVE_OCR_FORCE_AGGRESSIVE"]


def extract_ballot_data_with_ai(image_path: str, form_type: Optional[FormType] = None, is_retry: bool = False, backend_spec: Optional[str] = None) -> Optional[BallotData]:
    """Extract ballot data with an automatic self-correction loop for inconsistent results."""
    from model_backends import EnsembleExtractor, build_backends_from_env
    
    orig_backends = os.environ.get("EXTRACTION_BACKENDS")
    if backend_spec:
        os.environ["EXTRACTION_BACKENDS"] = backend_spec
    elif not is_retry and not orig_backends:
        # Pass 1: Only use fast local models
        os.environ["EXTRACTION_BACKENDS"] = "trocr,tesseract"
        
    try:
        result = EnsembleExtractor(build_backends_from_env()).extract(image_path, form_type)
    finally:
        if backend_spec or (not is_retry and not orig_backends):
            if orig_backends is not None:
                os.environ["EXTRACTION_BACKENDS"] = orig_backends
            elif "EXTRACTION_BACKENDS" in os.environ:
                del os.environ["EXTRACTION_BACKENDS"]
    
    if is_retry or (result and is_ballot_consistent(result)):
        return result

    # Self-Correction Pass
    filename = os.path.basename(image_path)
    reason = "missing result" if not result else "inconsistent result"
    print(f"  [Self-Correction] Pass 1 failed for {filename} ({reason}).")
    
    form_type = _verify_layout_and_update_form_type(image_path, form_type)
    print("  [Self-Correction] Retrying with aggressive vision...")
    
    retry_result = _retry_with_ensemble(image_path, form_type)
    
    if not retry_result:
        return result
        
    if not result or is_ballot_consistent(retry_result) or retry_result.confidence_score > result.confidence_score:
        improvement = f" (improved confidence: {result.confidence_score:.2f} -> {retry_result.confidence_score:.2f})" if result else ""
        print(f"  [Self-Correction] Retry successful{improvement}")
        return retry_result
    
    print("  [Self-Correction] Retry did not improve results. Keeping pass 1.")
    return result


def _get_crop_region(image_path: str, form_type: FormType) -> tuple[Any, bool]:
    """Determine the crop region based on form type and page number."""
    from crop_utils import FORM_TEMPLATES, _DEFAULT_TEMPLATE
    template = FORM_TEMPLATES.get(form_type, _DEFAULT_TEMPLATE)
    
    is_page_1 = True
    filename = os.path.basename(image_path).lower()
    if "page-" in filename and not any(p in filename for p in ["page-1", "page-01"]):
        import re
        match = re.search(r'page-(\d+)', filename)
        if match and int(match.group(1)) > 1:
            is_page_1 = False
            
    region = template.vote_numbers_p1 if is_page_1 else template.vote_numbers_cont
    return region, is_page_1


def _call_crop_api(api_key: str, image_data: str, model_id: str, base_url: str, timeout: int):
    """Make the API call to OpenRouter with the cropped image."""
    import requests
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
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_data}"}},
                    {"type": "text", "text": get_vote_numbers_prompt()},
                ],
            }],
            "max_tokens": 1024,
        },
        timeout=timeout,
    )
    if response.status_code != 200:
        return None
    return response.json()


def _build_ballot_from_crop(vote_counts: dict, vote_details: dict, form_type: FormType, image_path: str, provenance_images: Optional[dict] = None) -> BallotData:
    """Build a BallotData object from extracted crop data."""
    total = sum(vote_counts.values())
    return BallotData(
        form_type=form_type.value,
        form_category="party_list" if form_type.is_party_list else "constituency",
        province="", constituency_number=0, district="", polling_unit=0,
        polling_station_id=f"Constituency-{form_type.value}",
        vote_counts=vote_counts, vote_details=vote_details,
        party_votes={}, party_details={},
        total_votes=total, valid_votes=total, invalid_votes=0, blank_votes=0,
        source_file=image_path, confidence_score=0.7,
        confidence_details={"level": "MEDIUM", "crop_based": True},
        provenance_images=provenance_images or {},
    )


def _extract_with_crops(image_path: str, form_type: FormType, api_key: str, model_id: str = _OPENROUTER_MODEL, base_url: str = "https://openrouter.ai/api/v1", timeout: int = 30) -> Optional[BallotData]:
    """Perform crop-aware extraction to reduce token costs and improve accuracy."""
    try:
        from crop_utils import crop_page_image, deskew_image, extract_vote_cells
        import base64
        
        region, _ = _get_crop_region(image_path, form_type)
        vote_crop_path = crop_page_image(image_path, region)
        
        # Apply OpenCV deskewing for better OCR alignment
        deskewed_path = deskew_image(vote_crop_path)
        
        # Note: cell_paths = extract_vote_cells(deskewed_path) 
        # is ready for Phase 2 (Local TrOCR) integration. For the VLM fallback, 
        # we pass the full deskewed column so it retains candidate number context.
        
        try:
            image_data = base64.b64encode(_preprocess_image(deskewed_path)).decode("utf-8")
            result = _call_crop_api(api_key, image_data, model_id, base_url, timeout)
            
            if not result:
                return None

            vote_data = json.loads(_strip_json_fences(result["choices"][0]["message"]["content"]))
            if not isinstance(vote_data, list) or len(vote_data) == 0:
                return None
                
            counts, details = {}, {}
            for entry in vote_data:
                pos, num, thai = entry.get("position", 0), entry.get("numeric", 0), entry.get("thai", "")
                if pos > 0:
                    counts[pos] = num
                    if thai: details[pos] = validate_vote_entry(num, thai)

            # Harvest persistent provenance
            from crop_utils import save_crop_persistently
            provenance = {
                "vote_column": save_crop_persistently(deskewed_path, image_path, "vote_column")
            }

            return _build_ballot_from_crop(counts, details, form_type, image_path, provenance_images=provenance)
        finally:
            _cleanup_paths([vote_crop_path, deskewed_path])
    except Exception as e:
        print(f"  Crop extraction failed: {e}")
    return None

def _cleanup_paths(paths: list[str]) -> None:
    """Helper to cleanly remove temporary files."""
    for p in set(paths):
        if p and os.path.exists(p):
            try:
                os.unlink(p)
            except Exception:
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


def _parse_party_votes(raw_votes: dict) -> tuple[dict, dict]:
    """Parse raw party-list vote data."""
    votes, details = {}, {}
    for party_num, vote_data in raw_votes.items():
        if vote_data is None:
            continue
        party_num = convert_thai_numerals(str(party_num))
        if isinstance(vote_data, dict):
            numeric = vote_data.get("numeric", 0)
            votes[str(party_num)] = numeric
            details[str(party_num)] = validate_vote_entry(numeric, vote_data.get("thai_text", ""))
        else:
            votes[str(party_num)] = int(vote_data)
    return votes, details


def _parse_candidate_votes(raw_votes: dict) -> tuple[dict, dict]:
    """Parse raw constituency candidate vote data."""
    votes, details = {}, {}
    for cand_num, vote_data in raw_votes.items():
        if vote_data is None:
            continue
        cand_num = convert_thai_numerals(str(cand_num))
        if isinstance(vote_data, dict):
            numeric = vote_data.get("numeric", 0)
            votes[int(cand_num)] = numeric
            details[int(cand_num)] = validate_vote_entry(numeric, vote_data.get("thai_text", ""))
        else:
            votes[int(cand_num)] = int(vote_data)
    return votes, details


def _parse_votes(data: dict, is_party_list: bool) -> tuple[dict, dict, dict, dict]:
    """Parse raw vote data into structured counts and details."""
    if is_party_list:
        p_votes, p_details = _parse_party_votes(data.get("party_votes", {}))
        return {}, {}, p_votes, p_details
    
    c_votes, c_details = _parse_candidate_votes(data.get("vote_counts", {}))
    return c_votes, c_details, {}, {}


def _validate_sums(calculated_sum: int, data: dict):
    """Log and validate vote sums and totals."""
    reported_valid = data.get("valid_votes", 0) or 0
    reported_invalid = data.get("invalid_votes", 0) or 0
    reported_blank = data.get("blank_votes", 0) or 0
    reported_total = data.get("total_votes", 0) or 0

    print(f"  Sum check: calculated={calculated_sum}, valid={reported_valid}, invalid={reported_invalid}, blank={reported_blank}, total={reported_total}")

    if reported_valid and calculated_sum != reported_valid:
        print(f"  WARNING: Sum != Valid votes! Sum: {calculated_sum}, Valid: {reported_valid}")
    elif reported_valid:
        print("  ✓ Sum matches valid votes")

    expected_total = reported_valid + reported_invalid + reported_blank
    if reported_total and reported_valid:
        if reported_total != expected_total:
            print(f"  WARNING: Total mismatch! Expected: {expected_total}, Reported: {reported_total}")
        else:
            print("  ✓ Total = Valid + Invalid + Blank")


def _validate_province_metadata(province_name: str):
    """Validate province name and print suggestions if invalid."""
    is_valid, canonical = ect_data.validate_province_name(province_name)
    if not is_valid:
        print(f"  WARNING: Province '{province_name}' not found")
        for prov in ect_data.list_provinces():
            if province_name in prov or prov in province_name:
                print(f"  SUGGESTION: Did you mean '{prov}'?")
                break
    else:
        print(f"  Province validated: {canonical}")
    return canonical if is_valid else province_name


def _enrich_candidate_metadata(province: str, constituency: int, counts: dict) -> dict:
    """Enrich candidate info for constituency ballots."""
    info = {}
    for pos, count in counts.items():
        candidate = ect_data.get_candidate_by_thai_province(province, constituency, pos)
        if candidate:
            party = ect_data.get_party_for_candidate(candidate)
            info[pos] = {
                "name": candidate.mp_app_name,
                "party_id": candidate.mp_app_party_id,
                "party_name": party.name if party else "Unknown",
                "party_abbr": party.abbr if party else ""
            }
            print(f"  Position {pos}: {candidate.mp_app_name} ({party.abbr if party else '?'}) - {count} votes")
        else:
            info[pos] = {"name": "Unknown", "party_id": None, "party_name": "Unknown", "party_abbr": ""}
    return info


def _enrich_party_metadata(votes: dict) -> dict:
    """Enrich party info for party-list ballots."""
    info = {}
    for party_num in votes.keys():
        party = ect_data.get_party(party_num)
        if party:
            info[str(party_num)] = {"name": party.name, "abbr": party.abbr, "color": party.color}
            print(f"  Party #{party_num}: {party.name} ({party.abbr})")
        else:
            info[str(party_num)] = {"name": "Unknown", "abbr": "", "color": ""}
    return info


def _enrich_metadata(is_party_list: bool, province: str, data: dict, votes: dict, p_votes: dict):
    """Enrich ballot data with ECT metadata."""
    if not ECT_AVAILABLE or not province:
        return {}, {}
        
    province = _validate_province_metadata(province)
    constituency = data.get("constituency_number", data.get("constituency", 0))
    
    if is_party_list:
        return {}, _enrich_party_metadata(p_votes)
        
    return _enrich_candidate_metadata(province, constituency, votes), {}


def _score_thai_text(vote_details: dict, party_details: dict) -> tuple[float, dict]:
    """Score confidence based on Thai text cross-validation."""
    all_details = vote_details or party_details
    if not all_details:
        return 0.0, {}
    validated_count = sum(1 for e in all_details.values() if e.is_validated)
    rate = validated_count / len(all_details)
    return rate * 0.4, {"weight": 0.4, "validated": validated_count, "total": len(all_details), "rate": rate, "score": rate * 0.4}


def _score_sums(calculated_sum: int, data: dict) -> tuple[float, dict]:
    """Score confidence based on sum consistency."""
    reported_valid = data.get("valid_votes", 0) or 0
    match = (calculated_sum == reported_valid) if reported_valid else False
    return (0.3 if match else 0.0), {"weight": 0.3, "match": match, "score": 0.3 if match else 0.0}


def _score_geography(province: str, data: dict) -> tuple[float, dict]:
    """Score confidence based on geographic metadata completion."""
    points = 0.0
    if province: points += 0.1
    if data.get("constituency_number") or data.get("constituency"): points += 0.1
    if data.get("district"): points += 0.1
    return points, {"weight": 0.3, "province": bool(province), "constituency": bool(data.get("constituency")), "district": bool(data.get("district")), "score": points}


def _calculate_confidence(vote_details: dict, party_details: dict, calculated_sum: int, data: dict, province: str) -> tuple[float, dict]:
    """Calculate extraction confidence score based on various factors."""
    score = 0.0
    details = {}
    
    s_thai, d_thai = _score_thai_text(vote_details, party_details)
    score += s_thai
    details["thai_text_validation"] = d_thai
    
    s_sum, d_sum = _score_sums(calculated_sum, data)
    score += s_sum
    details["sum_validation"] = d_sum
    
    s_geo, d_geo = _score_geography(province, data)
    score += s_geo
    details["geography_validation"] = d_geo
    
    if score >= 0.8: level = "HIGH"
    elif score >= 0.5: level = "MEDIUM"
    else: level = "LOW"
    details["level"] = level
    
    return score, details


def _get_form_identifier(form_type: Optional[FormType], is_party_list: bool, data: dict) -> str:
    """Determine the simplified form identifier (e.g. 5/17 BCH)."""
    raw_code = data.get("form_code", data.get("form_type", "5/17"))
    code = "5/17"
    for c in ["5/16", "5/17", "5/18"]:
        if c in str(raw_code):
            code = c
            break
            
    output = str(form_type.value) if form_type else data.get("form_type", f"ส.ส. {code}")
    if is_party_list and "(บช)" not in output:
        output += " (บช)"
    return output


def _get_polling_station_id(province: str, data: dict) -> str:
    """Construct a descriptive polling station ID."""
    constituency = data.get("constituency_number", data.get("constituency", 0))
    station_id = f"{province}-เขต {constituency}"
    district = data.get("district", "")
    if district:
        station_id += f" {district}"
    polling_unit = data.get("polling_unit", 0)
    if polling_unit:
        station_id += f"-{polling_unit}"
    return station_id


def process_extracted_data(data: dict, image_path: str, form_type: Optional[FormType] = None) -> Optional[BallotData]:
    """Process extracted data into a BallotData object with validation."""
    try:
        is_party_list = form_type.is_party_list if form_type else data.get("is_party_list", False)
        
        # 1. Parse votes
        counts, details, p_votes, p_details = _parse_votes(data, is_party_list)
        calc_sum = sum(counts.values()) if counts else sum(p_votes.values())

        # 2. Validation and Enrichment
        _validate_sums(calc_sum, data)
        province = data.get("province", "")
        cand_info, p_info = _enrich_metadata(is_party_list, province, data, counts, p_votes)

        # 3. Metadata and Identity
        form_id = _get_form_identifier(form_type, is_party_list, data)
        station_id = _get_polling_station_id(province, data)

        # 4. Confidence
        score, c_details = _calculate_confidence(details, p_details, calc_sum, data, province)
        print(f"  Confidence: {c_details['level']} ({score:.1%})")

        return BallotData(
            form_type=form_id,
            form_category="party_list" if is_party_list else "constituency",
            province=province,
            constituency_number=data.get("constituency_number", data.get("constituency", 0)),
            district=data.get("district", ""),
            polling_unit=data.get("polling_unit", 0),
            page_parties=data.get("page_parties", data.get("page_info", "")),
            polling_station_id=station_id,
            vote_counts=counts,
            vote_details=details,
            party_votes=p_votes,
            party_details=p_details,
            candidate_info=cand_info,
            party_info=p_info,
            total_votes=data.get("total_votes", 0) or calc_sum,
            valid_votes=data.get("valid_votes", 0) or calc_sum,
            invalid_votes=data.get("invalid_votes", 0),
            blank_votes=data.get("blank_votes", 0),
            source_file=str(image_path),
            confidence_score=score,
            confidence_details=c_details,
        )

    except Exception as e:
        print(f"Error processing extracted data: {e}")
        return None
