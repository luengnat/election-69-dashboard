#!/usr/bin/env python3
"""
Data types and Thai numeral utilities for ballot OCR.

Contains: FormType enum, VoteEntry, BallotData, AggregatedResults dataclasses,
Thai numeral conversion utilities, and vote entry validation.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


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

    @classmethod
    def from_dict(cls, d: dict) -> "BallotData":
        """Reconstruct BallotData from a dictionary (e.g., loaded from JSON checkpoint)."""
        vote_details = {}
        for k, v in d.get("vote_details", {}).items():
            if isinstance(v, dict):
                vote_details[int(k)] = VoteEntry(
                    numeric=v.get("numeric", 0),
                    thai_text=v.get("thai_text", ""),
                    is_validated=v.get("is_validated", False)
                )
        party_details = {}
        for k, v in d.get("party_details", {}).items():
            if isinstance(v, dict):
                party_details[str(k)] = VoteEntry(
                    numeric=v.get("numeric", 0),
                    thai_text=v.get("thai_text", ""),
                    is_validated=v.get("is_validated", False)
                )
        return cls(
            form_type=d.get("form_type", ""),
            form_category=d.get("form_category", ""),
            province=d.get("province", ""),
            constituency_number=d.get("constituency_number", 0),
            district=d.get("district", ""),
            polling_unit=d.get("polling_unit", 0),
            page_parties=d.get("page_parties", ""),
            polling_station_id=d.get("polling_station_id", ""),
            vote_counts={int(k): v for k, v in d.get("vote_counts", {}).items()},
            vote_details=vote_details,
            party_votes={str(k): v for k, v in d.get("party_votes", {}).items()},
            party_details=party_details,
            candidate_info={int(k): v for k, v in d.get("candidate_info", {}).items()},
            party_info={str(k): v for k, v in d.get("party_info", {}).items()},
            total_votes=d.get("total_votes", 0),
            valid_votes=d.get("valid_votes", 0),
            invalid_votes=d.get("invalid_votes", 0),
            blank_votes=d.get("blank_votes", 0),
            source_file=d.get("source_file", ""),
            confidence_score=d.get("confidence_score", 0.0),
            confidence_details=d.get("confidence_details", {}),
        )


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
