#!/usr/bin/env python3
"""
Metadata parser for extracting ballot information from file paths.

This module extracts province, constituency, district, and other metadata
from Thai ballot file paths to reduce OCR burden by pre-filling metadata
before AI extraction.
"""

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


THAI_TO_ARABIC_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")


@dataclass
class InferredMetadata:
    """
    Metadata extracted from file path (not from OCR).

    This class holds metadata that was inferred from parsing the file path
    structure, as opposed to being extracted via OCR from the ballot image.
    The 'source' field tracks whether data came from path or OCR fallback.

    Attributes:
        province: Thai province name (validated against ECT's 77 provinces)
        constituency_number: Constituency number (1-77, depending on province)
        district: District name (Thai: อำเภอ)
        subdistrict: Subdistrict name (Thai: ตำบล)
        polling_unit: Polling unit number (Thai: หน่วยเลือกตั้ง)
        form_type: Type of ballot form ('constituency' or 'party_list')
        source: Origin of metadata ('path' for inferred, 'ocr' for fallback)
        confidence: Confidence score from 0.0 to 1.0 based on extraction success
    """
    province: Optional[str] = None
    constituency_number: Optional[int] = None
    district: Optional[str] = None
    subdistrict: Optional[str] = None
    polling_unit: Optional[int] = None
    form_type: Optional[str] = None  # 'constituency' or 'party_list'
    source: str = "path"  # 'path' or 'ocr' (fallback source indicator)
    confidence: float = 0.0  # 0.0 to 1.0


@dataclass
class DriveSheetEntry:
    """Parsed row from Drive Sheet style: 'จังหวัด.เขต (เปอร์เซ็นต์)'."""

    province: str
    constituency_number: int
    percent: Optional[float] = None
    rank: Optional[int] = None
    source: str = ""


@dataclass
class DriveSheetLocation:
    """Only the location fields needed from Drive Sheet rows."""

    province: str
    constituency_number: int


class PathMetadataParser:
    """
    Extract province/constituency metadata from Thai ballot file paths.

    Path structure example:
    ballots/Phrae/เขตเลือกตั้งที่ 1 จังหวัดแพร่/อําเภอสูงเม่น/ตําบลดอนมูล/หน่วยเลือกตั้งที่1/สส5ทับ18.pdf

    Integration:
    - Use before OCR to pre-fill BallotData fields
    - Validate province with ect_data.validate_province_name()
    - Fall back to OCR extraction if path parsing fails
    """

    # Regex patterns for Thai metadata extraction
    CONSTITUENCY_PATTERN = re.compile(r'เขตเลือกตั้งที่\s*(\d+)')
    DISTRICT_PATTERN = re.compile(r'อําเภอ([^/]+)')
    SUBDISTRICT_PATTERN = re.compile(r'ตําบล([^/]+)')
    POLLING_UNIT_PATTERN = re.compile(r'หน่วยเลือกตั้งที่\s*(\d+)')
    PROVINCE_IN_PATH_PATTERN = re.compile(r'จังหวัด([^/]+)')

    def __init__(self):
        """
        Initialize parser with ECT data reference.
        """
        self._ect_data = None

    def _get_ect_data(self):
        """
        Lazily initialize ECT data to avoid network work during object construction.
        """
        if self._ect_data is None:
            from ect_api import ect_data
            ect_data.load()  # Ensure province list is available
            self._ect_data = ect_data
        return self._ect_data

    def normalize_thai(self, text: str) -> str:
        """
        Apply NFC normalization for consistent Thai character comparison.

        Uses NFC (Canonical Composition) which is the standard for text
        comparison, unlike NFKD which is used for filename sanitization.

        Args:
            text: Input text to normalize

        Returns:
            Normalized text with consistent Unicode representation
        """
        return unicodedata.normalize('NFC', text)

    @staticmethod
    def _normalize_digits(text: str) -> str:
        """Normalize Thai numerals to Arabic numerals for numeric parsing."""
        return (text or "").translate(THAI_TO_ARABIC_DIGITS)

    def parse_drive_sheet_entry(self, row_text: str) -> Optional[DriveSheetEntry]:
        """
        Parse a row like:
        - "เชียงใหม่.1 (68.83%)"
        - "นราธิวาส 3 (43.35%)"
        - "10 นครราชสีมา.2 (47.42%)"
        """
        raw = self.normalize_thai(row_text or "").strip()
        if not raw:
            return None

        text = self._normalize_digits(raw)

        percent = None
        percent_match = re.search(r"\(([0-9]+(?:\.[0-9]+)?)%\)", text)
        if percent_match:
            try:
                percent = float(percent_match.group(1))
            except ValueError:
                percent = None
            text = text[: percent_match.start()].strip()

        rank = None
        rank_match = re.match(r"^\s*(\d+)\s+", text)
        if rank_match:
            rank = int(rank_match.group(1))
            text = text[rank_match.end() :].strip()

        match = re.match(r"^\s*([^.\d]+?)\s*[.\s]\s*(\d+)\s*$", text)
        if not match:
            return None

        province = match.group(1).strip()
        constituency = int(match.group(2))
        if not province or constituency <= 0:
            return None

        return DriveSheetEntry(
            province=province,
            constituency_number=constituency,
            percent=percent,
            rank=rank,
            source=raw,
        )

    def parse_drive_sheet_location(self, row_text: str) -> Optional[DriveSheetLocation]:
        """Parse Drive sheet row and return only province + constituency number."""
        entry = self.parse_drive_sheet_entry(row_text)
        if entry is None:
            return None
        return DriveSheetLocation(
            province=entry.province,
            constituency_number=entry.constituency_number,
        )

    def parse_path(self, file_path: str) -> InferredMetadata:
        """
        Extract metadata from a ballot file path.

        Parses Thai patterns in the path to extract:
        - Constituency number (เขตเลือกตั้งที่ X)
        - District (อำเภอ X)
        - Subdistrict (ตำบล X)
        - Polling unit (หน่วยเลือกตั้งที่ X)
        - Form type from filename patterns

        Confidence is calculated based on how many fields were extracted:
        - Province: +0.3
        - Constituency: +0.2
        - District: +0.1

        Args:
            file_path: Path to the ballot file

        Returns:
            InferredMetadata with extracted values and confidence score
        """
        metadata = InferredMetadata()

        # Normalize the path for consistent parsing
        normalized_path = self.normalize_thai(file_path)

        # Extract province from path (จังหวัด prefix)
        prov_match = self.PROVINCE_IN_PATH_PATTERN.search(normalized_path)
        if prov_match:
            potential_province = prov_match.group(1).strip()
            # Validate against ECT list
            ect_data = self._get_ect_data()
            is_valid, canonical = ect_data.validate_province_name(potential_province)
            if is_valid and canonical:
                metadata.province = canonical
                metadata.confidence += 0.3

        # Extract constituency number
        cons_match = self.CONSTITUENCY_PATTERN.search(normalized_path)
        if cons_match:
            metadata.constituency_number = int(cons_match.group(1))

        # Extract district (อําเภอ)
        dist_match = self.DISTRICT_PATTERN.search(normalized_path)
        if dist_match:
            metadata.district = dist_match.group(1).strip()

        # Extract subdistrict (ตําบล)
        subdist_match = self.SUBDISTRICT_PATTERN.search(normalized_path)
        if subdist_match:
            metadata.subdistrict = subdist_match.group(1).strip()

        # Extract polling unit
        unit_match = self.POLLING_UNIT_PATTERN.search(normalized_path)
        if unit_match:
            metadata.polling_unit = int(unit_match.group(1))

        # Extract form type from filename
        filename = Path(file_path).name
        if '(บช)' in filename:
            metadata.form_type = 'party_list'
        elif '5ทับ18' in filename or '5/18' in filename:
            metadata.form_type = 'constituency'

        # Calculate confidence based on fields extracted
        if metadata.constituency_number:
            metadata.confidence += 0.2
        if metadata.district:
            metadata.confidence += 0.1

        return metadata

    def extract_province_from_parent_dir(self, file_path: str) -> Optional[str]:
        """
        Extract province from immediate parent directory name.

        Google Drive folders are often named after provinces (e.g., "Phrae" or "แพร่").
        This method validates the parent directory name against the ECT province list.

        Args:
            file_path: Path to the ballot file

        Returns:
            Canonical Thai province name if valid, None otherwise
        """
        parent_dir = Path(file_path).parent.name
        normalized = self.normalize_thai(parent_dir)

        # Try direct match against ECT province list
        ect_data = self._get_ect_data()
        is_valid, canonical = ect_data.validate_province_name(normalized)
        if is_valid and canonical:
            return canonical

        return None
