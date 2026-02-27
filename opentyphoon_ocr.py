#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import requests


OCR_URL = "https://api.opentyphoon.ai/v1/ocr"


def parse_drive_file_id(url: str) -> str | None:
    patterns = [
        r"/file/d/([a-zA-Z0-9_-]+)",
        r"[?&]id=([a-zA-Z0-9_-]+)",
        r"/d/([a-zA-Z0-9_-]+)",
    ]
    for pattern in patterns:
        m = re.search(pattern, url)
        if m:
            return m.group(1)
    return None


def download_drive_file(file_id: str, timeout: int = 120) -> tuple[bytes, str]:
    """Best-effort download for publicly shared Drive files."""
    session = requests.Session()
    base = "https://drive.google.com/uc?export=download"
    resp = session.get(base, params={"id": file_id}, timeout=timeout)
    if resp.status_code != 200:
        raise RuntimeError(f"Drive download failed: HTTP {resp.status_code}")

    # Large files may require confirmation token.
    token = None
    for key, val in session.cookies.items():
        if key.startswith("download_warning"):
            token = val
            break
    if token:
        resp = session.get(base, params={"id": file_id, "confirm": token}, timeout=timeout)
        if resp.status_code != 200:
            raise RuntimeError(f"Drive confirm download failed: HTTP {resp.status_code}")

    ctype = (resp.headers.get("content-type") or "").lower()
    if "text/html" in ctype and b"ServiceLogin" in resp.content:
        raise RuntimeError("Drive file is not publicly accessible (login required).")

    disposition = resp.headers.get("content-disposition") or ""
    fname = f"{file_id}.pdf"
    m = re.search(r'filename\\*=UTF-8\'\'([^;]+)|filename=\"?([^\";]+)\"?', disposition)
    if m:
        fname = (m.group(1) or m.group(2) or fname).strip()
    return resp.content, fname


def call_opentyphoon_ocr(
    file_bytes: bytes,
    filename: str,
    api_key: str,
    model: str = "typhoon-ocr",
    task_type: str = "default",
    max_tokens: int = 16384,
    temperature: float = 0.1,
    top_p: float = 0.6,
    repetition_penalty: float = 1.2,
    pages: list[int] | None = None,
    timeout: int = 300,
) -> dict[str, Any]:
    files = {"file": (filename, file_bytes, "application/pdf")}
    data: dict[str, str] = {
        "model": model,
        "task_type": task_type,
        "max_tokens": str(max_tokens),
        "temperature": str(temperature),
        "top_p": str(top_p),
        "repetition_penalty": str(repetition_penalty),
    }
    if pages:
        data["pages"] = json.dumps(pages)
    headers = {"Authorization": f"Bearer {api_key}"}

    resp = requests.post(OCR_URL, files=files, data=data, headers=headers, timeout=timeout)
    if resp.status_code != 200:
        raise RuntimeError(f"OpenTyphoon OCR failed: HTTP {resp.status_code} {resp.text[:500]}")
    return resp.json()


def extract_text_from_ocr_result(result: dict[str, Any]) -> str:
    extracted: list[str] = []
    for page_result in result.get("results", []):
        if not page_result.get("success"):
            continue
        msg = page_result.get("message") or {}
        choices = msg.get("choices") or []
        if not choices:
            continue
        content = str(choices[0].get("message", {}).get("content", "")).strip()
        if not content:
            continue
        try:
            parsed = json.loads(content)
            text = parsed.get("natural_text", content) if isinstance(parsed, dict) else content
        except json.JSONDecodeError:
            text = content
        extracted.append(text)
    return "\n".join(extracted)


def parse_pages(raw: str | None) -> list[int] | None:
    if not raw:
        return None
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    nums = []
    for part in parts:
        if not part.isdigit():
            raise ValueError(f"Invalid page number: {part}")
        nums.append(int(part))
    return nums or None


def main() -> int:
    parser = argparse.ArgumentParser(description="OCR via OpenTyphoon from local file or Google Drive file link.")
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--file", help="Local file path (pdf/jpg/png).")
    src.add_argument("--drive-url", help="Google Drive file URL.")
    parser.add_argument("--api-key", default=os.environ.get("OPENTYPHOON_API_KEY", ""))
    parser.add_argument("--model", default="typhoon-ocr")
    parser.add_argument("--task-type", default="default")
    parser.add_argument("--max-tokens", type=int, default=16384)
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument("--top-p", type=float, default=0.6)
    parser.add_argument("--repetition-penalty", type=float, default=1.2)
    parser.add_argument("--pages", default="", help="Comma-separated page numbers, e.g. 1,2,3")
    parser.add_argument("--out-json", default="", help="Optional output JSON file.")
    parser.add_argument("--out-text", default="", help="Optional output text file.")
    args = parser.parse_args()

    if not args.api_key:
        print("ERROR: Missing API key. Set --api-key or OPENTYPHOON_API_KEY.", file=sys.stderr)
        return 2

    pages = parse_pages(args.pages)

    if args.file:
        p = Path(args.file)
        if not p.exists():
            print(f"ERROR: file not found: {p}", file=sys.stderr)
            return 2
        file_bytes = p.read_bytes()
        filename = p.name
    else:
        file_id = parse_drive_file_id(args.drive_url)
        if not file_id:
            print("ERROR: Could not parse Google Drive file id from URL.", file=sys.stderr)
            return 2
        file_bytes, filename = download_drive_file(file_id)

    result = call_opentyphoon_ocr(
        file_bytes=file_bytes,
        filename=filename,
        api_key=args.api_key,
        model=args.model,
        task_type=args.task_type,
        max_tokens=args.max_tokens,
        temperature=args.temperature,
        top_p=args.top_p,
        repetition_penalty=args.repetition_penalty,
        pages=pages,
    )

    text = extract_text_from_ocr_result(result)
    if args.out_json:
        Path(args.out_json).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.out_text:
        Path(args.out_text).write_text(text, encoding="utf-8")
    if not args.out_text:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
