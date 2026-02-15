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
from typing import Optional
from enum import Enum

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


def validate_vote_entry(numeric: int, thai_text: str) -> VoteEntry:
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
    total_votes: int = 0
    valid_votes: int = 0
    invalid_votes: int = 0
    blank_votes: int = 0  # บัตรไม่ประสงค์ลงคะแนน
    source_file: str = ""
    confidence_score: float = 0.0  # 0.0 to 1.0
    confidence_details: dict = field(default_factory=dict)  # Breakdown of confidence factors


def pdf_to_images(pdf_path: str, output_dir: str, dpi: int = 150) -> list[str]:
    """Convert PDF to PNG images using pdftoppm."""
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
                }
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
            print(f"  ✓ Sum matches valid votes")

        if reported_total and reported_valid:
            expected_total = reported_valid + reported_invalid + reported_blank
            if reported_total != expected_total:
                print(f"  WARNING: Total mismatch! Expected: {expected_total} (valid+invalid+blank), Reported: {reported_total}")
            else:
                print(f"  ✓ Total = Valid + Invalid + Blank")

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

        # Validate party numbers against ECT data (for party-list forms)
        if is_party_list and ECT_AVAILABLE:
            for party_num in party_votes.keys():
                party = ect_data.get_party(party_num)
                if party:
                    print(f"  Party #{party_num}: {party.name} ({party.abbr})")
                else:
                    print(f"  WARNING: Party #{party_num} not found in ECT data")

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
            total_votes=reported_total or calculated_sum,
            valid_votes=reported_valid or calculated_sum,
            invalid_votes=reported_invalid,
            blank_votes=reported_blank,
            source_file=image_path,
            confidence_score=confidence_score,
            confidence_details=confidence_details,
        )

    except Exception as e:
        print(f"Error processing extracted data: {e}")
        return None


def verify_with_ect_data(ballot_data: BallotData, ect_api_url: str) -> dict:
    """
    Compare extracted ballot data with official ECT API data.

    TODO: Implement ECT API integration.
    For now, return a placeholder structure.
    """
    result = {
        "ballot_data": {
            "form_type": ballot_data.form_type,
            "form_category": ballot_data.form_category,
            "polling_station": ballot_data.polling_station_id,
            "total_votes": ballot_data.total_votes,
        },
        "ect_data": {
            # Will be populated from ECT API
            "vote_counts": {},
            "total_votes": 0,
        },
        "discrepancies": [],
        "status": "pending_ect_data",
    }

    # Add appropriate vote data based on form type
    if ballot_data.form_category == "party_list":
        result["ballot_data"]["party_votes"] = ballot_data.party_votes
    else:
        result["ballot_data"]["vote_counts"] = ballot_data.vote_counts

    return result


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Extract and verify ballot data")
    parser.add_argument("input", help="PDF, image file, or directory to process")
    parser.add_argument("--output", "-o", help="Output JSON file", default="ballot_data.json")
    parser.add_argument("--verify", action="store_true", help="Verify against ECT API")
    parser.add_argument("--batch", "-b", action="store_true", help="Process directory of images")

    args = parser.parse_args()

    input_path = args.input

    # Determine what to process
    if os.path.isdir(input_path) or args.batch:
        # Process directory of images
        images = []
        for ext in ["*.png", "*.jpg", "*.jpeg"]:
            images.extend(sorted(Path(input_path).glob(ext)))
        if not images:
            print(f"No images found in {input_path}")
            return
        print(f"Found {len(images)} images in {input_path}")
    elif input_path.lower().endswith(".pdf"):
        # Create temp directory for images if PDF
        temp_dir = "/tmp/ballot_images"
        os.makedirs(temp_dir, exist_ok=True)
        print(f"Converting PDF to images...")
        images = pdf_to_images(input_path, temp_dir)
        print(f"Created {len(images)} images")
    else:
        images = [input_path]

    # Process each image
    results = []
    for image_path in images:
        print(f"\nProcessing: {image_path}")
        ballot_data = extract_ballot_data_with_ai(image_path)

        if ballot_data:
            print(f"  Form type: {ballot_data.form_type}")
            print(f"  Category: {ballot_data.form_category}")
            print(f"  Station: {ballot_data.polling_station_id}")
            if ballot_data.form_category == "party_list":
                print(f"  Party votes: {ballot_data.party_votes}")
            else:
                print(f"  Vote counts: {ballot_data.vote_counts}")
            print(f"  Total: {ballot_data.total_votes}")

            if args.verify:
                verification = verify_with_ect_data(ballot_data, "")
                results.append(verification)
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
                else:
                    result["vote_counts"] = ballot_data.vote_counts
                results.append(result)

    # Save results
    with open(args.output, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\nResults saved to: {args.output}")


if __name__ == "__main__":
    main()
