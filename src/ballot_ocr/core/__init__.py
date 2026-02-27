"""
Core module containing types and configuration.

This module provides the foundational data types and configuration
management for the ballot OCR system.
"""

from ballot_ocr.core.types import (
    FormType,
    VoteEntry,
    BallotData,
    AggregatedResults,
    THAI_NUMERALS,
    convert_thai_numerals,
    thai_text_to_number,
    validate_vote_entry,
)

from ballot_ocr.core.config import Config, config, get_config, reload_config

__all__ = [
    # Types
    "FormType",
    "VoteEntry",
    "BallotData",
    "AggregatedResults",
    "THAI_NUMERALS",
    "convert_thai_numerals",
    "thai_text_to_number",
    "validate_vote_entry",
    # Configuration
    "Config",
    "config",
    "get_config",
    "reload_config",
]
