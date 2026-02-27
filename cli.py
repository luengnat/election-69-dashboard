#!/usr/bin/env python3
"""
Backward compatibility shim for CLI.

DEPRECATED: Use ballot-ocr command or python -m ballot_ocr.cli instead.

This module re-exports the CLI entry point for backward compatibility.
"""

from ballot_ocr.cli.main import main, create_parser

__all__ = ["main", "create_parser"]

if __name__ == "__main__":
    main()
