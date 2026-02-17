#!/usr/bin/env python3
"""
Ballot OCR for Thai election verification.

Strategy:
- Extract vote counts by candidate POSITION (not name)
- Extract polling station identifiers
- Match against ECT API data which has candidate names
- Validate using: (1) numeric vs Thai text, (2) sum validation, (3) ECT reference data

This avoids the problem of AI hallucinating candidate names from handwritten Thai.

Form Types (6 total):
1. ส.ส. 5/16 - Early voting, constituency (แบ่งเขตเลือกตั้ง)
2. ส.ส. 5/16 (บช) - Early voting, party-list (บัญชีรายชื่อ)
3. ส.ส. 5/17 - Out-of-district, constituency (แบ่งเขตเลือกตั้ง)
4. ส.ส. 5/17 (บช) - Out-of-district, party-list (บัญชีรายชื่อ)
5. ส.ส. 5/18 - Vote counting by unit, constituency (แบ่งเขตเลือกตั้ง)
6. ส.ส. 5/18 (บช) - Vote counting by unit, party-list (บัญชีรายชื่อ)
"""

import os
import sys
import json
import subprocess
import base64
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from batch_processor import BatchResult
from enum import Enum
from datetime import datetime
from io import StringIO

try:
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak, Image
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    from reportlab.graphics.shapes import Drawing, Rect, String
    from reportlab.graphics.charts.barcharts import VerticalBarChart, HorizontalBarChart
    from reportlab.graphics.charts.piecharts import Pie
    from reportlab.graphics import renderPDF
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False

# Import ECT API for validation
try:
    from ect_api import ect_data
    ECT_AVAILABLE = True
except ImportError:
    ECT_AVAILABLE = False


class FormType(Enum):
    """Thai election ballot form types."""
    # Early voting (ลงคะแนนก่อนวันเลือกตั้ง)
    S5_16 = "ส.ส. 5/16"           # Early voting, constituency
    S5_16_BCH = "ส.ส. 5/16 (บช)"  # Early voting, party-list

    # Out-of-district and overseas (นอกเขตเลือกตั้งและนอกราชอาณาจักร)
    S5_17 = "ส.ส. 5/17"           # Out-of-district, constituency
    S5_17_BCH = "ส.ส. 5/17 (บช)"  # Out-of-district, party-list

    # By polling unit (รายหน่วย)
    S5_18 = "ส.ส. 5/18"           # By unit, constituency
    S5_18_BCH = "ส.ส. 5/18 (บช)"  # By unit, party-list

    @property
    def is_party_list(self) -> bool:
        """Check if this is a party-list (บัญชีรายชื่อ) form."""
        return self in (FormType.S5_16_BCH, FormType.S5_17_BCH, FormType.S5_18_BCH)

    @property
    def expected_candidates(self) -> int:
        """Expected number of candidates/parties."""
        return 57 if self.is_party_list else 6  # 57 parties, or ~6 constituency candidates


# Thai numeral to Arabic numeral mapping
THAI_NUMERALS = {
    "๐": "0", "๑": "1", "๒": "2", "๓": "3", "๔": "4",
    "๕": "5", "๖": "6", "๗": "7", "๘": "8", "๙": "9",
}


def convert_thai_numerals(text: str) -> str:
    """Convert Thai numerals (๐๑๒๓๔๕๖๗๘๙) to Arabic numerals (0123456789)."""
    result = text
    for thai, arabic in THAI_NUMERALS.items():
        result = result.replace(thai, arabic)
    return result


# Thai number word mappings
THAI_DIGITS = {
    "ศูนย์": 0, "หนึ่ง": 1, "สอง": 2, "สาม": 3, "สี่": 4,
    "ห้า": 5, "หก": 6, "เจ็ด": 7, "แปด": 8, "เก้า": 9,
}
THAI_TENS = {
    "สิบ": 10, "ยี่สิบ": 20, "สามสิบ": 30, "สี่สิบ": 40, "ห้าสิบ": 50,
    "หกสิบ": 60, "เจ็ดสิบ": 70, "แปดสิบ": 80, "เก้าสิบ": 90,
}
THAI_HUNDREDS = {
    "ร้อย": 100, "สองร้อย": 200, "สามร้อย": 300, "สี่ร้อย": 400, "ห้าร้อย": 500,
    "หกร้อย": 600, "เจ็ดร้อย": 700, "แปดร้อย": 800, "เก้าร้อย": 900,
}
THAI_THOUSANDS = {
    "พัน": 1000, "สองพัน": 2000, "สามพัน": 3000, "สี่พัน": 4000, "ห้าพัน": 5000,
    "หกพัน": 6000, "เจ็ดพัน": 7000, "แปดพัน": 8000, "เก้าพัน": 9000,
}
THAI_SUFFIXES = {
    "ร้อย": 100,
    "พัน": 1000,
    "หมื่น": 10000,
    "แสน": 100000,
    "ล้าน": 1000000,
}


def thai_text_to_number(thai_text: str) -> Optional[int]:
    """
    Convert Thai number text to integer.
    Examples: "หนึ่งร้อยห้าสิบสี่" -> 154, "สี่ร้อยยี่สิบสี่" -> 424
    """
    if not thai_text:
        return None

    thai_text = thai_text.strip()

    # Check for exact matches first
    if thai_text in THAI_DIGITS:
        return THAI_DIGITS[thai_text]
    if thai_text in THAI_TENS:
        return THAI_TENS[thai_text]
    if thai_text in THAI_HUNDREDS:
        return THAI_HUNDREDS[thai_text]
    if thai_text in THAI_THOUSANDS:
        return THAI_THOUSANDS[thai_text]

    # Parse compound numbers
    result = 0
    remaining = thai_text

    # Handle thousands
    for thai_word, value in sorted(THAI_THOUSANDS.items(), key=lambda x: -len(x[0])):
        if remaining.startswith(thai_word.replace("สอง", "").replace("สาม", "").replace("สี่", "").replace("ห้า", "").replace("หก", "").replace("เจ็ด", "").replace("แปด", "").replace("เก้า", "")):
            # Check for prefix digit
            for digit_thai, digit_val in THAI_DIGITS.items():
                prefix = digit_thai + "พัน"
                if remaining.startswith(prefix):
                    result += digit_val * 1000
                    remaining = remaining[len(prefix):]
                    break
            else:
                if remaining.startswith("พัน"):
                    result += 1000
                    remaining = remaining[3:]
            break

    # Handle hundreds
    for digit_thai, digit_val in [("หนึ่ง", 1), ("สอง", 2), ("สาม", 3), ("สี่", 4), ("ห้า", 5), ("หก", 6), ("เจ็ด", 7), ("แปด", 8), ("เก้า", 9)]:
        prefix = digit_thai + "ร้อย"
        if remaining.startswith(prefix):
            result += digit_val * 100
            remaining = remaining[len(prefix):]
            break
    else:
        if remaining.startswith("ร้อย"):
            result += 100
            remaining = remaining[3:]

    # Handle tens (special case for "ยี่สิบ" = 20)
    if remaining.startswith("ยี่สิบ"):
        result += 20
        remaining = remaining[6:]
    else:
        for digit_thai, digit_val in [("สาม", 3), ("สี่", 4), ("ห้า", 5), ("หก", 6), ("เจ็ด", 7), ("แปด", 8), ("เก้า", 9)]:
            prefix = digit_thai + "สิบ"
            if remaining.startswith(prefix):
                result += digit_val * 10
                remaining = remaining[len(prefix):]
                break
        else:
            if remaining.startswith("สิบ"):
                result += 10
                remaining = remaining[3:]

    # Handle units (remaining digit)
    for digit_thai, digit_val in THAI_DIGITS.items():
        if remaining == digit_thai:
            result += digit_val
            break
        # Special case: "เอ็ด" means 1 at the end (e.g., ยี่สิบเอ็ด = 21)
        if remaining == "เอ็ด":
            result += 1
            break

    return result if result > 0 else None


def validate_vote_entry(numeric: int, thai_text: str) -> "VoteEntry":
    """Create a VoteEntry with validation of numeric vs Thai text."""
    thai_value = thai_text_to_number(thai_text)
    is_validated = thai_value is not None and thai_value == numeric
    return VoteEntry(
        numeric=numeric,
        thai_text=thai_text,
        is_validated=is_validated
    )


@dataclass
class VoteEntry:
    """A single vote count entry with dual representation."""
    numeric: int  # Numeric vote count
    thai_text: str  # Thai text representation (e.g., "หนึ่งร้อยห้าสิบสี่")
    is_validated: bool  # True if numeric matches Thai text interpretation


@dataclass
class BallotData:
    """Extracted ballot data."""
    form_type: str  # e.g., "ส.ส. 5/17"
    form_category: str  # "constituency" or "party_list"
    province: str
    constituency_number: int = 0
    district: str = ""
    polling_unit: int = 0
    page_parties: str = ""  # For party-list: which parties on this page (e.g., "1-20")
    polling_station_id: str = ""
    vote_counts: dict[int, int] = field(default_factory=dict)  # candidate_number -> vote_count
    vote_details: dict[int, VoteEntry] = field(default_factory=dict)  # candidate_number -> VoteEntry (with Thai text)
    party_votes: dict[str, int] = field(default_factory=dict)  # party_number -> vote_count
    party_details: dict[str, VoteEntry] = field(default_factory=dict)  # party_number -> VoteEntry
    candidate_info: dict[int, dict] = field(default_factory=dict)  # candidate_number -> {name, party}
    party_info: dict[str, dict] = field(default_factory=dict)  # party_number -> {name, abbr}
    total_votes: int = 0
    valid_votes: int = 0
    invalid_votes: int = 0
    blank_votes: int = 0  # บัตรไม่ประสงค์ลงคะแนน
    source_file: str = ""
    confidence_score: float = 0.0  # 0.0 to 1.0
    confidence_details: dict = field(default_factory=dict)  # Breakdown of confidence factors


@dataclass
class AggregatedResults:
    """Aggregated results for a constituency from multiple polling stations."""
    province: str
    constituency: str  # District/name
    constituency_no: int
    
    # Vote aggregation
    candidate_totals: dict[int, int] = field(default_factory=dict)  # position -> total votes
    party_totals: dict[str, int] = field(default_factory=dict)  # party # -> total votes
    candidate_info: dict[int, dict] = field(default_factory=dict)  # position -> {name, party_abbr, votes}
    party_info: dict[str, dict] = field(default_factory=dict)  # party # -> {name, abbr, votes}
    
    # Polling information
    polling_units_reporting: int = 0  # How many units provided data
    total_polling_units: int = 0  # Expected total units
    valid_votes_total: int = 0
    invalid_votes_total: int = 0
    blank_votes_total: int = 0
    overall_total: int = 0
    
    # Quality metrics
    aggregated_confidence: float = 0.0
    ballots_processed: int = 0
    ballots_with_discrepancies: int = 0
    
    # Winners (highest votes per position)
    winners: list[dict] = field(default_factory=list)  # [{position, name, party, votes, percentage}, ...]
    turnout_rate: float = 0.0
    discrepancy_rate: float = 0.0
    
    # Source tracking
    source_ballots: list[str] = field(default_factory=list)  # List of source file names
    form_types: list[str] = field(default_factory=list)  # Form types used


def pdf_to_images(pdf_path: str, output_dir: str, dpi: int = 150) -> list[str]:
    """
    Convert PDF to PNG images using pdftoppm.

    Args:
        pdf_path: Path to the PDF file
        output_dir: Directory to save output images
        dpi: Resolution for conversion (default 150)

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

        response_text = message.content[0].text.strip()
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]

        data = json.loads(response_text)
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

CRITICAL: Look at EACH handwritten digit individually. Read the COMPLETE number.

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
}"""


def extract_ballot_data_with_ai(image_path: str, form_type: Optional[FormType] = None) -> Optional[BallotData]:
    """
    Use OpenRouter with Gemma 3 12B IT to extract ballot data from an image.

    IMPORTANT: We extract vote counts BY POSITION, not by name.
    AI vision often hallucinates handwritten names, but numbers are easier to read.
    """
    import os
    import requests

    # Read and encode image
    with open(image_path, "rb") as f:
        image_data = base64.b64encode(f.read()).decode("utf-8")

    # Check for OpenRouter API key
    openrouter_api_key = os.environ.get("OPENROUTER_API_KEY")

    if openrouter_api_key:
        try:
            print("  Using OpenRouter with Gemma 3 12B IT...")

            # Use appropriate prompt based on form type
            if form_type is not None:
                if form_type.is_party_list:
                    prompt = get_party_list_prompt()
                else:
                    prompt = get_constituency_prompt()
            else:
                # Combined prompt for auto-detection
                prompt = get_combined_prompt()

            # OpenRouter API call (OpenAI-compatible)
            response = requests.post(
                url="https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {openrouter_api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://github.com/election-verification",  # Optional
                    "X-Title": "Thai Election Ballot OCR"  # Optional
                },
                json={
                    "model": "google/gemma-3-12b-it:free",
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/png;base64,{image_data}"
                                    }
                                },
                                {
                                    "type": "text",
                                    "text": prompt
                                }
                            ]
                        }
                    ],
                    "max_tokens": 2048
                },
                timeout=60  # 60 second timeout
            )

            if response.status_code == 200:
                result = response.json()
                response_text = result["choices"][0]["message"]["content"]
                print(f"  Gemma 3 response received ({len(response_text)} chars)")

                # Parse JSON from response
                if "```json" in response_text:
                    response_text = response_text.split("```json")[1].split("```")[0]
                elif "```" in response_text:
                    response_text = response_text.split("```")[1].split("```")[0]

                data = json.loads(response_text.strip())
                return process_extracted_data(data, image_path, form_type)
            else:
                print(f"  OpenRouter error: {response.status_code} - {response.text}")
                print("  Falling back to Claude Vision...")

        except Exception as e:
            print(f"  OpenRouter failed: {e}")
            print("  Falling back to Claude Vision...")

    # Fallback to Claude Vision
    return extract_with_claude_vision(image_path, form_type)


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
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0]
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0]

        data = json.loads(response_text.strip())

        # Process the data (same logic as before)
        return process_extracted_data(data, image_path, form_type)

    except Exception as e:
        print(f"  Error parsing OCR text: {e}")
        return None


def extract_with_claude_vision(image_path: str, form_type: Optional[FormType] = None) -> Optional[BallotData]:
    """Fallback to Claude Vision for extraction."""
    import anthropic

    client = anthropic.Anthropic()

    with open(image_path, "rb") as f:
        image_data = base64.b64encode(f.read()).decode("utf-8")

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
            model="claude-sonnet-4-20250514",
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
        # Extract JSON from response (handle markdown code blocks)
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0]
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0]

        data = json.loads(response_text.strip())

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


def detect_discrepancies(extracted_data: BallotData, official_data: Optional[dict] = None) -> dict:
    """
    Detect discrepancies between extracted ballot data and official ECT results.
    
    Args:
        extracted_data: BallotData object with extracted votes
        official_data: Optional dict with official vote counts from ECT
        
    Returns:
        Dictionary with discrepancy report
    """
    report = {
        "form_type": extracted_data.form_type,
        "polling_station": extracted_data.polling_station_id,
        "extracted_total": extracted_data.valid_votes,
        "official_total": official_data.get("total", 0) if official_data else None,
        "discrepancies": [],
        "summary": {
            "high_severity": 0,
            "medium_severity": 0,
            "low_severity": 0,
            "matches": 0
        }
    }
    
    # If no official data, return empty report
    if not official_data:
        report["status"] = "pending_official_data"
        return report
    
    # Determine form type and compare accordingly
    if extracted_data.form_category == "party_list":
        # Compare party votes
        official_votes = official_data.get("party_votes", {})
        for party_num_str, extracted_votes in extracted_data.party_votes.items():
            party_num = int(party_num_str)
            official_votes_count = official_votes.get(party_num, 0)
            
            if extracted_votes == official_votes_count:
                report["summary"]["matches"] += 1
            else:
                variance = abs(extracted_votes - official_votes_count)
                variance_pct = (variance / official_votes_count * 100) if official_votes_count > 0 else 100.0
                
                # Determine severity
                if variance_pct > 10:
                    severity = "HIGH"
                    report["summary"]["high_severity"] += 1
                elif variance_pct > 5:
                    severity = "MEDIUM"
                    report["summary"]["medium_severity"] += 1
                else:
                    severity = "LOW"
                    report["summary"]["low_severity"] += 1
                
                # Get party name if available
                party_info = extracted_data.party_info.get(party_num_str, {})
                party_name = party_info.get("name", f"Party #{party_num_str}")
                party_abbr = party_info.get("abbr", "")
                
                report["discrepancies"].append({
                    "type": "party_vote",
                    "party_number": party_num,
                    "party_name": party_name,
                    "party_abbr": party_abbr,
                    "extracted": extracted_votes,
                    "official": official_votes_count,
                    "variance": variance,
                    "variance_pct": f"{variance_pct:.1f}%",
                    "severity": severity
                })
    else:
        # Compare constituency votes
        official_votes = official_data.get("vote_counts", {})
        for position, extracted_votes in extracted_data.vote_counts.items():
            official_votes_count = official_votes.get(position, 0)
            
            if extracted_votes == official_votes_count:
                report["summary"]["matches"] += 1
            else:
                variance = abs(extracted_votes - official_votes_count)
                variance_pct = (variance / official_votes_count * 100) if official_votes_count > 0 else 100.0
                
                # Determine severity
                if variance_pct > 10:
                    severity = "HIGH"
                    report["summary"]["high_severity"] += 1
                elif variance_pct > 5:
                    severity = "MEDIUM"
                    report["summary"]["medium_severity"] += 1
                else:
                    severity = "LOW"
                    report["summary"]["low_severity"] += 1
                
                # Get candidate name if available
                candidate_info = extracted_data.candidate_info.get(position, {})
                candidate_name = candidate_info.get("name", f"Position #{position}")
                
                report["discrepancies"].append({
                    "type": "candidate_vote",
                    "position": position,
                    "candidate_name": candidate_name,
                    "extracted": extracted_votes,
                    "official": official_votes_count,
                    "variance": variance,
                    "variance_pct": f"{variance_pct:.1f}%",
                    "severity": severity
                })
    
    # Overall status
    if report["summary"]["high_severity"] > 0:
        report["status"] = "discrepancies_found_high"
    elif report["summary"]["medium_severity"] > 0:
        report["status"] = "discrepancies_found_medium"
    elif report["summary"]["low_severity"] > 0:
        report["status"] = "discrepancies_found_low"
    else:
        report["status"] = "verified"
    
    return report


def format_discrepancy_report(discrepancy_report: dict) -> str:
    """
    Format a discrepancy report as human-readable text.
    
    Args:
        discrepancy_report: Report dict from detect_discrepancies()
        
    Returns:
        Formatted report string
    """
    lines = []
    lines.append("=" * 70)
    lines.append("BALLOT VERIFICATION REPORT")
    lines.append("=" * 70)
    
    lines.append(f"\nForm Type: {discrepancy_report['form_type']}")
    lines.append(f"Polling Station: {discrepancy_report['polling_station']}")
    
    # Status with emoji
    status = discrepancy_report.get('status', 'unknown')
    status_emoji = {
        'verified': '✓',
        'discrepancies_found_low': '⚠',
        'discrepancies_found_medium': '⚠⚠',
        'discrepancies_found_high': '✗',
        'pending_official_data': '?'
    }.get(status, '?')
    
    status_text = {
        'verified': 'VERIFIED - No discrepancies',
        'discrepancies_found_low': 'LOW SEVERITY discrepancies found',
        'discrepancies_found_medium': 'MEDIUM SEVERITY discrepancies found',
        'discrepancies_found_high': 'HIGH SEVERITY discrepancies found',
        'pending_official_data': 'Waiting for official results'
    }.get(status, 'Unknown status')
    
    lines.append(f"\nStatus: {status_emoji} {status_text}")
    
    # Summary
    summary = discrepancy_report['summary']
    lines.append("\nVerification Summary:")
    lines.append(f"  Verified matches: {summary['matches']}")
    lines.append(f"  Low severity issues: {summary['low_severity']}")
    lines.append(f"  Medium severity issues: {summary['medium_severity']}")
    lines.append(f"  High severity issues: {summary['high_severity']}")
    
    # Discrepancies
    if discrepancy_report['discrepancies']:
        lines.append(f"\nDiscrepancies Detected ({len(discrepancy_report['discrepancies'])} items):")
        lines.append("-" * 70)
        
        for disc in discrepancy_report['discrepancies']:
            if disc['type'] == 'candidate_vote':
                lines.append(f"\nPosition {disc['position']}: {disc['candidate_name']}")
            else:
                lines.append(f"\nParty #{disc['party_number']}: {disc['party_name']} ({disc['party_abbr']})")
            
            lines.append(f"  Extracted: {disc['extracted']} votes")
            lines.append(f"  Official:  {disc['official']} votes")
            lines.append(f"  Variance:  {disc['variance']} votes ({disc['variance_pct']})")
            lines.append(f"  Severity:  {disc['severity']}")
    else:
        lines.append("\n✓ All votes verified successfully!")
    
    lines.append("\n" + "=" * 70)
    
    return "\n".join(lines)


def generate_single_ballot_report(ballot_data: BallotData, discrepancy_report: Optional[dict] = None) -> str:
    """
    Generate a comprehensive markdown report for a single ballot.
    
    Args:
        ballot_data: BallotData object with extraction results
        discrepancy_report: Optional discrepancy report from detect_discrepancies()
        
    Returns:
        Formatted markdown report string
    """
    from datetime import datetime
    
    lines = []
    lines.append("# Ballot Verification Report")
    lines.append("")
    lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    
    # Header section
    lines.append("## Form Information")
    lines.append("")
    lines.append("| Field | Value |")
    lines.append("|-------|-------|")
    lines.append(f"| Form Type | {ballot_data.form_type} |")
    lines.append(f"| Category | {ballot_data.form_category.title()} |")
    lines.append(f"| Province | {ballot_data.province} |")
    lines.append(f"| Constituency | {ballot_data.constituency_number} |")
    lines.append(f"| District | {ballot_data.district} |")
    lines.append(f"| Polling Unit | {ballot_data.polling_unit} |")
    lines.append(f"| Polling Station | {ballot_data.polling_station_id} |")
    lines.append("")
    
    # Vote totals
    lines.append("## Vote Summary")
    lines.append("")
    lines.append("| Metric | Count |")
    lines.append("|--------|-------|")
    lines.append(f"| Valid Votes | {ballot_data.valid_votes} |")
    lines.append(f"| Invalid Votes | {ballot_data.invalid_votes} |")
    lines.append(f"| Blank Votes | {ballot_data.blank_votes} |")
    lines.append(f"| **Total Votes** | **{ballot_data.total_votes}** |")
    lines.append("")
    
    # Extraction quality
    lines.append("## Extraction Quality")
    lines.append("")
    confidence_level = ballot_data.confidence_details.get("level", "UNKNOWN")
    confidence_score = ballot_data.confidence_score
    
    # Confidence level emoji
    confidence_emoji = {
        "HIGH": "✓",
        "MEDIUM": "⚠",
        "LOW": "⚠",
        "VERY_LOW": "✗"
    }.get(confidence_level, "?")
    
    lines.append(f"**Confidence Level:** {confidence_emoji} {confidence_level} ({confidence_score:.1%})")
    lines.append("")
    
    # Confidence factors
    confidence_details = ballot_data.confidence_details
    if "thai_text_validation" in confidence_details:
        val = confidence_details["thai_text_validation"]
        lines.append(f"- Thai Text Validation: {val['validated']}/{val['total']} ({val['rate']:.1%})")
    
    if "sum_validation" in confidence_details:
        val = confidence_details["sum_validation"]
        match_status = "✓ Matched" if val["match"] else "✗ Mismatch"
        lines.append(f"- Sum Validation: {match_status} (calculated={val['calculated_sum']}, reported={val['reported_valid']})")
    
    if "province_validation" in confidence_details:
        val = confidence_details["province_validation"]
        valid_status = "✓ Valid" if val["valid"] else "✗ Invalid"
        lines.append(f"- Province Validation: {valid_status} ({val['province']})")
    
    lines.append("")
    
    # Votes breakdown
    if ballot_data.form_category == "party_list":
        lines.append("## Party Votes")
        lines.append("")
        if ballot_data.party_votes:
            lines.append("| Party # | Party Name | Abbr | Votes |")
            lines.append("|---------|-----------|------|-------|")
            for party_num_str in sorted(ballot_data.party_votes.keys(), key=lambda x: int(x)):
                votes = ballot_data.party_votes[party_num_str]
                party_info = ballot_data.party_info.get(party_num_str, {})
                party_name = party_info.get("name", "Unknown")
                party_abbr = party_info.get("abbr", "")
                lines.append(f"| {party_num_str} | {party_name} | {party_abbr} | {votes} |")
        lines.append("")
        if ballot_data.page_parties:
            lines.append(f"**Page Parties:** {ballot_data.page_parties}")
            lines.append("")
    else:
        lines.append("## Candidate Votes")
        lines.append("")
        if ballot_data.vote_counts:
            lines.append("| Pos | Candidate Name | Party | Votes |")
            lines.append("|-----|----------------|-------|-------|")
            for position in sorted(ballot_data.vote_counts.keys()):
                votes = ballot_data.vote_counts[position]
                candidate_info = ballot_data.candidate_info.get(position, {})
                candidate_name = candidate_info.get("name", "Unknown")
                party_abbr = candidate_info.get("party_abbr", "")
                lines.append(f"| {position} | {candidate_name} | {party_abbr} | {votes} |")
        lines.append("")
    
    # Discrepancy section
    if discrepancy_report:
        lines.append("## Verification Results")
        lines.append("")
        
        status = discrepancy_report.get("status", "unknown")
        status_emoji = {
            "verified": "✓",
            "discrepancies_found_low": "⚠",
            "discrepancies_found_medium": "⚠⚠",
            "discrepancies_found_high": "✗",
            "pending_ect_data": "?",
            "pending_official_data": "?"
        }.get(status, "?")
        
        status_text = {
            "verified": "VERIFIED - No discrepancies",
            "discrepancies_found_low": "LOW SEVERITY discrepancies found",
            "discrepancies_found_medium": "MEDIUM SEVERITY discrepancies found",
            "discrepancies_found_high": "HIGH SEVERITY discrepancies found",
            "pending_ect_data": "ECT reference unavailable",
            "pending_official_data": "Waiting for official results"
        }.get(status, "Unknown status")
        
        lines.append(f"**Status:** {status_emoji} {status_text}")
        lines.append("")
        
        summary = discrepancy_report["summary"]
        lines.append("**Summary:**")
        lines.append(f"- Verified matches: {summary['matches']}")
        lines.append(f"- Low severity issues: {summary['low_severity']}")
        lines.append(f"- Medium severity issues: {summary['medium_severity']}")
        lines.append(f"- High severity issues: {summary['high_severity']}")
        lines.append("")
        
        if discrepancy_report["discrepancies"]:
            lines.append("### Discrepancies Detected")
            lines.append("")
            lines.append("| Item | Extracted | Official | Variance | Severity |")
            lines.append("|------|-----------|----------|----------|----------|")
            
            for disc in discrepancy_report["discrepancies"]:
                if disc["type"] == "candidate_vote":
                    item = f"Pos {disc['position']}: {disc['candidate_name']}"
                    extracted = disc.get("extracted", "")
                    official = disc.get("official", "")
                    variance = disc.get("variance_pct", "")
                elif disc["type"] == "party_vote":
                    item = f"Party #{disc['party_number']}: {disc['party_name']}"
                    extracted = disc.get("extracted", "")
                    official = disc.get("official", "")
                    variance = disc.get("variance_pct", "")
                else:
                    item = disc["type"]
                    extracted = disc.get("extracted", disc.get("position", disc.get("party_number", "")))
                    official = disc.get("official", disc.get("expected", ""))
                    variance = disc.get("variance_pct", "N/A")
                
                lines.append(f"| {item} | {extracted} | {official} | {variance} | {disc.get('severity', '')} |")
            
            lines.append("")
    
    # Footer
    lines.append("---")
    lines.append(f"*Source File:* {ballot_data.source_file}")
    lines.append("")
    
    return "\n".join(lines)


def generate_batch_report(results: list[dict], ballot_data_list: list[BallotData]) -> str:
    """
    Generate a summary report for a batch of ballots.
    
    Args:
        results: List of discrepancy report dicts
        ballot_data_list: List of BallotData objects
        
    Returns:
        Formatted markdown report string
    """
    from datetime import datetime
    
    lines = []
    lines.append("# Batch Ballot Verification Report")
    lines.append("")
    lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    
    # Overall statistics
    total_ballots = len(results)
    verified = sum(1 for r in results if r.get("status") == "verified")
    low_severity = sum(1 for r in results if r.get("status") == "discrepancies_found_low")
    medium_severity = sum(1 for r in results if r.get("status") == "discrepancies_found_medium")
    high_severity = sum(1 for r in results if r.get("status") == "discrepancies_found_high")
    
    accuracy_rate = (verified / total_ballots * 100) if total_ballots > 0 else 0
    
    lines.append("## Overall Statistics")
    lines.append("")
    lines.append("| Metric | Count | Percentage |")
    lines.append("|--------|-------|-----------|")
    lines.append(f"| Total Ballots | {total_ballots} | 100% |")
    lines.append(f"| Verified (No Issues) | {verified} | {verified/total_ballots*100:.1f}% |")
    lines.append(f"| Low Severity Issues | {low_severity} | {low_severity/total_ballots*100:.1f}% |")
    lines.append(f"| Medium Severity Issues | {medium_severity} | {medium_severity/total_ballots*100:.1f}% |")
    lines.append(f"| High Severity Issues | {high_severity} | {high_severity/total_ballots*100:.1f}% |")
    lines.append("")
    
    # Accuracy indicator
    if accuracy_rate >= 95:
        accuracy_emoji = "✓✓✓"
        accuracy_text = "Excellent"
    elif accuracy_rate >= 90:
        accuracy_emoji = "✓✓"
        accuracy_text = "Good"
    elif accuracy_rate >= 80:
        accuracy_emoji = "✓"
        accuracy_text = "Acceptable"
    else:
        accuracy_emoji = "✗"
        accuracy_text = "Poor"
    
    lines.append(f"**Verification Accuracy:** {accuracy_emoji} {accuracy_text} ({accuracy_rate:.1f}%)")
    lines.append("")
    
    # Form type breakdown
    if ballot_data_list:
        form_types = {}
        constituencies = {}
        provinces = {}
        
        for ballot in ballot_data_list:
            form_type = ballot.form_type
            form_types[form_type] = form_types.get(form_type, 0) + 1
            
            if ballot.constituency_number:
                cons_key = f"{ballot.province} - Constituency {ballot.constituency_number}"
                constituencies[cons_key] = constituencies.get(cons_key, 0) + 1
            
            if ballot.province:
                provinces[ballot.province] = provinces.get(ballot.province, 0) + 1
        
        if form_types:
            lines.append("## Form Type Breakdown")
            lines.append("")
            lines.append("| Form Type | Count |")
            lines.append("|-----------|-------|")
            for form_type, count in sorted(form_types.items()):
                lines.append(f"| {form_type} | {count} |")
            lines.append("")
        
        if provinces:
            lines.append("## Province Breakdown")
            lines.append("")
            lines.append("| Province | Count |")
            lines.append("|----------|-------|")
            for province, count in sorted(provinces.items()):
                lines.append(f"| {province} | {count} |")
            lines.append("")
    
    # High severity issues summary
    high_severity_items = []
    for i, result in enumerate(results):
        if result.get("status") == "discrepancies_found_high":
            for disc in result.get("discrepancies", []):
                if disc.get("severity") == "HIGH":
                    high_severity_items.append({
                        "ballot_index": i,
                        "station": result.get("polling_station", "Unknown"),
                        "discrepancy": disc
                    })
    
    if high_severity_items:
        lines.append("## High Severity Issues")
        lines.append("")
        lines.append(f"> **⚠ {len(high_severity_items)} high-severity discrepancies detected across batch**")
        lines.append("")
        lines.append("| Polling Station | Item | Extracted | Official | Variance |")
        lines.append("|-----------------|------|-----------|----------|----------|")
        for item in high_severity_items[:10]:  # Show top 10
            disc = item["discrepancy"]
            if disc["type"] == "candidate_vote":
                item_name = f"Pos {disc['position']}: {disc['candidate_name']}"
                extracted = disc.get("extracted", "")
                official = disc.get("official", "")
                variance = disc.get("variance_pct", "")
            elif disc["type"] == "party_vote":
                item_name = f"Party #{disc['party_number']}: {disc['party_name']}"
                extracted = disc.get("extracted", "")
                official = disc.get("official", "")
                variance = disc.get("variance_pct", "")
            else:
                item_name = disc["type"]
                extracted = disc.get("extracted", disc.get("position", disc.get("party_number", "")))
                official = disc.get("official", disc.get("expected", ""))
                variance = disc.get("variance_pct", "N/A")
            
            lines.append(f"| {item['station']} | {item_name} | {extracted} | {official} | {variance} |")
        
        if len(high_severity_items) > 10:
            lines.append(f"| ... | *{len(high_severity_items) - 10} more issues* | | | |")
        
        lines.append("")
    
    # Recommendations
    lines.append("## Recommendations")
    lines.append("")
    if high_severity > 0:
        lines.append("⚠ **Manual Review Required**")
        lines.append("")
        lines.append(f"- {high_severity} ballot(s) with high-severity discrepancies")
        lines.append("- Review extracted data against source documents")
        lines.append("- Verify against official ECT results")
        lines.append("- Investigate potential OCR errors or data entry issues")
    elif medium_severity > 0:
        lines.append("⚠ **Quality Check Recommended**")
        lines.append("")
        lines.append(f"- {medium_severity} ballot(s) with medium-severity discrepancies")
        lines.append("- Cross-check with official results")
        lines.append("- Consider re-extraction if discrepancies exceed 5%")
    else:
        lines.append("✓ **No Action Required**")
        lines.append("")
        lines.append("- All ballots verified successfully")
        lines.append(f"- Accuracy rate: {accuracy_rate:.1f}%")
    
    lines.append("")
    lines.append("---")
    lines.append("")
    
    return "\n".join(lines)


def save_report(report_content: str, output_path: str) -> bool:
    """
    Save report content to a markdown file.
    
    Args:
        report_content: Markdown report string
        output_path: Path to save the report
        
    Returns:
        True if successful, False otherwise
    """
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(report_content)
        print(f"✓ Report saved to: {output_path}")
        return True
    except Exception as e:
        print(f"✗ Error saving report: {e}")
        return False


def markdown_table_to_pdf_table(markdown_table: str) -> tuple[list, list]:
    """
    Convert markdown table to PDF table format.
    
    Args:
        markdown_table: Markdown table string with | separators
        
    Returns:
        (data_rows, table_style) for reportlab Table
    """
    lines = [line.strip() for line in markdown_table.strip().split('\n') if line.strip()]
    if len(lines) < 2:
        return [], []
    
    # Parse header
    header = [cell.strip() for cell in lines[0].split('|')[1:-1]]
    
    # Skip separator line
    data_rows = [header]
    
    # Parse data rows
    for line in lines[2:]:
        if not line.strip():
            continue
        cells = [cell.strip() for cell in line.split('|')[1:-1]]
        if cells:
            data_rows.append(cells)
    
    # Create table style
    table_style = [
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#E0E0E0')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F5F5F5')]),
    ]
    
    return data_rows, table_style


def generate_ballot_pdf(ballot_data: BallotData, output_path: str) -> bool:
    """
    Generate a professional PDF report for a single ballot.
    
    Args:
        ballot_data: Extracted ballot data
        output_path: Path to save PDF
        
    Returns:
        True if successful, False otherwise
    """
    if not HAS_REPORTLAB:
        print("✗ reportlab not installed. Install with: pip install reportlab")
        return False
    
    try:
        doc = SimpleDocTemplate(output_path, pagesize=letter)
        styles = getSampleStyleSheet()
        story = []
        
        # Title
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=18,
            textColor=colors.HexColor('#1f4788'),
            spaceAfter=12,
            alignment=TA_CENTER,
        )
        story.append(Paragraph("Ballot Verification Report", title_style))
        story.append(Spacer(1, 0.2*inch))
        
        # Form Information Section
        story.append(Paragraph("Form Information", styles['Heading2']))
        
        form_data = [
            ['Field', 'Value'],
            ['Form Type', ballot_data.form_type],
            ['Category', ballot_data.form_category.title()],
            ['Province', ballot_data.province],
            ['Constituency', str(ballot_data.constituency_number)],
            ['District', ballot_data.district or 'N/A'],
            ['Polling Unit', str(ballot_data.polling_unit)],
            ['Polling Station', ballot_data.polling_station_id or 'N/A'],
            ['Source File', ballot_data.source_file],
        ]
        
        form_table = Table(form_data, colWidths=[2*inch, 4*inch])
        form_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4788')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F9F9F9')]),
        ]))
        story.append(form_table)
        story.append(Spacer(1, 0.3*inch))
        
        # Vote Summary Section
        story.append(Paragraph("Vote Summary", styles['Heading2']))
        
        vote_data = [
            ['Metric', 'Count'],
            ['Valid Votes', str(ballot_data.valid_votes)],
            ['Invalid Votes', str(ballot_data.invalid_votes)],
            ['Blank Votes', str(ballot_data.blank_votes)],
            ['Total Votes', f"<b>{ballot_data.total_votes}</b>"],
        ]
        
        vote_table = Table(vote_data, colWidths=[3*inch, 3*inch])
        vote_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4788')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#E8F0F8')),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
        ]))
        story.append(vote_table)
        story.append(Spacer(1, 0.3*inch))
        
        # Quality Assessment
        story.append(Paragraph("Extraction Quality", styles['Heading2']))
        
        confidence_pct = int(ballot_data.confidence_score * 100)
        confidence_level = ballot_data.confidence_details.get('level', 'UNKNOWN')
        
        quality_color = {
            'EXCELLENT': colors.HexColor('#2ecc71'),
            'GOOD': colors.HexColor('#3498db'),
            'ACCEPTABLE': colors.HexColor('#f39c12'),
            'POOR': colors.HexColor('#e74c3c'),
        }.get(confidence_level, colors.grey)
        
        quality_text = f"<font color='{quality_color.hexval()}' size=12><b>✓ {confidence_level}</b></font> ({confidence_pct}%)"
        story.append(Paragraph(quality_text, styles['Normal']))
        story.append(Spacer(1, 0.2*inch))
        
        # Candidate votes (if applicable)
        if ballot_data.form_category == 'constituency' and ballot_data.candidate_info:
            story.append(Paragraph("Candidate Votes", styles['Heading2']))
            
            cand_data = [['Position', 'Candidate Name', 'Party', 'Votes']]
            for pos, info in sorted(ballot_data.candidate_info.items()):
                votes = ballot_data.vote_counts.get(int(pos), 0)
                party = info.get('party_abbr', '?')
                cand_data.append([str(pos), info['name'], party, str(votes)])
            
            cand_table = Table(cand_data, colWidths=[1*inch, 2.5*inch, 1.2*inch, 1.3*inch])
            cand_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4788')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('ALIGN', (1, 1), (1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('GRID', (0, 0), (-1, -1), 1, colors.grey),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F9F9F9')]),
            ]))
            story.append(cand_table)
            story.append(Spacer(1, 0.3*inch))
        
        # Party votes (if applicable)
        elif ballot_data.form_category == 'party_list' and ballot_data.party_votes:
            story.append(Paragraph("Party Votes", styles['Heading2']))
            
            party_data = [['Party', 'Votes', 'Percentage']]
            total_pv = sum(ballot_data.party_votes.values())
            for party_no, votes in sorted(ballot_data.party_votes.items()):
                pct = (votes / total_pv * 100) if total_pv > 0 else 0
                party_data.append([str(party_no), str(votes), f"{pct:.1f}%"])
            
            party_table = Table(party_data, colWidths=[2*inch, 2*inch, 2*inch])
            party_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4788')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('GRID', (0, 0), (-1, -1), 1, colors.grey),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F9F9F9')]),
            ]))
            story.append(party_table)
            story.append(Spacer(1, 0.3*inch))
        
        # Footer
        story.append(Spacer(1, 0.3*inch))
        footer_text = f"<i>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</i>"
        story.append(Paragraph(footer_text, styles['Normal']))
        
        doc.build(story)
        print(f"✓ PDF report saved to: {output_path}")
        return True

    except Exception as e:
        print(f"✗ Error generating PDF: {e}")
        return False


def _create_confidence_chart(ballot_data_list: list) -> "Drawing":
    """Create a bar chart showing confidence level distribution."""
    # Count by confidence level
    levels = {"EXCELLENT": 0, "GOOD": 0, "ACCEPTABLE": 0, "POOR": 0, "VERY_LOW": 0}
    for ballot in ballot_data_list:
        level = ballot.confidence_details.get("level", "POOR")
        if level in levels:
            levels[level] += 1
        else:
            levels["POOR"] += 1

    drawing = Drawing(400, 200)

    bc = VerticalBarChart()
    bc.x = 50
    bc.y = 50
    bc.height = 125
    bc.width = 300
    bc.data = [[levels["EXCELLENT"], levels["GOOD"], levels["ACCEPTABLE"], levels["POOR"], levels["VERY_LOW"]]]
    bc.strokeColor = colors.black
    bc.valueAxis.valueMin = 0
    bc.valueAxis.valueMax = max(levels.values()) + 1 if max(levels.values()) > 0 else 5
    bc.valueAxis.valueStep = 1
    bc.categoryAxis.labels.boxAnchor = 'ne'
    bc.categoryAxis.labels.dx = 8
    bc.categoryAxis.labels.dy = -2
    bc.categoryAxis.labels.angle = 30
    bc.categoryAxis.categoryNames = ['Excellent', 'Good', 'Acceptable', 'Poor', 'Very Low']

    # Color the bars
    bc.bars[0].fillColor = colors.HexColor('#1f4788')

    drawing.add(bc)

    # Title
    title = String(200, 180, 'Confidence Distribution', fontSize=12, fillColor=colors.black, textAnchor='middle')
    drawing.add(title)

    return drawing


def _create_province_pie_chart(ballot_data_list: list) -> "Drawing":
    """Create a pie chart showing ballot distribution by province."""
    # Count by province
    provinces = {}
    for ballot in ballot_data_list:
        prov = ballot.province or "Unknown"
        provinces[prov] = provinces.get(prov, 0) + 1

    # Sort and take top 8, group rest as "Other"
    sorted_provs = sorted(provinces.items(), key=lambda x: x[1], reverse=True)
    if len(sorted_provs) > 8:
        top_provs = sorted_provs[:8]
        other_count = sum(c for _, c in sorted_provs[8:])
        if other_count > 0:
            top_provs.append(("Other", other_count))
    else:
        top_provs = sorted_provs

    drawing = Drawing(400, 250)

    pie = Pie()
    pie.x = 100
    pie.y = 50
    pie.width = 150
    pie.height = 150
    pie.data = [c for _, c in top_provs]
    pie.labels = [p[:15] for p, _ in top_provs]  # Truncate long names

    # Colors for pie slices
    pie_colors = [
        colors.HexColor('#1f4788'),
        colors.HexColor('#3498db'),
        colors.HexColor('#2ecc71'),
        colors.HexColor('#f39c12'),
        colors.HexColor('#e74c3c'),
        colors.HexColor('#9b59b6'),
        colors.HexColor('#1abc9c'),
        colors.HexColor('#34495e'),
        colors.HexColor('#95a5a6'),
    ]
    for i in range(len(top_provs)):
        pie.slices[i].fillColor = pie_colors[i % len(pie_colors)]

    pie.slices.strokeWidth = 0.5

    drawing.add(pie)

    # Title
    title = String(200, 220, 'Ballots by Province', fontSize=12, fillColor=colors.black, textAnchor='middle')
    drawing.add(title)

    return drawing


def _create_votes_bar_chart(aggregated_results: dict) -> "Drawing":
    """Create a bar chart showing total votes by constituency."""
    if not aggregated_results:
        return None

    # Get vote totals per constituency
    constituencies = []
    for (province, cons_no), agg in aggregated_results.items():
        cons_name = f"{province[:10]}-{cons_no}"
        constituencies.append((cons_name, agg.valid_votes_total))

    # Sort by votes and take top 10
    constituencies.sort(key=lambda x: x[1], reverse=True)
    top_cons = constituencies[:10]

    if not top_cons:
        return None

    drawing = Drawing(450, 220)

    bc = VerticalBarChart()
    bc.x = 50
    bc.y = 50
    bc.height = 125
    bc.width = 350
    bc.data = [[v for _, v in top_cons]]
    bc.strokeColor = colors.black
    bc.valueAxis.valueMin = 0
    bc.valueAxis.valueMax = max(v for _, v in top_cons) + 50
    bc.categoryAxis.labels.boxAnchor = 'ne'
    bc.categoryAxis.labels.dx = 8
    bc.categoryAxis.labels.dy = -2
    bc.categoryAxis.labels.angle = 45
    bc.categoryAxis.labels.fontSize = 7
    bc.categoryAxis.categoryNames = [name for name, _ in top_cons]

    bc.bars[0].fillColor = colors.HexColor('#2ecc71')

    drawing.add(bc)

    # Title
    title = String(225, 195, 'Valid Votes by Constituency (Top 10)', fontSize=11, fillColor=colors.black, textAnchor='middle')
    drawing.add(title)

    return drawing


def generate_batch_pdf(aggregated_results: dict, ballot_data_list: list, output_path: str) -> bool:
    """
    Generate a PDF batch summary report.
    
    Args:
        aggregated_results: Dictionary of aggregated results by constituency
        ballot_data_list: List of all BallotData objects
        output_path: Path to save PDF
        
    Returns:
        True if successful, False otherwise
    """
    if not HAS_REPORTLAB:
        print("✗ reportlab not installed. Install with: pip install reportlab")
        return False
    
    try:
        doc = SimpleDocTemplate(output_path, pagesize=letter)
        styles = getSampleStyleSheet()
        story = []
        
        # Title
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=18,
            textColor=colors.HexColor('#1f4788'),
            spaceAfter=12,
            alignment=TA_CENTER,
        )
        story.append(Paragraph("Batch Ballot Verification Report", title_style))
        story.append(Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles['Normal']))
        story.append(Spacer(1, 0.3*inch))
        
        # Overall Statistics
        story.append(Paragraph("Overall Statistics", styles['Heading2']))
        
        total_ballots = len(ballot_data_list)
        verified_count = len([b for b in ballot_data_list if b.confidence_score >= 0.90])
        
        stats_data = [
            ['Metric', 'Count', 'Percentage'],
            ['Total Ballots', str(total_ballots), '100%'],
            ['Verified (High Confidence)', str(verified_count), f"{verified_count/total_ballots*100:.1f}%"],
        ]
        
        stats_table = Table(stats_data, colWidths=[3*inch, 1.5*inch, 1.5*inch])
        stats_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4788')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
        ]))
        story.append(stats_table)
        story.append(Spacer(1, 0.3*inch))
        
        # Form Type Breakdown
        story.append(Paragraph("Form Type Breakdown", styles['Heading2']))
        
        form_types = {}
        for ballot in ballot_data_list:
            form_types[ballot.form_type] = form_types.get(ballot.form_type, 0) + 1
        
        form_data = [['Form Type', 'Count']]
        for form_type, count in sorted(form_types.items()):
            form_data.append([form_type, str(count)])
        
        form_table = Table(form_data, colWidths=[3*inch, 3*inch])
        form_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4788')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
        ]))
        story.append(form_table)
        story.append(Spacer(1, 0.3*inch))
        
        # Province Breakdown
        story.append(Paragraph("Province Breakdown", styles['Heading2']))
        
        provinces = {}
        for ballot in ballot_data_list:
            provinces[ballot.province] = provinces.get(ballot.province, 0) + 1
        
        prov_data = [['Province', 'Count']]
        for province, count in sorted(provinces.items()):
            prov_data.append([province, str(count)])
        
        prov_table = Table(prov_data, colWidths=[3*inch, 3*inch])
        prov_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4788')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
        ]))
        story.append(prov_table)
        story.append(Spacer(1, 0.3*inch))

        # Charts Section
        story.append(PageBreak())
        story.append(Paragraph("Visual Analysis", styles['Heading2']))
        story.append(Spacer(1, 0.2*inch))

        # Confidence Distribution Chart
        if len(ballot_data_list) > 0:
            story.append(Paragraph("Confidence Level Distribution", styles['Heading3']))
            conf_chart = _create_confidence_chart(ballot_data_list)
            story.append(conf_chart)
            story.append(Spacer(1, 0.3*inch))

        # Province Pie Chart
        if len(ballot_data_list) > 1:
            story.append(Paragraph("Ballot Distribution by Province", styles['Heading3']))
            prov_chart = _create_province_pie_chart(ballot_data_list)
            story.append(prov_chart)
            story.append(Spacer(1, 0.3*inch))

        # Votes by Constituency Chart (if aggregated data available)
        if aggregated_results:
            story.append(Paragraph("Valid Votes by Constituency", styles['Heading3']))
            votes_chart = _create_votes_bar_chart(aggregated_results)
            if votes_chart:
                story.append(votes_chart)
            story.append(Spacer(1, 0.3*inch))

        # Ballot Details (per page if many)
        if len(ballot_data_list) > 0 and len(ballot_data_list) <= 10:
            story.append(PageBreak())
            story.append(Paragraph("Ballot Details", styles['Heading2']))
            
            ballot_data = [['#', 'Form Type', 'Province', 'Station', 'Valid Votes', 'Confidence']]
            for i, ballot in enumerate(ballot_data_list, 1):
                confidence_level = ballot.confidence_details.get('level', 'UNKNOWN')
                ballot_data.append([
                    str(i),
                    ballot.form_type,
                    ballot.province,
                    ballot.polling_station_id or 'N/A',
                    str(ballot.valid_votes),
                    confidence_level
                ])
            
            ballot_table = Table(ballot_data, colWidths=[0.5*inch, 1.2*inch, 1*inch, 1.5*inch, 1*inch, 1.2*inch])
            ballot_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4788')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 8),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('GRID', (0, 0), (-1, -1), 1, colors.grey),
                ('FONTSIZE', (0, 1), (-1, -1), 7),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F9F9F9')]),
            ]))
            story.append(ballot_table)
        
        doc.build(story)
        print(f"✓ Batch PDF report saved to: {output_path}")
        return True
        
    except Exception as e:
        print(f"✗ Error generating batch PDF: {e}")
        return False


def generate_constituency_pdf(agg: "AggregatedResults", output_path: str) -> bool:
    """
    Generate a professional PDF report for aggregated constituency results.

    Args:
        agg: AggregatedResults object with aggregated data
        output_path: Path to save PDF

    Returns:
        True if successful, False otherwise
    """
    if not HAS_REPORTLAB:
        print("✗ reportlab not installed. Install with: pip install reportlab")
        return False

    try:
        doc = SimpleDocTemplate(output_path, pagesize=letter)
        styles = getSampleStyleSheet()
        story = []

        # Title
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=18,
            textColor=colors.HexColor('#1f4788'),
            spaceAfter=12,
            alignment=TA_CENTER,
        )
        story.append(Paragraph("Constituency Results Report", title_style))
        story.append(Spacer(1, 0.2*inch))

        # Constituency Information Section
        story.append(Paragraph("Constituency Information", styles['Heading2']))

        info_data = [
            ['Field', 'Value'],
            ['Province', agg.province],
            ['Constituency', agg.constituency],
            ['Constituency #', str(agg.constituency_no)],
        ]

        info_table = Table(info_data, colWidths=[2*inch, 4*inch])
        info_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4788')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F9F9F9')]),
        ]))
        story.append(info_table)
        story.append(Spacer(1, 0.3*inch))

        # Data Collection Status
        story.append(Paragraph("Data Collection Status", styles['Heading2']))

        status_data = [
            ['Metric', 'Value'],
            ['Ballots Processed', str(agg.ballots_processed)],
            ['Polling Units Reporting', str(agg.polling_units_reporting)],
            ['Reporting Rate', f"{float(agg.turnout_rate or 0):.1f}%"],
            ['Form Types Used', ', '.join(agg.form_types) if agg.form_types else 'N/A'],
        ]

        status_table = Table(status_data, colWidths=[3*inch, 3*inch])
        status_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4788')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F9F9F9')]),
        ]))
        story.append(status_table)
        story.append(Spacer(1, 0.3*inch))

        # Vote Totals
        story.append(Paragraph("Vote Totals", styles['Heading2']))

        vote_data = [
            ['Category', 'Votes'],
            ['Valid Votes', str(agg.valid_votes_total)],
            ['Invalid Votes', str(agg.invalid_votes_total)],
            ['Blank Votes', str(agg.blank_votes_total)],
            ['Overall Total', f"<b>{agg.overall_total}</b>"],
        ]

        vote_table = Table(vote_data, colWidths=[3*inch, 3*inch])
        vote_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4788')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 4), (-1, 4), colors.HexColor('#E8F0F8')),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
        ]))
        story.append(vote_table)
        story.append(Spacer(1, 0.3*inch))

        # Quality Assessment
        story.append(Paragraph("Data Quality", styles['Heading2']))

        confidence_pct = int(agg.aggregated_confidence * 100)
        if agg.aggregated_confidence >= 0.95:
            confidence_level = 'EXCELLENT'
            quality_color = colors.HexColor('#2ecc71')
        elif agg.aggregated_confidence >= 0.85:
            confidence_level = 'GOOD'
            quality_color = colors.HexColor('#3498db')
        elif agg.aggregated_confidence >= 0.70:
            confidence_level = 'ACCEPTABLE'
            quality_color = colors.HexColor('#f39c12')
        else:
            confidence_level = 'POOR'
            quality_color = colors.HexColor('#e74c3c')

        quality_text = f"<font color='{quality_color.hexval()}' size=12><b>✓ {confidence_level}</b></font> ({confidence_pct}%)"
        story.append(Paragraph(quality_text, styles['Normal']))
        story.append(Paragraph(f"Discrepancy Rate: {float(agg.discrepancy_rate or 0):.1%}", styles['Normal']))
        story.append(Paragraph(f"Ballots with Issues: {agg.ballots_with_discrepancies}/{agg.ballots_processed}", styles['Normal']))
        story.append(Spacer(1, 0.2*inch))

        # Results table - determine if party-list or constituency
        is_party_list = bool(agg.party_totals)

        if is_party_list:
            story.append(Paragraph("Party Results", styles['Heading2']))

            party_data = [['Party #', 'Party Name', 'Abbr', 'Votes', 'Percentage']]
            sorted_results = sorted(agg.party_totals.items(), key=lambda x: x[1], reverse=True)

            for party_num_str, votes in sorted_results:
                info = agg.party_info.get(party_num_str, {})
                party_name = info.get("name", "Unknown")
                abbr = info.get("abbr", "")
                votes_int = int(votes) if votes else 0
                percentage = (votes_int / agg.valid_votes_total * 100) if agg.valid_votes_total > 0 else 0
                party_data.append([str(party_num_str), party_name[:25], abbr, str(votes_int), f"{percentage:.2f}%"])

            if len(party_data) > 1:
                party_table = Table(party_data, colWidths=[0.8*inch, 2.5*inch, 0.8*inch, 1*inch, 1*inch])
                party_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4788')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('ALIGN', (1, 1), (1, -1), 'LEFT'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 9),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                    ('GRID', (0, 0), (-1, -1), 1, colors.grey),
                    ('FONTSIZE', (0, 1), (-1, -1), 8),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F9F9F9')]),
                ]))
                story.append(party_table)
        else:
            story.append(Paragraph("Candidate Results", styles['Heading2']))

            cand_data = [['Pos', 'Candidate Name', 'Party', 'Votes', 'Percentage']]
            sorted_results = sorted(agg.candidate_totals.items(), key=lambda x: x[1], reverse=True)

            for position, votes in sorted_results:
                info = agg.candidate_info.get(position, {})
                candidate_name = info.get("name", "Unknown")
                party = info.get("party_abbr", "")
                votes_int = int(votes) if votes else 0
                percentage = (votes_int / agg.valid_votes_total * 100) if agg.valid_votes_total > 0 else 0
                cand_data.append([str(position), candidate_name[:30], party, str(votes_int), f"{percentage:.2f}%"])

            if len(cand_data) > 1:
                cand_table = Table(cand_data, colWidths=[0.6*inch, 2.8*inch, 0.8*inch, 1*inch, 1*inch])
                cand_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4788')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('ALIGN', (1, 1), (1, -1), 'LEFT'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 9),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                    ('GRID', (0, 0), (-1, -1), 1, colors.grey),
                    ('FONTSIZE', (0, 1), (-1, -1), 8),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F9F9F9')]),
                ]))
                story.append(cand_table)

        story.append(Spacer(1, 0.3*inch))

        # Winners section
        if agg.winners:
            story.append(Paragraph("Top Results", styles['Heading2']))

            for i, winner in enumerate(agg.winners[:3], 1):
                if is_party_list:
                    winner_text = f"<b>#{i}</b> {winner.get('name', 'N/A')} ({winner.get('abbr', '')})"
                else:
                    winner_text = f"<b>#{i}</b> {winner.get('name', 'N/A')} ({winner.get('party', '')})"
                pct_val = winner.get('percentage', 0)
                if isinstance(pct_val, str):
                    pct_val = float(pct_val.rstrip('%'))
                else:
                    pct_val = float(pct_val or 0)
                votes_text = f"Votes: {winner.get('votes', 0)} ({pct_val:.2f}%)"
                story.append(Paragraph(winner_text, styles['Normal']))
                story.append(Paragraph(f"    {votes_text}", styles['Normal']))

            story.append(Spacer(1, 0.2*inch))

        # Source Information
        if agg.source_ballots:
            story.append(Paragraph("Source Information", styles['Heading2']))
            for source in agg.source_ballots[:10]:  # Limit to 10 sources
                story.append(Paragraph(f"• {source}", styles['Normal']))
            if len(agg.source_ballots) > 10:
                story.append(Paragraph(f"<i>... and {len(agg.source_ballots) - 10} more</i>", styles['Normal']))

        # Footer
        story.append(Spacer(1, 0.3*inch))
        footer_text = f"<i>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</i>"
        story.append(Paragraph(footer_text, styles['Normal']))

        doc.build(story)
        print(f"✓ Constituency PDF report saved to: {output_path}")
        return True

    except Exception as e:
        print(f"✗ Error generating constituency PDF: {e}")
        return False


def generate_executive_summary_pdf(
    all_results: list["AggregatedResults"],
    anomalies: list[dict],
    output_path: str,
    provinces: Optional[list[str]] = None
) -> bool:
    """
    Generate a professional PDF executive summary report.

    Args:
        all_results: All AggregatedResults from all constituencies
        anomalies: All detected anomalies
        output_path: Path to save PDF
        provinces: Optional list of provinces (auto-detected if None)

    Returns:
        True if successful, False otherwise
    """
    if not HAS_REPORTLAB:
        print("✗ reportlab not installed. Install with: pip install reportlab")
        return False

    if not all_results:
        print("✗ No results to summarize")
        return False

    try:
        doc = SimpleDocTemplate(output_path, pagesize=letter)
        styles = getSampleStyleSheet()
        story = []

        # Detect provinces if not provided
        if provinces is None:
            provinces = sorted(set(r.province for r in all_results))

        # Title
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=20,
            textColor=colors.HexColor('#1f4788'),
            spaceAfter=12,
            alignment=TA_CENTER,
        )
        story.append(Paragraph("Electoral Results", title_style))
        story.append(Paragraph("Executive Summary", styles['Heading2']))
        story.append(Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles['Normal']))
        story.append(Spacer(1, 0.3*inch))

        # Key Statistics
        total_valid = sum(r.valid_votes_total for r in all_results)
        total_invalid = sum(r.invalid_votes_total for r in all_results)
        total_blank = sum(r.blank_votes_total for r in all_results)
        total_votes = sum(r.overall_total for r in all_results)
        avg_confidence = (sum(r.aggregated_confidence for r in all_results) / len(all_results)) if all_results else 0

        story.append(Paragraph("Key Statistics", styles['Heading2']))

        stats_data = [
            ['Metric', 'Value'],
            ['Total Constituencies', str(len(all_results))],
            ['Total Provinces', str(len(provinces))],
            ['Total Valid Votes', f"{total_valid:,}"],
            ['Total Invalid Votes', f"{total_invalid:,}"],
            ['Total Blank Votes', f"{total_blank:,}"],
            ['Overall Total', f"<b>{total_votes:,}</b>"],
            ['Average Confidence', f"{avg_confidence:.1%}"],
        ]

        stats_table = Table(stats_data, colWidths=[3*inch, 3*inch])
        stats_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4788')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 6), (-1, 6), colors.HexColor('#E8F0F8')),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
        ]))
        story.append(stats_table)
        story.append(Spacer(1, 0.3*inch))

        # Data Quality Assessment
        story.append(Paragraph("Data Quality Assessment", styles['Heading2']))

        if avg_confidence >= 0.95:
            quality_rating = "EXCELLENT"
            quality_color = colors.HexColor('#2ecc71')
        elif avg_confidence >= 0.85:
            quality_rating = "GOOD"
            quality_color = colors.HexColor('#3498db')
        elif avg_confidence >= 0.75:
            quality_rating = "ACCEPTABLE"
            quality_color = colors.HexColor('#f39c12')
        else:
            quality_rating = "POOR"
            quality_color = colors.HexColor('#e74c3c')

        quality_text = f"<font color='{quality_color.hexval()}' size=14><b>{quality_rating}</b></font>"
        story.append(Paragraph(f"Overall Rating: {quality_text}", styles['Normal']))
        story.append(Paragraph(f"Average Confidence: {avg_confidence:.1%}", styles['Normal']))
        story.append(Spacer(1, 0.2*inch))

        # Province Summary
        story.append(Paragraph("Results by Province", styles['Heading2']))

        prov_data = [['Province', 'Constituencies', 'Valid Votes', 'Avg Confidence']]
        for province in provinces:
            prov_results = [r for r in all_results if r.province == province]
            if prov_results:
                prov_valid = sum(r.valid_votes_total for r in prov_results)
                prov_conf = sum(r.aggregated_confidence for r in prov_results) / len(prov_results)
                prov_data.append([province, str(len(prov_results)), f"{prov_valid:,}", f"{prov_conf:.1%}"])

        if len(prov_data) > 1:
            prov_table = Table(prov_data, colWidths=[2*inch, 1.5*inch, 1.5*inch, 1.5*inch])
            prov_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4788')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('GRID', (0, 0), (-1, -1), 1, colors.grey),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F9F9F9')]),
            ]))
            story.append(prov_table)
            story.append(Spacer(1, 0.3*inch))

        # Top Candidates (if constituency results)
        is_party_list = bool(all_results[0].party_totals) if all_results else False
        if not is_party_list:
            story.append(Paragraph("Top Candidates Overall", styles['Heading2']))

            # Aggregate all candidates
            all_winners = []
            for result in all_results:
                for winner in result.winners:
                    all_winners.append({
                        "name": winner["name"],
                        "province": result.province,
                        "votes": winner.get("votes", 0),
                        "percentage": winner.get("percentage", 0)
                    })

            # Sort by votes
            top_winners = sorted(all_winners, key=lambda x: x["votes"] if isinstance(x["votes"], int) else 0, reverse=True)[:10]

            if top_winners:
                cand_data = [['Rank', 'Candidate', 'Province', 'Votes', '%']]
                for i, winner in enumerate(top_winners, 1):
                    pct_val = winner["percentage"]
                    if isinstance(pct_val, str):
                        pct_val = pct_val.rstrip('%')
                    cand_data.append([
                        str(i),
                        winner["name"][:25],
                        winner["province"][:15],
                        str(winner["votes"]),
                        f"{float(pct_val or 0):.1f}%"
                    ])

                cand_table = Table(cand_data, colWidths=[0.5*inch, 2.5*inch, 1.2*inch, 1*inch, 0.8*inch])
                cand_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4788')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('ALIGN', (1, 1), (1, -1), 'LEFT'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 9),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                    ('GRID', (0, 0), (-1, -1), 1, colors.grey),
                    ('FONTSIZE', (0, 1), (-1, -1), 8),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F9F9F9')]),
                ]))
                story.append(cand_table)
                story.append(Spacer(1, 0.3*inch))

        # Issues & Recommendations
        story.append(PageBreak())
        story.append(Paragraph("Issues & Recommendations", styles['Heading2']))

        if anomalies:
            high_anomalies = [a for a in anomalies if a.get("severity") == "HIGH"]
            medium_anomalies = [a for a in anomalies if a.get("severity") == "MEDIUM"]

            story.append(Paragraph(f"<b>Total Anomalies Detected:</b> {len(anomalies)}", styles['Normal']))
            story.append(Spacer(1, 0.1*inch))

            if high_anomalies:
                story.append(Paragraph(f"<font color='#e74c3c'><b>CRITICAL ({len(high_anomalies)}):</b></font>", styles['Normal']))
                for anom in high_anomalies[:5]:
                    story.append(Paragraph(f"  • {anom.get('constituency', 'Unknown')}", styles['Normal']))
                story.append(Spacer(1, 0.1*inch))

            if medium_anomalies:
                story.append(Paragraph(f"<font color='#f39c12'><b>NEEDS REVIEW ({len(medium_anomalies)}):</b></font>", styles['Normal']))
                for anom in medium_anomalies[:5]:
                    story.append(Paragraph(f"  • {anom.get('constituency', 'Unknown')}", styles['Normal']))
                story.append(Spacer(1, 0.2*inch))
        else:
            story.append(Paragraph("✓ No anomalies detected", styles['Normal']))
            story.append(Spacer(1, 0.2*inch))

        # Final Recommendations
        story.append(Paragraph("Recommendations", styles['Heading3']))
        if avg_confidence < 0.85:
            story.append(Paragraph("⚠ <b>Low average confidence.</b> Consider re-verification of data.", styles['Normal']))
        elif anomalies and len(anomalies) > len(all_results) * 0.2:
            story.append(Paragraph("⚠ <b>High anomaly rate.</b> Manual review of flagged constituencies recommended.", styles['Normal']))
        else:
            story.append(Paragraph("✓ <b>Data quality acceptable.</b> Proceed with standard verification process.", styles['Normal']))

        # Footer
        story.append(Spacer(1, 0.5*inch))
        footer_text = "<i>Report generated automatically by Thai Election Ballot OCR</i>"
        story.append(Paragraph(footer_text, styles['Normal']))

        doc.build(story)
        print(f"✓ Executive Summary PDF saved to: {output_path}")
        return True

    except Exception as e:
        print(f"✗ Error generating executive summary PDF: {e}")
        return False


# =============================================================================
# One-Page Executive Summary PDF Generation (Phase 8)
# =============================================================================

def _create_compact_stats_table(all_results: list["AggregatedResults"], ballots_processed: int, duration_seconds: float) -> "Table":
    """
    Create a compact 2-column stats table for one-page executive summary.

    Args:
        all_results: List of AggregatedResults
        ballots_processed: Total number of ballots processed
        duration_seconds: Processing duration in seconds

    Returns:
        Formatted Table with compact stats
    """
    if not all_results:
        # Empty state
        stats_data = [
            ['Total Ballots', '0', 'Total Provinces', '0'],
            ['Valid Votes', '0', 'Avg Confidence', '0%'],
            ['Invalid Votes', '0', 'Processing Time', '0.0s'],
        ]
    else:
        total_valid = sum(r.valid_votes_total for r in all_results)
        total_invalid = sum(r.invalid_votes_total for r in all_results)
        avg_confidence = sum(r.aggregated_confidence for r in all_results) / len(all_results)
        provinces = len(set(r.province for r in all_results))

        stats_data = [
            ['Total Ballots', str(ballots_processed), 'Total Provinces', str(provinces)],
            ['Valid Votes', f"{total_valid:,}", 'Avg Confidence', f"{avg_confidence:.1%}"],
            ['Invalid Votes', f"{total_invalid:,}", 'Processing Time', f"{duration_seconds:.1f}s"],
        ]

    table = Table(stats_data, colWidths=[1.3*inch, 1.2*inch, 1.3*inch, 1.2*inch])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f0f0f0')),
        ('BACKGROUND', (2, 0), (2, -1), colors.HexColor('#f0f0f0')),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('ALIGN', (3, 0), (3, -1), 'RIGHT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),
    ]))
    return table


def _format_discrepancy_summary_inline(all_results: list["AggregatedResults"]) -> "Paragraph":
    """
    Format discrepancy summary as inline color-coded text.

    Args:
        all_results: List of AggregatedResults with discrepancy_rate field

    Returns:
        Paragraph with color-coded discrepancy counts
    """
    if not all_results:
        text = (
            "<font color='#2ecc71'><b>NONE: 0</b></font>"
        )
    else:
        # Count by severity
        critical = sum(1 for r in all_results if r.discrepancy_rate > 0.5)
        medium = sum(1 for r in all_results if 0.25 < r.discrepancy_rate <= 0.5)
        low = sum(1 for r in all_results if 0 < r.discrepancy_rate <= 0.25)
        none = sum(1 for r in all_results if r.discrepancy_rate == 0)

        # Color-coded inline format
        text = (
            f"<font color='#e74c3c'><b>CRITICAL: {critical}</b></font> | "
            f"<font color='#f39c12'><b>MEDIUM: {medium}</b></font> | "
            f"<font color='#3498db'><b>LOW: {low}</b></font> | "
            f"<font color='#2ecc71'><b>NONE: {none}</b></font>"
        )

    return Paragraph(f"Discrepancy Summary: {text}", ParagraphStyle(
        'DiscrepancyStyle',
        fontSize=9,
        spaceAfter=6,
        spaceBefore=6
    ))


def _create_top_parties_chart(all_results: list["AggregatedResults"], width: float = None, height: float = None) -> "Drawing":
    """
    Create a compact horizontal bar chart for top 5 parties by total votes.

    Args:
        all_results: List of AggregatedResults with party_totals
        width: Chart width (default 5 inches)
        height: Chart height (default 2 inches)

    Returns:
        Drawing with horizontal bar chart, or None if no party data
    """
    if not HAS_REPORTLAB:
        return None

    # Set defaults after HAS_REPORTLAB check so inch is defined
    if width is None:
        width = 5*inch
    if height is None:
        height = 2*inch

    # Aggregate all party votes
    party_totals = {}
    for result in all_results:
        for party_num, votes in result.party_totals.items():
            party_totals[party_num] = party_totals.get(party_num, 0) + votes

    # Sort and take top 5
    sorted_parties = sorted(party_totals.items(), key=lambda x: x[1], reverse=True)[:5]
    if not sorted_parties:
        return None

    drawing = Drawing(width, height)

    bc = HorizontalBarChart()
    bc.x = 80  # Space for labels
    bc.y = 20
    bc.height = height - 40
    bc.width = width - 100
    bc.data = [[v for _, v in sorted_parties]]
    bc.strokeColor = colors.black
    bc.valueAxis.valueMin = 0
    bc.valueAxis.valueMax = max(v for _, v in sorted_parties) * 1.1
    bc.categoryAxis.categoryNames = [f"Party {p}" for p, _ in sorted_parties]
    bc.bars[0].fillColor = colors.HexColor('#1f4788')

    drawing.add(bc)

    # Title
    title = String(width / 2, height - 10, 'Top 5 Parties by Total Votes', fontSize=10, fillColor=colors.black, textAnchor='middle')
    drawing.add(title)

    return drawing


def generate_one_page_executive_summary_pdf(
    all_results: list["AggregatedResults"],
    batch_result: "BatchResult",
    output_path: str
) -> bool:
    """
    Generate a one-page executive summary PDF with key batch statistics.

    This function creates a compact, single-page PDF summary with:
    - Compact 2-column stats table
    - Color-coded discrepancy summary by severity
    - Top 5 parties horizontal bar chart
    - Batch metadata footer

    Args:
        all_results: List of AggregatedResults from all constituencies
        batch_result: BatchResult with timing and metadata
        output_path: Path to save PDF

    Returns:
        True if successful, False otherwise
    """
    if not HAS_REPORTLAB:
        print("reportlab not installed. Install with: pip install reportlab")
        return False

    if not all_results:
        print("No results to summarize")
        return False

    try:
        # Document setup with tight margins for one-page layout
        doc = SimpleDocTemplate(
            output_path,
            pagesize=letter,
            leftMargin=0.5*inch,
            rightMargin=0.5*inch,
            topMargin=0.5*inch,
            bottomMargin=0.5*inch
        )
        styles = getSampleStyleSheet()
        story = []

        # Title (compact, 14pt)
        title_style = ParagraphStyle(
            'CompactTitle',
            parent=styles['Heading1'],
            fontSize=14,
            textColor=colors.HexColor('#1f4788'),
            spaceAfter=6,
            alignment=TA_CENTER,
        )
        story.append(Paragraph("Electoral Results - Executive Summary", title_style))

        # Timestamp line
        timestamp_style = ParagraphStyle(
            'Timestamp',
            parent=styles['Normal'],
            fontSize=8,
            textColor=colors.grey,
            alignment=TA_CENTER,
            spaceAfter=8
        )
        story.append(Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", timestamp_style))

        # Small spacer
        story.append(Spacer(1, 0.1*inch))

        # Compact stats table
        stats_table = _create_compact_stats_table(
            all_results,
            batch_result.processed if hasattr(batch_result, 'processed') else len(all_results),
            batch_result.duration_seconds if hasattr(batch_result, 'duration_seconds') else 0.0
        )
        story.append(stats_table)

        # Small spacer
        story.append(Spacer(1, 0.1*inch))

        # Discrepancy summary (inline, color-coded)
        discrepancy_para = _format_discrepancy_summary_inline(all_results)
        story.append(discrepancy_para)

        # Small spacer
        story.append(Spacer(1, 0.1*inch))

        # Top 5 parties horizontal bar chart
        chart = _create_top_parties_chart(all_results)
        if chart:
            story.append(chart)
        else:
            # Fallback message if no party data
            no_chart_style = ParagraphStyle(
                'NoChart',
                parent=styles['Normal'],
                fontSize=9,
                textColor=colors.grey,
                alignment=TA_CENTER
            )
            story.append(Paragraph("(No party-list data available)", no_chart_style))

        # Small spacer
        story.append(Spacer(1, 0.1*inch))

        # Footer with batch metadata (smaller font, 7pt italic)
        footer_style = ParagraphStyle(
            'Footer',
            parent=styles['Normal'],
            fontSize=7,
            textColor=colors.grey,
            alignment=TA_CENTER,
            fontName='Helvetica-Oblique'
        )
        processed_count = batch_result.processed if hasattr(batch_result, 'processed') else len(all_results)
        duration = batch_result.duration_seconds if hasattr(batch_result, 'duration_seconds') else 0.0
        footer_text = f"Batch processed: {processed_count} ballots in {duration:.1f}s"
        story.append(Paragraph(footer_text, footer_style))

        # Build the PDF (NO PageBreak() - single page constraint)
        doc.build(story)
        print(f"One-page Executive Summary PDF saved to: {output_path}")
        return True

    except Exception as e:
        print(f"Error generating one-page executive summary PDF: {e}")
        return False


def aggregate_ballot_results(ballot_data_list: list[BallotData]) -> dict[tuple, AggregatedResults]:
    """
    Aggregate ballot results by constituency.
    
    Args:
        ballot_data_list: List of BallotData objects from multiple polling stations
        
    Returns:
        Dictionary mapping (province, constituency_no) to AggregatedResults
    """
    # Group ballots by constituency
    grouped = {}
    
    for ballot in ballot_data_list:
        key = (ballot.province, ballot.constituency_number)
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(ballot)
    
    # Aggregate each constituency
    results = {}
    for (province, cons_no), ballots in grouped.items():
        results[(province, cons_no)] = aggregate_constituency(province, cons_no, ballots)
    
    return results


def aggregate_constituency(province: str, constituency_no: int, ballots: list[BallotData]) -> AggregatedResults:
    """
    Aggregate ballot results for a single constituency.
    
    Args:
        province: Province name
        constituency_no: Constituency number
        ballots: List of BallotData objects for this constituency
        
    Returns:
        AggregatedResults with aggregated votes and analysis
    """
    if not ballots:
        return AggregatedResults(province=province, constituency=province, constituency_no=constituency_no)
    
    # Determine if this is constituency or party-list based on first ballot
    is_party_list = ballots[0].form_category == "party_list"
    
    # Initialize aggregation
    agg = AggregatedResults(
        province=province,
        constituency=ballots[0].district or province,
        constituency_no=constituency_no,
        ballots_processed=len(ballots),
    )
    
    # Aggregate votes
    if is_party_list:
        # Party-list aggregation
        party_vote_counts = {}
        party_info_map = {}
        
        for ballot in ballots:
            # Add votes
            for party_num_str, votes in ballot.party_votes.items():
                party_vote_counts[party_num_str] = party_vote_counts.get(party_num_str, 0) + votes
            
            # Collect party info
            for party_num_str, info in ballot.party_info.items():
                if party_num_str not in party_info_map:
                    party_info_map[party_num_str] = info
        
        agg.party_totals = party_vote_counts
        agg.party_info = party_info_map
        
    else:
        # Constituency aggregation
        candidate_vote_counts = {}
        candidate_info_map = {}
        
        for ballot in ballots:
            # Add votes
            for position, votes in ballot.vote_counts.items():
                candidate_vote_counts[position] = candidate_vote_counts.get(position, 0) + votes
            
            # Collect candidate info
            for position, info in ballot.candidate_info.items():
                if position not in candidate_info_map:
                    candidate_info_map[position] = info
        
        agg.candidate_totals = candidate_vote_counts
        agg.candidate_info = candidate_info_map
    
    # Aggregate vote categories
    valid_total = 0
    invalid_total = 0
    blank_total = 0
    
    for ballot in ballots:
        valid_total += ballot.valid_votes
        invalid_total += ballot.invalid_votes
        blank_total += ballot.blank_votes
    
    agg.valid_votes_total = valid_total
    agg.invalid_votes_total = invalid_total
    agg.blank_votes_total = blank_total
    agg.overall_total = valid_total + invalid_total + blank_total
    
    # Count polling units
    polling_units = set()
    for ballot in ballots:
        polling_units.add(ballot.polling_unit)
    agg.polling_units_reporting = len(polling_units)
    
    # Calculate aggregated confidence
    if ballots:
        avg_confidence = sum(b.confidence_score for b in ballots) / len(ballots)
        agg.aggregated_confidence = avg_confidence
    
    # Track discrepancies
    agg.ballots_with_discrepancies = sum(1 for b in ballots if b.confidence_score < 0.9)
    agg.discrepancy_rate = (agg.ballots_with_discrepancies / len(ballots)) if ballots else 0.0
    
    # Calculate winners
    if is_party_list:
        # Sort parties by votes
        sorted_parties = sorted(agg.party_totals.items(), key=lambda x: x[1], reverse=True)
        for party_num_str, votes in sorted_parties[:5]:  # Top 5 parties
            info = agg.party_info.get(party_num_str, {})
            percentage = (votes / agg.valid_votes_total * 100) if agg.valid_votes_total > 0 else 0
            agg.winners.append({
                "party_number": party_num_str,
                "name": info.get("name", "Unknown"),
                "abbr": info.get("abbr", ""),
                "votes": votes,
                "percentage": f"{percentage:.2f}%"
            })
    else:
        # Sort candidates by votes
        sorted_candidates = sorted(agg.candidate_totals.items(), key=lambda x: x[1], reverse=True)
        for position, votes in sorted_candidates[:5]:  # Top 5 candidates
            info = agg.candidate_info.get(position, {})
            percentage = (votes / agg.valid_votes_total * 100) if agg.valid_votes_total > 0 else 0
            agg.winners.append({
                "position": position,
                "name": info.get("name", "Unknown"),
                "party": info.get("party_abbr", ""),
                "votes": votes,
                "percentage": f"{percentage:.2f}%"
            })
    
    # Calculate turnout rate (if we have expected total units)
    if agg.total_polling_units > 0:
        agg.turnout_rate = (agg.polling_units_reporting / agg.total_polling_units) * 100
    
    # Track source ballots
    agg.source_ballots = [b.source_file for b in ballots]
    agg.form_types = list(set(b.form_type for b in ballots))
    
    return agg


def generate_constituency_report(agg: AggregatedResults) -> str:
    """
    Generate a detailed markdown report for aggregated constituency results.
    
    Args:
        agg: AggregatedResults object with aggregated data
        
    Returns:
        Formatted markdown report string
    """
    from datetime import datetime
    
    lines = []
    lines.append("# Constituency Results Report")
    lines.append("")
    lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    
    # Header
    lines.append("## Constituency Information")
    lines.append("")
    lines.append("| Field | Value |")
    lines.append("|-------|-------|")
    lines.append(f"| Province | {agg.province} |")
    lines.append(f"| Constituency | {agg.constituency} |")
    lines.append(f"| Constituency # | {agg.constituency_no} |")
    lines.append("")
    
    # Data collection status
    lines.append("## Data Collection Status")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Ballots Processed | {agg.ballots_processed} |")
    lines.append(f"| Polling Units Reporting | {agg.polling_units_reporting} |")
    lines.append(f"| Reporting Rate | {float(agg.turnout_rate or 0):.1f}% |")
    lines.append(f"| Form Types Used | {', '.join(agg.form_types)} |")
    lines.append("")
    
    # Vote totals
    lines.append("## Vote Totals")
    lines.append("")
    lines.append("| Category | Votes |")
    lines.append("|----------|-------|")
    lines.append(f"| Valid Votes | {agg.valid_votes_total} |")
    lines.append(f"| Invalid Votes | {agg.invalid_votes_total} |")
    lines.append(f"| Blank Votes | {agg.blank_votes_total} |")
    lines.append(f"| **Overall Total** | **{agg.overall_total}** |")
    lines.append("")
    
    # Quality metrics
    lines.append("## Data Quality")
    lines.append("")
    confidence_emoji = {
        True: "✓",
        False: "⚠"
    }.get(agg.aggregated_confidence >= 0.95, "?")
    
    lines.append(f"**Aggregated Confidence:** {confidence_emoji} {agg.aggregated_confidence:.1%}")
    lines.append(f"**Discrepancy Rate:** {agg.discrepancy_rate:.1%}")
    lines.append(f"**Ballots with Issues:** {agg.ballots_with_discrepancies}/{agg.ballots_processed}")
    lines.append("")
    
    # Results table
    is_party_list = bool(agg.party_totals)
    
    if is_party_list:
        lines.append("## Party Results")
        lines.append("")
        lines.append("| Party # | Party Name | Abbr | Votes | Percentage |")
        lines.append("|---------|-----------|------|-------|-----------|")
        
        # Sort by votes descending
        sorted_results = sorted(agg.party_totals.items(), key=lambda x: x[1], reverse=True)
        for party_num_str, votes in sorted_results:
            info = agg.party_info.get(party_num_str, {})
            party_name = info.get("name", "Unknown")
            abbr = info.get("abbr", "")
            percentage = (votes / agg.valid_votes_total * 100) if agg.valid_votes_total > 0 else 0
            lines.append(f"| {party_num_str} | {party_name} | {abbr} | {votes} | {percentage:.2f}% |")
        
        lines.append("")
    else:
        lines.append("## Candidate Results")
        lines.append("")
        lines.append("| Pos | Candidate Name | Party | Votes | Percentage |")
        lines.append("|-----|----------------|-------|-------|-----------|")
        
        # Sort by votes descending
        sorted_results = sorted(agg.candidate_totals.items(), key=lambda x: x[1], reverse=True)
        for position, votes in sorted_results:
            info = agg.candidate_info.get(position, {})
            candidate_name = info.get("name", "Unknown")
            party = info.get("party_abbr", "")
            percentage = (votes / agg.valid_votes_total * 100) if agg.valid_votes_total > 0 else 0
            lines.append(f"| {position} | {candidate_name} | {party} | {votes} | {percentage:.2f}% |")
        
        lines.append("")
    
    # Winners
    if agg.winners:
        lines.append("## Winners")
        lines.append("")
        for i, winner in enumerate(agg.winners[:3], 1):
            if is_party_list:
                lines.append(f"**#{i}** {winner['name']} ({winner['abbr']})")
                lines.append(f"  - Votes: {winner['votes']}")
                lines.append(f"  - Percentage: {winner['percentage']}")
            else:
                lines.append(f"**#{i}** {winner['name']} ({winner['party']})")
                lines.append(f"  - Votes: {winner['votes']}")
                lines.append(f"  - Percentage: {winner['percentage']}")
            lines.append("")
    
    # Source information
    lines.append("## Source Information")
    lines.append("")
    lines.append("**Ballots Included:**")
    for source in agg.source_ballots:
        lines.append(f"- {source}")
    lines.append("")
    
    # Footer
    lines.append("---")
    lines.append("")
    
    return "\n".join(lines)


def analyze_constituency_discrepancies(agg: AggregatedResults, ballots: list[BallotData], official_data: Optional[dict] = None) -> dict:
    """
    Analyze discrepancies at the constituency level.
    
    Args:
        agg: AggregatedResults with aggregated votes
        ballots: List of source BallotData objects
        official_data: Optional official results for comparison
        
    Returns:
        Dictionary with discrepancy analysis
    """
    analysis = {
        "constituency": f"{agg.province} - {agg.constituency}",
        "overall_discrepancy_rate": agg.discrepancy_rate,
        "ballots_analyzed": len(ballots),
        "problematic_ballots": [],
        "candidate_variance": {},
        "party_variance": {},
        "recommendations": []
    }
    
    # Analyze each ballot's contribution
    is_party_list = bool(agg.party_totals)
    
    if is_party_list:
        # Party-list analysis
        for ballot in ballots:
            if ballot.confidence_score < 0.9:
                analysis["problematic_ballots"].append({
                    "source": ballot.source_file,
                    "confidence": ballot.confidence_score,
                    "issues": ballot.confidence_details
                })
    else:
        # Constituency analysis
        for ballot in ballots:
            if ballot.confidence_score < 0.9:
                analysis["problematic_ballots"].append({
                    "source": ballot.source_file,
                    "confidence": ballot.confidence_score,
                    "issues": ballot.confidence_details
                })
    
    # Calculate variance by candidate/party if official data available
    if official_data:
        if is_party_list:
            official_parties = official_data.get("party_votes", {})
            for party_num_str, agg_votes in agg.party_totals.items():
                official_votes = official_parties.get(int(party_num_str), 0)
                if official_votes > 0:
                    variance_pct = abs(agg_votes - official_votes) / official_votes * 100
                    severity = "HIGH" if variance_pct > 10 else "MEDIUM" if variance_pct > 5 else "LOW"
                    
                    analysis["party_variance"][party_num_str] = {
                        "extracted": agg_votes,
                        "official": official_votes,
                        "variance_pct": f"{variance_pct:.2f}%",
                        "severity": severity
                    }
        else:
            official_candidates = official_data.get("vote_counts", {})
            for position, agg_votes in agg.candidate_totals.items():
                official_votes = official_candidates.get(position, 0)
                if official_votes > 0:
                    variance_pct = abs(agg_votes - official_votes) / official_votes * 100
                    severity = "HIGH" if variance_pct > 10 else "MEDIUM" if variance_pct > 5 else "LOW"
                    
                    analysis["candidate_variance"][position] = {
                        "extracted": agg_votes,
                        "official": official_votes,
                        "variance_pct": f"{variance_pct:.2f}%",
                        "severity": severity
                    }
    
    # Generate recommendations
    if agg.discrepancy_rate > 0.5:
        analysis["recommendations"].append("⚠ CRITICAL: Over 50% of ballots have discrepancies. Recommend manual review of all ballots.")
    elif agg.discrepancy_rate > 0.25:
        analysis["recommendations"].append("⚠ HIGH: 25-50% of ballots have discrepancies. Recommend review of problematic ballots.")
    elif agg.discrepancy_rate > 0.1:
        analysis["recommendations"].append("⚠ MEDIUM: 10-25% of ballots have minor discrepancies. Recommend spot checks.")
    else:
        analysis["recommendations"].append("✓ LOW: <10% discrepancies. Data quality acceptable.")
    
    if agg.aggregated_confidence < 0.85:
        analysis["recommendations"].append("⚠ Low confidence aggregate. Consider re-extraction.")
    else:
        analysis["recommendations"].append("✓ Good confidence aggregate.")
    
    return analysis


def generate_discrepancy_summary(analyses: list[dict]) -> str:
    """
    Generate a summary report of discrepancies across constituencies.
    
    Args:
        analyses: List of discrepancy analysis dicts from analyze_constituency_discrepancies()
        
    Returns:
        Formatted markdown report string
    """
    from datetime import datetime
    
    lines = []
    lines.append("# Discrepancy Analysis Summary")
    lines.append("")
    lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    
    # Overall statistics
    total_constituencies = len(analyses)
    high_discrepancy = sum(1 for a in analyses if a["overall_discrepancy_rate"] > 0.5)
    medium_discrepancy = sum(1 for a in analyses if 0.25 < a["overall_discrepancy_rate"] <= 0.5)
    low_discrepancy = sum(1 for a in analyses if 0 < a["overall_discrepancy_rate"] <= 0.25)
    no_discrepancy = sum(1 for a in analyses if a["overall_discrepancy_rate"] == 0)
    
    lines.append("## Overall Statistics")
    lines.append("")
    lines.append("| Category | Count | Percentage |")
    lines.append("|----------|-------|-----------|")
    lines.append(f"| Constituencies Analyzed | {total_constituencies} | 100% |")
    lines.append(f"| No Discrepancies | {no_discrepancy} | {no_discrepancy/total_constituencies*100:.1f}% |")
    lines.append(f"| Low Discrepancies | {low_discrepancy} | {low_discrepancy/total_constituencies*100:.1f}% |")
    lines.append(f"| Medium Discrepancies | {medium_discrepancy} | {medium_discrepancy/total_constituencies*100:.1f}% |")
    lines.append(f"| High Discrepancies | {high_discrepancy} | {high_discrepancy/total_constituencies*100:.1f}% |")
    lines.append("")
    
    # Problem areas
    problem_areas = [a for a in analyses if a["overall_discrepancy_rate"] > 0.1]
    if problem_areas:
        lines.append("## Problem Areas")
        lines.append("")
        lines.append(f"> ⚠ **{len(problem_areas)} constituency/ies with >10% discrepancies**")
        lines.append("")
        
        for analysis in sorted(problem_areas, key=lambda x: x["overall_discrepancy_rate"], reverse=True):
            rate = analysis["overall_discrepancy_rate"] * 100
            lines.append(f"### {analysis['constituency']}")
            lines.append(f"**Discrepancy Rate:** {rate:.1f}% ({analysis['ballots_analyzed']} ballots analyzed)")
            
            if analysis["problematic_ballots"]:
                lines.append(f"**Problematic Ballots:** {len(analysis['problematic_ballots'])}")
                for ballot in analysis["problematic_ballots"][:3]:
                    lines.append(f"- {ballot['source']}: {ballot['confidence']:.0%} confidence")
            
            lines.append("")
    
    # Recommendations
    lines.append("## Overall Recommendations")
    lines.append("")
    if high_discrepancy > 0:
        lines.append("⚠ **IMMEDIATE ACTION REQUIRED**")
        lines.append(f"- {high_discrepancy} constituency/ies have >50% discrepancies")
        lines.append("- Recommend manual verification of all ballots in these areas")
    elif medium_discrepancy > 0:
        lines.append("⚠ **REVIEW RECOMMENDED**")
        lines.append(f"- {medium_discrepancy} constituency/ies have 25-50% discrepancies")
        lines.append("- Review problematic ballots and re-extract if needed")
    elif low_discrepancy > 0:
        lines.append("✓ **SPOT CHECKS RECOMMENDED**")
        lines.append(f"- {low_discrepancy} constituency/ies have 10-25% discrepancies")
        lines.append("- Minor issues detected, spot checks recommended")
    else:
        lines.append("✓ **NO ACTION NEEDED**")
        lines.append("- All constituencies have acceptable discrepancy rates")
    
    lines.append("")
    lines.append("---")
    lines.append("")
    
    return "\n".join(lines)


def calculate_vote_statistics(agg: AggregatedResults) -> dict:
    """
    Calculate statistical metrics for aggregated votes.
    
    Args:
        agg: AggregatedResults object
        
    Returns:
        Dictionary with statistics
    """
    import statistics
    
    stats = {
        "vote_distribution": {},
        "outliers": [],
        "anomalies": [],
        "recommendations": []
    }
    
    is_party_list = bool(agg.party_totals)
    votes_list = list(agg.party_totals.values()) if is_party_list else list(agg.candidate_totals.values())
    
    if not votes_list or len(votes_list) < 2:
        return stats
    
    # Calculate basic statistics
    mean_votes = statistics.mean(votes_list)
    median_votes = statistics.median(votes_list)
    stdev_votes = statistics.stdev(votes_list) if len(votes_list) > 1 else 0
    
    stats["vote_distribution"] = {
        "mean": round(mean_votes, 2),
        "median": median_votes,
        "std_dev": round(stdev_votes, 2),
        "min": min(votes_list),
        "max": max(votes_list),
        "range": max(votes_list) - min(votes_list)
    }
    
    # Detect outliers using IQR method
    if len(votes_list) >= 4:
        sorted_votes = sorted(votes_list)
        q1_idx = len(sorted_votes) // 4
        q3_idx = (3 * len(sorted_votes)) // 4
        q1 = sorted_votes[q1_idx]
        q3 = sorted_votes[q3_idx]
        iqr = q3 - q1
        
        lower_bound = q1 - 1.5 * iqr
        upper_bound = q3 + 1.5 * iqr
        
        if is_party_list:
            for party_num_str, votes in agg.party_totals.items():
                if votes < lower_bound or votes > upper_bound:
                    info = agg.party_info.get(party_num_str, {})
                    stats["outliers"].append({
                        "party_number": party_num_str,
                        "party_name": info.get("name", "Unknown"),
                        "votes": votes,
                        "type": "LOW" if votes < lower_bound else "HIGH",
                        "severity": "MEDIUM"
                    })
        else:
            for position, votes in agg.candidate_totals.items():
                if votes < lower_bound or votes > upper_bound:
                    info = agg.candidate_info.get(position, {})
                    stats["outliers"].append({
                        "position": position,
                        "candidate_name": info.get("name", "Unknown"),
                        "votes": votes,
                        "type": "LOW" if votes < lower_bound else "HIGH",
                        "severity": "MEDIUM"
                    })
    
    # Detect anomalies (unusual patterns)
    if agg.valid_votes_total > 0:
        if is_party_list:
            for party_num_str, votes in agg.party_totals.items():
                vote_pct = (votes / agg.valid_votes_total) * 100
                
                # Anomaly: One party gets >80% of votes
                if vote_pct > 80:
                    info = agg.party_info.get(party_num_str, {})
                    stats["anomalies"].append({
                        "type": "EXTREME_CONCENTRATION",
                        "party_number": party_num_str,
                        "party_name": info.get("name", "Unknown"),
                        "percentage": f"{vote_pct:.1f}%",
                        "severity": "HIGH",
                        "description": f"Party {party_num_str} received {vote_pct:.1f}% of votes"
                    })
                
                # Anomaly: Zero votes (could indicate missing data or no support)
                if votes == 0 and len(agg.party_totals) > 10:
                    info = agg.party_info.get(party_num_str, {})
                    stats["anomalies"].append({
                        "type": "ZERO_VOTES",
                        "party_number": party_num_str,
                        "party_name": info.get("name", "Unknown"),
                        "votes": 0,
                        "severity": "LOW",
                        "description": f"Party {party_num_str} received zero votes"
                    })
        else:
            for position, votes in agg.candidate_totals.items():
                vote_pct = (votes / agg.valid_votes_total) * 100
                
                # Anomaly: One candidate gets >75% of votes
                if vote_pct > 75:
                    info = agg.candidate_info.get(position, {})
                    stats["anomalies"].append({
                        "type": "EXTREME_CONCENTRATION",
                        "position": position,
                        "candidate_name": info.get("name", "Unknown"),
                        "percentage": f"{vote_pct:.1f}%",
                        "severity": "MEDIUM",
                        "description": f"Position {position} received {vote_pct:.1f}% of votes"
                    })
    
    # Generate recommendations based on statistics
    if stats["outliers"]:
        stats["recommendations"].append(f"⚠ {len(stats['outliers'])} outlier(s) detected. Recommend spot checks.")
    
    if any(a["severity"] == "HIGH" for a in stats["anomalies"]):
        stats["recommendations"].append("⚠ High-severity anomalies detected. Manual review recommended.")
    
    if stdev_votes > mean_votes * 0.5:
        stats["recommendations"].append("⚠ High variance in vote distribution. Verify data consistency.")
    
    if not stats["recommendations"]:
        stats["recommendations"].append("✓ Vote distribution looks normal. No anomalies detected.")
    
    return stats


def detect_anomalous_constituencies(results: dict[tuple, AggregatedResults]) -> list[dict]:
    """
    Identify constituencies with statistical anomalies.
    
    Args:
        results: Dictionary of (province, cons_no) -> AggregatedResults
        
    Returns:
        List of anomaly reports
    """
    anomalies = []
    
    for key, agg in results.items():
        stats = calculate_vote_statistics(agg)
        
        # Check for issues
        if stats["outliers"] or stats["anomalies"] or any("High" in rec or "high" in rec for rec in stats["recommendations"]):
            anomalies.append({
                "constituency": f"{agg.province} - {agg.constituency}",
                "statistics": stats,
                "severity": max(
                    (a.get("severity", "LOW") for a in stats["anomalies"]), 
                    default="LOW"
                ),
                "issue_count": len(stats["outliers"]) + len(stats["anomalies"])
            })
    
    return sorted(anomalies, key=lambda x: x["issue_count"], reverse=True)


def generate_anomaly_report(anomalies: list[dict]) -> str:
    """
    Generate a report of detected anomalies.
    
    Args:
        anomalies: List of anomaly dicts from detect_anomalous_constituencies()
        
    Returns:
        Formatted markdown report string
    """
    from datetime import datetime
    
    lines = []
    lines.append("# Statistical Anomaly Report")
    lines.append("")
    lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    
    if not anomalies:
        lines.append("## No Anomalies Detected")
        lines.append("")
        lines.append("✓ All constituencies show normal statistical patterns.")
        lines.append("")
        return "\n".join(lines)
    
    lines.append("## Summary")
    lines.append("")
    lines.append(f"**Constituencies with Anomalies:** {len(anomalies)}")
    lines.append("")
    
    # Severity breakdown
    high_severity = sum(1 for a in anomalies if a["severity"] == "HIGH")
    medium_severity = sum(1 for a in anomalies if a["severity"] == "MEDIUM")
    low_severity = sum(1 for a in anomalies if a["severity"] == "LOW")
    
    lines.append("| Severity | Count |")
    lines.append("|----------|-------|")
    lines.append(f"| HIGH | {high_severity} |")
    lines.append(f"| MEDIUM | {medium_severity} |")
    lines.append(f"| LOW | {low_severity} |")
    lines.append("")
    
    # Detailed anomalies
    lines.append("## Detailed Anomalies")
    lines.append("")
    
    for anomaly in anomalies:
        lines.append(f"### {anomaly['constituency']}")
        lines.append(f"**Severity:** {anomaly['severity']} ({anomaly['issue_count']} issues)")
        lines.append("")
        
        stats = anomaly["statistics"]
        
        # Vote distribution stats
        if stats["vote_distribution"]:
            dist = stats["vote_distribution"]
            lines.append("**Vote Distribution:**")
            lines.append(f"- Mean: {dist['mean']} votes")
            lines.append(f"- Median: {dist['median']} votes")
            lines.append(f"- Std Dev: {dist['std_dev']}")
            lines.append(f"- Range: {dist['min']} - {dist['max']} ({dist['range']} spread)")
            lines.append("")
        
        # Outliers
        if stats["outliers"]:
            lines.append("**Outliers Detected:**")
            for outlier in stats["outliers"]:
                if "party_number" in outlier:
                    lines.append(f"- Party #{outlier['party_number']}: {outlier['votes']} votes ({outlier['type']})")
                else:
                    lines.append(f"- Position {outlier['position']}: {outlier['votes']} votes ({outlier['type']})")
            lines.append("")
        
        # Anomalies
        if stats["anomalies"]:
            lines.append("**Pattern Anomalies:**")
            for anomaly_item in stats["anomalies"]:
                lines.append(f"- [{anomaly_item['severity']}] {anomaly_item['description']}")
            lines.append("")
        
        # Recommendations
        if stats["recommendations"]:
            lines.append("**Recommendations:**")
            for rec in stats["recommendations"]:
                lines.append(f"- {rec}")
            lines.append("")
    
    # Footer
    lines.append("---")
    lines.append("")
    lines.append("## Next Steps")
    lines.append("")
    if high_severity > 0:
        lines.append("⚠ **IMMEDIATE ACTION REQUIRED**")
        lines.append(f"- {high_severity} constituency/ies with HIGH severity anomalies")
        lines.append("- Recommend manual verification of these areas")
    elif medium_severity > 0:
        lines.append("⚠ **REVIEW RECOMMENDED**")
        lines.append(f"- {medium_severity} constituency/ies with MEDIUM severity anomalies")
        lines.append("- Verify vote data and polling station reports")
    else:
        lines.append("✓ **ROUTINE CHECKS SUFFICIENT**")
        lines.append("- Low severity anomalies detected")
        lines.append("- Standard verification procedures recommended")
    
    lines.append("")
    
    return "\n".join(lines)


def generate_province_report(province_results: list[AggregatedResults], anomalies: list[dict]) -> str:
    """
    Generate a comprehensive province-level report.
    
    Args:
        province_results: List of AggregatedResults for all constituencies in province
        anomalies: List of anomaly dicts from detect_anomalous_constituencies()
        
    Returns:
        Formatted markdown report string
    """
    from datetime import datetime
    
    if not province_results:
        return "No results to report"
    
    province_name = province_results[0].province
    
    lines = []
    lines.append("# Province Electoral Report")
    lines.append("")
    lines.append(f"**Province:** {province_name}")
    lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    
    # Overview
    lines.append("## Overview")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Constituencies Reporting | {len(province_results)} |")
    lines.append(f"| Total Valid Votes | {sum(r.valid_votes_total for r in province_results)} |")
    lines.append(f"| Total Invalid Votes | {sum(r.invalid_votes_total for r in province_results)} |")
    lines.append(f"| Overall Total Votes | {sum(r.overall_total for r in province_results)} |")
    lines.append(f"| Average Confidence | {(sum(r.aggregated_confidence for r in province_results) / len(province_results) * 100):.1f}% |")
    lines.append("")
    
    # Data quality
    lines.append("## Data Quality Summary")
    lines.append("")
    high_conf = sum(1 for r in province_results if r.aggregated_confidence >= 0.95)
    med_conf = sum(1 for r in province_results if 0.85 <= r.aggregated_confidence < 0.95)
    low_conf = sum(1 for r in province_results if r.aggregated_confidence < 0.85)
    
    lines.append("**Confidence Levels:**")
    lines.append(f"- High (95%+): {high_conf} constituencies")
    lines.append(f"- Medium (85-95%): {med_conf} constituencies")
    lines.append(f"- Low (<85%): {low_conf} constituencies")
    lines.append("")
    
    # Anomalies in this province
    province_anomalies = [a for a in anomalies if province_name in a["constituency"]]
    if province_anomalies:
        lines.append(f"**Anomalies Detected:** {len(province_anomalies)} constituency/ies")
        lines.append("")
    
    # Constituency breakdown
    lines.append("## Constituency Results")
    lines.append("")
    lines.append("| # | Constituency | Valid Votes | Invalid | Confidence | Status |")
    lines.append("|---|--------------|------------|---------|-----------|--------|")
    
    for i, result in enumerate(province_results, 1):
        # Determine status
        if result.aggregated_confidence >= 0.95:
            status = "✓"
        elif result.aggregated_confidence >= 0.85:
            status = "⚠"
        else:
            status = "✗"
        
        # Check for anomalies
        has_anomaly = any(result.constituency in a["constituency"] for a in province_anomalies)
        if has_anomaly:
            status += " ⚠"
        
        lines.append(f"| {i} | {result.constituency} | {result.valid_votes_total} | {result.invalid_votes_total} | {result.aggregated_confidence:.0%} | {status} |")
    
    lines.append("")
    
    # Recommendations
    lines.append("## Recommendations")
    lines.append("")
    if low_conf > 0 or province_anomalies:
        if low_conf > 0:
            lines.append(f"⚠ **{low_conf}** constituency/ies with confidence <85%. Manual review recommended.")
        if province_anomalies:
            lines.append(f"⚠ **{len(province_anomalies)}** constituency/ies with detected anomalies.")
        if high_conf == len(province_results):
            lines.append("✓ All other constituencies show good data quality.")
    else:
        lines.append("✓ All constituencies show good data quality.")
    
    lines.append("")
    
    return "\n".join(lines)


def generate_executive_summary(
    all_results: list[AggregatedResults],
    anomalies: list[dict],
    provinces: Optional[list[str]] = None
) -> str:
    """
    Generate an executive summary report.
    
    Args:
        all_results: All AggregatedResults from all constituencies
        anomalies: All detected anomalies
        provinces: Optional list of provinces (auto-detected if None)
        
    Returns:
        Formatted markdown report string
    """
    from datetime import datetime
    
    if not all_results:
        return "No results to summarize"
    
    # Detect provinces if not provided
    if provinces is None:
        provinces = sorted(set(r.province for r in all_results))
    
    lines = []
    lines.append("# Electoral Results - Executive Summary")
    lines.append("")
    lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    
    # Key statistics
    total_valid = sum(r.valid_votes_total for r in all_results)
    total_invalid = sum(r.invalid_votes_total for r in all_results)
    total_blank = sum(r.blank_votes_total for r in all_results)
    total_votes = sum(r.overall_total for r in all_results)
    avg_confidence = (sum(r.aggregated_confidence for r in all_results) / len(all_results)) if all_results else 0
    
    lines.append("## Key Statistics")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Total Constituencies | {len(all_results)} |")
    lines.append(f"| Total Provinces | {len(provinces)} |")
    lines.append(f"| Total Valid Votes | {total_valid:,} |")
    lines.append(f"| Total Invalid Votes | {total_invalid:,} |")
    lines.append(f"| Total Blank Votes | {total_blank:,} |")
    lines.append(f"| **Overall Total** | **{total_votes:,}** |")
    lines.append(f"| Average Confidence | {avg_confidence:.1%} |")
    lines.append("")
    
    # Data quality assessment
    lines.append("## Data Quality Assessment")
    lines.append("")
    
    if avg_confidence >= 0.95:
        quality_rating = "EXCELLENT"
        quality_emoji = "✓✓✓"
    elif avg_confidence >= 0.85:
        quality_rating = "GOOD"
        quality_emoji = "✓✓"
    elif avg_confidence >= 0.75:
        quality_rating = "ACCEPTABLE"
        quality_emoji = "✓"
    else:
        quality_rating = "POOR"
        quality_emoji = "✗"
    
    lines.append(f"**Overall Rating:** {quality_emoji} {quality_rating}")
    lines.append(f"**Average Confidence:** {avg_confidence:.1%}")
    lines.append("")
    
    # Province summary
    lines.append("## By Province")
    lines.append("")
    lines.append("| Province | Constituencies | Valid Votes | Avg Confidence |")
    lines.append("|----------|---|---|---|")
    
    for province in provinces:
        prov_results = [r for r in all_results if r.province == province]
        if prov_results:
            prov_valid = sum(r.valid_votes_total for r in prov_results)
            prov_conf = sum(r.aggregated_confidence for r in prov_results) / len(prov_results)
            lines.append(f"| {province} | {len(prov_results)} | {prov_valid:,} | {prov_conf:.1%} |")
    
    lines.append("")
    
    # Top winners (if constituency results)
    is_party_list = bool(all_results[0].party_totals) if all_results else False
    if not is_party_list and all_results:
        lines.append("## Top Candidates Overall")
        lines.append("")
        
        # Aggregate all candidates
        all_winners = []
        for result in all_results:
            for winner in result.winners:
                all_winners.append({
                    "name": winner["name"],
                    "province": result.province,
                    "votes": winner["votes"],
                    "percentage": winner["percentage"]
                })
        
        # Sort by votes
        top_winners = sorted(all_winners, key=lambda x: x["votes"], reverse=True)[:10]
        
        lines.append("| Rank | Candidate | Province | Votes | Percentage |")
        lines.append("|------|-----------|----------|-------|-----------|")
        
        for i, winner in enumerate(top_winners, 1):
            lines.append(f"| {i} | {winner['name']} | {winner['province']} | {winner['votes']:,} | {winner['percentage']} |")
        
        lines.append("")
    
    # Issues and recommendations
    lines.append("## Issues & Recommendations")
    lines.append("")
    
    if anomalies:
        lines.append(f"⚠ **{len(anomalies)}** constituency/ies with detected anomalies")
        lines.append("")
    
    high_anomalies = [a for a in anomalies if a["severity"] == "HIGH"]
    medium_anomalies = [a for a in anomalies if a["severity"] == "MEDIUM"]
    
    if high_anomalies:
        lines.append(f"**CRITICAL ISSUES ({len(high_anomalies)}):**")
        for anom in high_anomalies[:5]:
            lines.append(f"- {anom['constituency']}")
        lines.append("")
    
    if medium_anomalies:
        lines.append(f"**NEEDS REVIEW ({len(medium_anomalies)}):**")
        for anom in medium_anomalies[:5]:
            lines.append(f"- {anom['constituency']}")
        lines.append("")
    
    # Final recommendations
    if avg_confidence < 0.85:
        lines.append("⚠ **Low average confidence.** Consider re-verification of data.")
    elif len(anomalies) > len(all_results) * 0.2:
        lines.append("⚠ **High anomaly rate.** Manual review of flagged constituencies recommended.")
    else:
        lines.append("✓ **Data quality acceptable.** Proceed with standard verification process.")
    
    lines.append("")
    lines.append("---")
    lines.append("")
    
    return "\n".join(lines)


def verify_with_ect_data(ballot_data: BallotData, ect_api_url: str) -> dict:
    """
    Compare extracted ballot data with official ECT API data.
    """

    def add_discrepancy(result_obj: dict, severity: str, disc_type: str, **payload) -> None:
        """Append discrepancy and update severity summary counters."""
        result_obj["discrepancies"].append({
            "type": disc_type,
            "severity": severity,
            **payload,
        })
        counter_key = f"{severity.lower()}_severity"
        if counter_key in result_obj["summary"]:
            result_obj["summary"][counter_key] += 1

    def finalize_status(result_obj: dict, official_checked: bool) -> None:
        """Set overall status based on discrepancy severity."""
        if result_obj["summary"]["high_severity"] > 0:
            result_obj["status"] = "discrepancies_found_high"
        elif result_obj["summary"]["medium_severity"] > 0:
            result_obj["status"] = "discrepancies_found_medium"
        elif result_obj["summary"]["low_severity"] > 0:
            result_obj["status"] = "discrepancies_found_low"
        elif official_checked:
            result_obj["status"] = "verified"
        else:
            result_obj["status"] = "pending_official_data"

    def get_candidate_info(position: int) -> dict:
        """Fetch candidate metadata regardless of int/str key format."""
        return ballot_data.candidate_info.get(position) or ballot_data.candidate_info.get(str(position), {})

    result = {
        "form_type": ballot_data.form_type,
        "polling_station": ballot_data.polling_station_id,
        "ballot_data": {
            "form_type": ballot_data.form_type,
            "form_category": ballot_data.form_category,
            "polling_station": ballot_data.polling_station_id,
            "province": ballot_data.province,
            "constituency_number": ballot_data.constituency_number,
            "polling_unit": ballot_data.polling_unit,
            "total_votes": ballot_data.total_votes,
        },
        "ect_data": {
            "province": None,
            "province_abbr": None,
            "constituency_id": None,
            "constituency_vote_stations": None,
            "vote_counts": {},
            "party_votes": {},
            "total_votes": None,
            "official_results_available": False,
            "candidate_info": {},
            "party_info": {},
        },
        "discrepancies": [],
        "summary": {
            "high_severity": 0,
            "medium_severity": 0,
            "low_severity": 0,
            "matches": 0,
        },
        "status": "pending_ect_data",
    }

    # Add appropriate vote data based on form type
    if ballot_data.form_category == "party_list":
        result["ballot_data"]["party_votes"] = ballot_data.party_votes
    else:
        result["ballot_data"]["vote_counts"] = ballot_data.vote_counts

    if not ECT_AVAILABLE:
        return result

    try:
        official_checked = False
        cons_id = None
        province_valid, canonical_province = ect_data.validate_province_name(ballot_data.province)
        if province_valid and canonical_province:
            result["ect_data"]["province"] = canonical_province
            result["summary"]["matches"] += 1
        else:
            add_discrepancy(
                result,
                "HIGH",
                "province_reference",
                extracted=ballot_data.province,
                expected="valid ECT province",
            )

        province_for_lookup = canonical_province or ballot_data.province
        province_abbr = ect_data.get_province_abbr(province_for_lookup)
        if province_abbr:
            result["ect_data"]["province_abbr"] = province_abbr
            result["summary"]["matches"] += 1
        else:
            add_discrepancy(
                result,
                "HIGH",
                "province_abbr_lookup",
                extracted=province_for_lookup,
                expected="valid province abbreviation",
            )

        # Constituency-level structural checks for forms that contain constituency ID.
        if ballot_data.constituency_number and province_abbr:
            cons_id = f"{province_abbr}_{ballot_data.constituency_number}"
            constituency = ect_data.get_constituency(cons_id)
            result["ect_data"]["constituency_id"] = cons_id
            if constituency:
                result["summary"]["matches"] += 1
                result["ect_data"]["constituency_vote_stations"] = constituency.total_vote_stations
                if ballot_data.polling_unit > 0 and constituency.total_vote_stations > 0:
                    if ballot_data.polling_unit <= constituency.total_vote_stations:
                        result["summary"]["matches"] += 1
                    else:
                        add_discrepancy(
                            result,
                            "HIGH",
                            "polling_unit_range",
                            extracted=ballot_data.polling_unit,
                            expected=f"1-{constituency.total_vote_stations}",
                        )
            else:
                add_discrepancy(
                    result,
                    "HIGH",
                    "constituency_reference",
                    extracted=cons_id,
                    expected="existing ECT constituency",
                )

        # If official constituency results are available, compare extracted votes directly.
        if cons_id:
            official_results = ect_data.get_official_constituency_results(cons_id)
            if official_results:
                official_checked = True
                result["ect_data"]["official_results_available"] = True
                result["ect_data"]["vote_counts"] = official_results.get("vote_counts", {})
                result["ect_data"]["party_votes"] = official_results.get("party_votes", {})
                result["ect_data"]["total_votes"] = official_results.get("total")

                vote_report = detect_discrepancies(ballot_data, official_results)
                result["summary"]["matches"] += vote_report.get("summary", {}).get("matches", 0)
                for discrepancy in vote_report.get("discrepancies", []):
                    result["discrepancies"].append(discrepancy)
                    severity = discrepancy.get("severity", "LOW")
                    counter_key = f"{severity.lower()}_severity"
                    if counter_key in result["summary"]:
                        result["summary"][counter_key] += 1

        if ballot_data.form_category == "party_list":
            for party_no_str, extracted_votes in ballot_data.party_votes.items():
                if not str(party_no_str).isdigit():
                    add_discrepancy(
                        result,
                        "MEDIUM",
                        "party_number_format",
                        extracted=party_no_str,
                        expected="numeric party number",
                    )
                    continue

                party = ect_data.get_party_by_number(int(party_no_str))
                if party:
                    result["summary"]["matches"] += 1
                    result["ect_data"]["party_info"][str(party_no_str)] = {
                        "name": party.name,
                        "abbr": party.abbr,
                        "extracted_votes": extracted_votes,
                    }
                else:
                    add_discrepancy(
                        result,
                        "MEDIUM",
                        "party_reference_missing",
                        party_number=int(party_no_str),
                        extracted_votes=extracted_votes,
                        expected="known ECT party",
                    )
        else:
            for position, extracted_votes in ballot_data.vote_counts.items():
                candidate = ect_data.get_candidate_by_thai_province(
                    ballot_data.province,
                    ballot_data.constituency_number,
                    int(position),
                )
                if not candidate:
                    add_discrepancy(
                        result,
                        "MEDIUM",
                        "candidate_reference_missing",
                        position=int(position),
                        extracted_votes=extracted_votes,
                        expected="known ECT candidate",
                    )
                    continue

                result["summary"]["matches"] += 1
                party = ect_data.get_party_for_candidate(candidate)
                party_abbr = party.abbr if party else ""
                result["ect_data"]["candidate_info"][str(position)] = {
                    "name": candidate.mp_app_name,
                    "party_abbr": party_abbr,
                    "extracted_votes": extracted_votes,
                }

                extracted_candidate = get_candidate_info(int(position))
                extracted_name = extracted_candidate.get("name")
                if extracted_name and extracted_name != candidate.mp_app_name:
                    add_discrepancy(
                        result,
                        "LOW",
                        "candidate_name_mismatch",
                        position=int(position),
                        extracted=extracted_name,
                        expected=candidate.mp_app_name,
                    )
                elif extracted_name:
                    result["summary"]["matches"] += 1

                extracted_party_abbr = extracted_candidate.get("party_abbr")
                if extracted_party_abbr and party_abbr and extracted_party_abbr != party_abbr:
                    add_discrepancy(
                        result,
                        "LOW",
                        "candidate_party_mismatch",
                        position=int(position),
                        extracted=extracted_party_abbr,
                        expected=party_abbr,
                    )
                elif extracted_party_abbr and party_abbr:
                    result["summary"]["matches"] += 1

        finalize_status(result, official_checked)
    except Exception as exc:
        add_discrepancy(
            result,
            "HIGH",
            "ect_verification_error",
            message=str(exc),
        )
        finalize_status(result, official_checked=False)

    return result


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Extract and verify ballot data")
    parser.add_argument("input", help="PDF, image file, or directory to process")
    parser.add_argument("--output", "-o", help="Output JSON file", default="ballot_data.json")
    parser.add_argument("--verify", action="store_true", help="Verify against ECT API")
    parser.add_argument("--batch", "-b", action="store_true", help="Process directory of images")
    parser.add_argument("--reports", "-r", action="store_true", help="Generate markdown reports")
    parser.add_argument("--pdf", "-p", action="store_true", help="Generate PDF reports")
    parser.add_argument("--aggregate", "-a", action="store_true", help="Aggregate results by constituency")
    parser.add_argument("--report-dir", default="reports", help="Directory to save reports")
    parser.add_argument("--parallel", action="store_true", help="Enable parallel processing with ThreadPoolExecutor")
    parser.add_argument("--workers", type=int, default=5, help="Number of concurrent workers for parallel processing (default: 5)")

    args = parser.parse_args()

    input_path = args.input

    # Determine what to process
    if os.path.isdir(input_path) or args.batch:
        # Process directory of images and/or PDFs
        images = []
        pdfs = []

        # Find all images
        for ext in ["*.png", "*.jpg", "*.jpeg"]:
            images.extend(sorted(Path(input_path).glob(ext)))

        # Find all PDFs recursively
        for root, dirs, files in os.walk(input_path):
            for f in files:
                if f.lower().endswith('.pdf'):
                    pdfs.append(os.path.join(root, f))

        if not images and not pdfs:
            print(f"No images or PDFs found in {input_path}")
            return

        print(f"Found {len(images)} images and {len(pdfs)} PDFs in {input_path}")

        # Convert PDFs to images
        if pdfs:
            temp_dir = "/tmp/ballot_images"
            os.makedirs(temp_dir, exist_ok=True)
            print(f"\nConverting {len(pdfs)} PDFs to images...")
            for pdf_path in pdfs:
                try:
                    pdf_images = pdf_to_images(pdf_path, temp_dir)
                    images.extend([Path(img) for img in pdf_images])
                    print(f"  {os.path.basename(pdf_path)}: {len(pdf_images)} pages")
                except Exception as e:
                    print(f"  {os.path.basename(pdf_path)}: ERROR - {e}")

        print(f"\nTotal images to process: {len(images)}")
    elif input_path.lower().endswith(".pdf"):
        # Create temp directory for images if PDF
        temp_dir = "/tmp/ballot_images"
        os.makedirs(temp_dir, exist_ok=True)
        print("Converting PDF to images...")
        images = pdf_to_images(input_path, temp_dir)
        print(f"Created {len(images)} images")
    else:
        images = [input_path]

    # Create report directory if needed
    if args.reports:
        os.makedirs(args.report_dir, exist_ok=True)

    # Process images (parallel or sequential)
    results = []
    ballot_data_list = []
    processing_errors = []

    if args.parallel and len(images) > 1:
        # Use BatchProcessor for parallel processing
        print(f"\nProcessing {len(images)} images in parallel with {args.workers} workers...")
        from batch_processor import BatchProcessor
        processor = BatchProcessor(max_workers=args.workers, rate_limit=2.0)
        batch_result = processor.process_batch([str(img) for img in images])

        ballot_data_list = batch_result.results
        processing_errors = batch_result.errors

        if processing_errors:
            print(f"\nWarning: {len(processing_errors)} images failed to process")
            for err in processing_errors:
                print(f"  - {err['path']}: {err['error']}")

        print(f"\nSuccessfully processed {batch_result.processed}/{batch_result.total} images")
    else:
        # Sequential processing (default)
        for i, image_path in enumerate(images, 1):
            print(f"\nProcessing: {image_path}")
            ballot_data = extract_ballot_data_with_ai(image_path)
            if ballot_data:
                ballot_data_list.append(ballot_data)

    # Process results (verification and reporting)
    for i, ballot_data in enumerate(ballot_data_list, 1):
        print(f"\nResult {i}: {ballot_data.source_file}")
        print(f"  Form type: {ballot_data.form_type}")
        print(f"  Category: {ballot_data.form_category}")
        print(f"  Station: {ballot_data.polling_station_id}")
        if ballot_data.form_category == "party_list":
            print(f"  Party votes: {ballot_data.party_votes}")
        else:
            print(f"  Vote counts: {ballot_data.vote_counts}")
        print(f"  Total: {ballot_data.total_votes}")

        discrepancy_report = None

        if args.verify:
            verification = verify_with_ect_data(ballot_data, "")
            results.append(verification)
            discrepancy_report = verification
        else:
            result = {
                "form_type": ballot_data.form_type,
                "form_category": ballot_data.form_category,
                "province": ballot_data.province,
                "constituency_number": ballot_data.constituency_number,
                "district": ballot_data.district,
                "polling_unit": ballot_data.polling_unit,
                "polling_station": ballot_data.polling_station_id,
                "valid_votes": ballot_data.valid_votes,
                "invalid_votes": ballot_data.invalid_votes,
                "blank_votes": ballot_data.blank_votes,
                "total_votes": ballot_data.total_votes,
                "confidence_score": ballot_data.confidence_score,
                "confidence_level": ballot_data.confidence_details.get("level", "UNKNOWN"),
                "source_file": ballot_data.source_file,
            }
            if ballot_data.form_category == "party_list":
                result["page_parties"] = ballot_data.page_parties
                result["party_votes"] = ballot_data.party_votes
                if ballot_data.party_info:
                    result["party_info"] = ballot_data.party_info
            else:
                result["vote_counts"] = ballot_data.vote_counts
                if ballot_data.candidate_info:
                    result["candidate_info"] = ballot_data.candidate_info
            results.append(result)

        # Generate individual report if requested
        if args.reports:
            report_filename = f"{args.report_dir}/ballot_{i:03d}.md"
            report = generate_single_ballot_report(ballot_data, discrepancy_report=discrepancy_report)
            save_report(report, report_filename)

            # Also generate PDF if requested
            if args.pdf:
                pdf_filename = f"{args.report_dir}/ballot_{i:03d}.pdf"
                generate_ballot_pdf(ballot_data, pdf_filename)

    # Save results
    with open(args.output, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\nResults saved to: {args.output}")

    # Aggregate results by constituency if requested (do this first so batch PDF can use it)
    aggregated_results = {}
    if args.aggregate and len(ballot_data_list) > 1:
        print("\nAggregating results by constituency...")
        aggregated_results = aggregate_ballot_results(ballot_data_list)

        # Save aggregated results
        aggregated_output = args.output.replace('.json', '_aggregated.json')
        aggregated_data = {}
        for (province, cons_no), agg in aggregated_results.items():
            key = f"{province}_{cons_no}"
            aggregated_data[key] = {
                "province": agg.province,
                "constituency": agg.constituency,
                "constituency_no": agg.constituency_no,
                "ballots_processed": agg.ballots_processed,
                "polling_units_reporting": agg.polling_units_reporting,
                "valid_votes_total": agg.valid_votes_total,
                "invalid_votes_total": agg.invalid_votes_total,
                "blank_votes_total": agg.blank_votes_total,
                "overall_total": agg.overall_total,
                "aggregated_confidence": agg.aggregated_confidence,
                "discrepancy_rate": agg.discrepancy_rate,
                "winners": agg.winners,
            }
            if agg.candidate_totals:
                aggregated_data[key]["candidate_totals"] = agg.candidate_totals
            if agg.party_totals:
                aggregated_data[key]["party_totals"] = agg.party_totals

        with open(aggregated_output, "w") as f:
            json.dump(aggregated_data, f, indent=2, ensure_ascii=False)
        print(f"Aggregated results saved to: {aggregated_output}")

        # Generate constituency reports and PDFs
        for (province, cons_no), agg in aggregated_results.items():
            cons_key = f"{province}_{cons_no}"

            if args.reports:
                # Markdown report
                cons_report = generate_constituency_report(agg)
                cons_report_filename = f"{args.report_dir}/constituency_{cons_key}.md"
                save_report(cons_report, cons_report_filename)
                print(f"Constituency report saved to: {cons_report_filename}")

            if args.pdf:
                # PDF report
                cons_pdf_filename = f"{args.report_dir}/constituency_{cons_key}.pdf"
                generate_constituency_pdf(agg, cons_pdf_filename)

        # Generate executive summary PDF if requested
        if args.pdf and len(aggregated_results) > 1:
            all_agg_results = list(aggregated_results.values())
            anomalies = detect_anomalous_constituencies(aggregated_results)
            exec_summary_pdf = f"{args.report_dir}/EXECUTIVE_SUMMARY.pdf"
            generate_executive_summary_pdf(all_agg_results, anomalies, exec_summary_pdf)

    # Generate batch report if requested and multiple ballots
    if args.reports and len(ballot_data_list) > 1:
        batch_report_filename = f"{args.report_dir}/BATCH_SUMMARY.md"
        batch_report = generate_batch_report(results, ballot_data_list)
        save_report(batch_report, batch_report_filename)
        print(f"Batch report saved to: {batch_report_filename}")

        # Also generate batch PDF if requested (with charts if aggregated data available)
        if args.pdf:
            batch_pdf_filename = f"{args.report_dir}/BATCH_SUMMARY.pdf"
            generate_batch_pdf(aggregated_results, ballot_data_list, batch_pdf_filename)


if __name__ == "__main__":
    main()
