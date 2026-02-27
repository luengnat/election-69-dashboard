"""
Backward compatibility shim for config.

DEPRECATED: Import from ballot_ocr.core.config instead.
    from ballot_ocr.core.config import config, Config, get_config, reload_config

This module re-exports all symbols from ballot_ocr.core.config for backward compatibility.
"""

from ballot_ocr.core.config import (
    Config,
    config,
    get_config,
    reload_config,
)

__all__ = [
    "Config",
    "config",
    "get_config",
    "reload_config",
]
