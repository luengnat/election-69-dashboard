#!/usr/bin/env python3
"""Normalize Thai numerals to Arabic digits in Gemini JSON blocks from jsonl output."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

THAI_TO_ARABIC = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")
JSON_BLOCK_RE = re.compile(r"\{\n\s*\"drive_id\"[\s\S]*\n\}")
INT_STR_RE = re.compile(r"^\s*[-+]?\d+\s*$")


def normalize_scalar(value: Any) -> Any:
    if isinstance(value, str):
        s = value.translate(THAI_TO_ARABIC)
        if INT_STR_RE.match(s):
            try:
                return int(s.strip())
            except Exception:
                return s
        return s
    return value


def normalize_obj(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: normalize_obj(v) for k, v in value.items()}
    if isinstance(value, list):
        return [normalize_obj(v) for v in value]
    return normalize_scalar(value)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in-file", required=True)
    ap.add_argument("--out-file", required=True)
    args = ap.parse_args()

    in_path = Path(args.in_file)
    out_path = Path(args.out_file)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    converted = 0
    total = 0

    with in_path.open("r", encoding="utf-8") as src, out_path.open("w", encoding="utf-8") as dst:
        for line in src:
            line = line.strip()
            if not line:
                continue
            total += 1
            try:
                row = json.loads(line)
            except Exception:
                continue
            summary = str(row.get("summary", "") or "")
            m = JSON_BLOCK_RE.search(summary)
            if not m:
                continue
            try:
                parsed = json.loads(m.group(0))
            except Exception:
                continue
            normalized = normalize_obj(parsed)
            dst.write(json.dumps(normalized, ensure_ascii=False) + "\n")
            converted += 1

    print(f"total_lines={total} converted_json_blocks={converted} out={out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
