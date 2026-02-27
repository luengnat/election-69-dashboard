#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

from pypdf import PdfReader
from typhoon_ocr import ocr_document

from opentyphoon_ocr import download_drive_file, parse_drive_file_id


def parse_pages(raw: str) -> list[int]:
    if not raw.strip():
        return []
    out = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        if "-" in token:
            a, b = token.split("-", 1)
            if not a.strip().isdigit() or not b.strip().isdigit():
                raise ValueError(f"Invalid page range: {token}")
            start, end = int(a.strip()), int(b.strip())
            if start > end:
                raise ValueError(f"Invalid page range: {token}")
            out.extend(range(start, end + 1))
        else:
            if not token.isdigit():
                raise ValueError(f"Invalid page number: {token}")
            out.append(int(token))
    return sorted(set(out))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run typhoon-ocr package over local/Drive PDF pages.")
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--file", help="Local file path")
    src.add_argument("--drive-url", help="Google Drive file URL")
    parser.add_argument("--api-key", default=os.environ.get("TYPHOON_OCR_API_KEY", ""))
    parser.add_argument("--base-url", default=os.environ.get("TYPHOON_BASE_URL", "https://api.opentyphoon.ai/v1"))
    parser.add_argument("--model", default="typhoon-ocr")
    parser.add_argument("--task-type", default="default", choices=["default", "structure", "v1.5"])
    parser.add_argument("--pages", default="", help="Page list/range, e.g. 1,2,5-7. 1-based.")
    parser.add_argument("--all-pages", action="store_true", help="Process all pages in PDF.")
    parser.add_argument("--out-json", default="", help="Output JSON file")
    parser.add_argument("--out-jsonl", default="", help="Output JSONL (one row per page)")
    args = parser.parse_args()

    if not args.api_key:
        raise SystemExit("Missing API key. Use --api-key or env TYPHOON_OCR_API_KEY")

    local_path = ""
    tmp_file = None
    if args.file:
        local_path = args.file
    else:
        file_id = parse_drive_file_id(args.drive_url)
        if not file_id:
            raise SystemExit("Could not parse Google Drive file id.")
        content, filename = download_drive_file(file_id)
        suffix = Path(filename).suffix or ".pdf"
        tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        tmp_file.write(content)
        tmp_file.flush()
        tmp_file.close()
        local_path = tmp_file.name

    pages = parse_pages(args.pages)
    if args.all_pages:
        reader = PdfReader(local_path)
        pages = list(range(1, len(reader.pages) + 1))
    if not pages:
        pages = [1]

    results = []
    try:
        for page in pages:
            text = ocr_document(
                local_path,
                task_type=args.task_type,
                page_num=page,
                base_url=args.base_url,
                api_key=args.api_key,
                model=args.model,
            )
            results.append({"page": page, "text": text})
            print(f"page {page}: chars={len(text)}")
    finally:
        if tmp_file is not None:
            Path(tmp_file.name).unlink(missing_ok=True)

    payload = {
        "source": args.file or args.drive_url,
        "model": args.model,
        "task_type": args.task_type,
        "pages": pages,
        "results": results,
    }

    if args.out_json:
        Path(args.out_json).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.out_jsonl:
        with Path(args.out_jsonl).open("w", encoding="utf-8") as f:
            for row in results:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    if not args.out_json and not args.out_jsonl:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
