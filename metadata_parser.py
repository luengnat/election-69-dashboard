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
