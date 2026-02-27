#!/usr/bin/env python3
"""
Backward compatibility shim for ballot_types.

DEPRECATED: Import from ballot_ocr.core.types instead.
    from ballot_ocr.core.types import BallotData, FormType, VoteEntry

This module re-exports all symbols from ballot_ocr.core.types for backward compatibility.
"""

# Re-export everything from the new location
from ballot_ocr.core.types import (
    # Enums
    FormType,
    # Data classes
    VoteEntry,
    BallotData,
    AggregatedResults,
    # Constants
    THAI_NUMERALS,
    THAI_DIGITS,
    THAI_TENS,
    THAI_HUNDREDS,
    THAI_THOUSANDS,
    THAI_SUFFIXES,
    # Functions
    convert_thai_numerals,
    thai_text_to_number,
    validate_vote_entry,
)

__all__ = [
    "FormType",
    "VoteEntry",
    "BallotData",
    "AggregatedResults",
    "THAI_NUMERALS",
    "THAI_DIGITS",
    "THAI_TENS",
    "THAI_HUNDREDS",
    "THAI_THOUSANDS",
    "THAI_SUFFIXES",
    "convert_thai_numerals",
    "thai_text_to_number",
    "validate_vote_entry",
]
