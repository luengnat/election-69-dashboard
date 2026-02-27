"""Shim package to expose src/ballot_ocr as top-level package for tests.

This shim avoids executing the package __init__ at import time (which can
trigger circular imports). Instead it inserts the src/ballot_ocr directory
into the package __path__ and provides a lazy attribute loader that imports
specific submodules or top-level modules on demand.
"""
import os
import importlib

_pkg_dir = os.path.dirname(__file__)
_src_pkg = os.path.abspath(os.path.join(_pkg_dir, '..', 'src', 'ballot_ocr'))

# Prefer the src package directory for submodule imports
if os.path.isdir(_src_pkg):
    __path__.insert(0, _src_pkg)

# Names grouped by source module for lazy loading
_TYPES = {
    "FormType",
    "VoteEntry",
    "BallotData",
    "AggregatedResults",
    "THAI_NUMERALS",
    "convert_thai_numerals",
    "thai_text_to_number",
    "validate_vote_entry",
}
_CONFIG = {"Config", "config", "get_config", "reload_config"}
_EXTRACTION = {"extract_ballot_data_with_ai", "ECT_AVAILABLE", "pdf_to_images", "ect_data"}
_VALIDATION = {"detect_discrepancies", "verify_with_ect_data"}
_AGGREGATION = {"aggregate_ballot_results", "aggregate_constituency", "detect_anomalous_constituencies"}
_REPORTING = {"generate_constituency_report", "generate_single_ballot_report", "generate_batch_report", "save_report"}
_PDF = {"generate_constituency_pdf", "generate_batch_pdf", "generate_ballot_pdf", "generate_executive_summary_pdf", "generate_one_page_executive_summary_pdf", "HAS_REPORTLAB"}


def _load_from(module_name: str, attr: str):
    mod = importlib.import_module(module_name)
    val = getattr(mod, attr)
    globals()[attr] = val
    return val


def __getattr__(name: str):
    if name in _TYPES:
        return _load_from('ballot_ocr.core.types', name)
    if name in _CONFIG:
        return _load_from('ballot_ocr.core.config', name)
    if name in _EXTRACTION:
        # extraction helpers live in the top-level ballot_extraction and ect_api
        if name == 'ect_data':
            return _load_from('ect_api', 'ect_data')
        return _load_from('ballot_extraction', name)
    if name in _VALIDATION:
        return _load_from('ballot_validation', name)
    if name in _AGGREGATION:
        return _load_from('ballot_aggregation', name)
    if name in _REPORTING:
        return _load_from('ballot_reporting', name)
    if name in _PDF:
        return _load_from('ballot_pdf', name)
    raise AttributeError(f"module {__name__} has no attribute {name}")


# Public names for from ballot_ocr import *
__all__ = sorted(list(_TYPES | _CONFIG | _EXTRACTION | _VALIDATION | _AGGREGATION | _REPORTING | _PDF))

