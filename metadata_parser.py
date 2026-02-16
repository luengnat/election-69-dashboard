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
