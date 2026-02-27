"""
Thai Election Ballot OCR Package.

A comprehensive toolkit for extracting, validating, and reporting ballot data
from Thai election forms using AI Vision OCR.

Main Components:
    - Core types and configuration
    - Ballot extraction with multiple AI backends
    - Validation against official ECT data
    - Result aggregation and reporting
    - Batch processing capabilities

Example Usage:
    >>> from ballot_ocr import BallotData, extract_ballot_data_with_ai
    >>> result = extract_ballot_data_with_ai("ballot.jpg")
    >>> print(result.form_type, result.total_votes)
"""

# Version
__version__ = "1.1.0"
__author__ = "Thai Election Ballot OCR Contributors"

# Core types - imported from core module
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

# Configuration - imported from core module
from ballot_ocr.core.config import Config, config, get_config, reload_config

# ECT reference data (re-export ect_data for tests and external use)
from ect_api import ect_data

# Extraction - imported from root-level module (shim)
from ballot_extraction import (
    extract_ballot_data_with_ai,
    ECT_AVAILABLE,
    pdf_to_images,
)

# Validation - imported from root-level module (shim)
from ballot_validation import (
    detect_discrepancies,
    verify_with_ect_data,
)

# Aggregation - imported from root-level module (shim)
from ballot_aggregation import (
    aggregate_ballot_results,
    aggregate_constituency,
    detect_anomalous_constituencies,
)

# Reporting - imported from root-level module (shim)
from ballot_reporting import (
    generate_constituency_report,
    generate_single_ballot_report,
    generate_batch_report,
    save_report,
)

from ballot_pdf import (
    generate_constituency_pdf,
    generate_batch_pdf,
    generate_ballot_pdf,
    generate_executive_summary_pdf,
    generate_one_page_executive_summary_pdf,
    HAS_REPORTLAB,
)

__all__ = [
    # Version
    "__version__",
    # Core types
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
    # Extraction
    "extract_ballot_data_with_ai",
    "ECT_AVAILABLE",
    "ect_data",
    "pdf_to_images",
    # Validation
    "detect_discrepancies",
    "verify_with_ect_data",
    # Aggregation
    "aggregate_ballot_results",
    "aggregate_constituency",
    "detect_anomalous_constituencies",
    # Reporting
    "generate_constituency_report",
    "generate_single_ballot_report",
    "generate_batch_report",
    "save_report",
    "generate_constituency_pdf",
    "generate_batch_pdf",
    "generate_ballot_pdf",
    "generate_executive_summary_pdf",
    "generate_one_page_executive_summary_pdf",
    "HAS_REPORTLAB",
]
