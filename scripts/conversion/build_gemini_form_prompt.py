#!/usr/bin/env python3
"""Build reusable Gemini extraction prompt for Thai election PDFs."""

from __future__ import annotations

import argparse
from pathlib import Path

TEMPLATE_PATH = Path(__file__).parent / "prompts" / "gemini_ballot_json_extraction.md"


def main() -> int:
    parser = argparse.ArgumentParser(description="Render Gemini ballot JSON extraction instruction")
    parser.add_argument("--source-name", default="<file name>", help="PDF file name for context")
    parser.add_argument("--page-count", default="<int|null>", help="Known page count (optional)")
    parser.add_argument("--out", default="-", help="Output path or - for stdout")
    args = parser.parse_args()

    if not TEMPLATE_PATH.exists():
        print(f"ERROR: template not found: {TEMPLATE_PATH}")
        return 1

    text = TEMPLATE_PATH.read_text(encoding="utf-8")
    text = text.replace("<file name>", str(args.source_name))
    text = text.replace("<int|null>", str(args.page_count))

    if args.out == "-":
        print(text)
    else:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"Wrote prompt to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
