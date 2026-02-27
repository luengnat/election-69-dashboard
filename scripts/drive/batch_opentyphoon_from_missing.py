#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from opentyphoon_ocr import call_opentyphoon_ocr, download_drive_file, extract_text_from_ocr_result


def run_one(item: dict[str, Any], api_key: str, out_dir: Path) -> dict[str, Any]:
    drive_id = item["drive_id"]
    name = item.get("name", "")
    drive_url = item.get("drive_url", f"https://drive.google.com/file/d/{drive_id}/view")
    try:
        content, filename = download_drive_file(drive_id)
        result = call_opentyphoon_ocr(
            file_bytes=content,
            filename=filename or f"{drive_id}.pdf",
            api_key=api_key,
            model="typhoon-ocr",
            task_type="default",
            max_tokens=16384,
            temperature=0.1,
            top_p=0.6,
            repetition_penalty=1.2,
            pages=None,
            timeout=300,
        )
        text = extract_text_from_ocr_result(result)
        (out_dir / f"{drive_id}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        (out_dir / f"{drive_id}.txt").write_text(text, encoding="utf-8")
        return {
            "ok": True,
            "drive_id": drive_id,
            "name": name,
            "drive_url": drive_url,
            "text_chars": len(text),
        }
    except Exception as exc:
        return {
            "ok": False,
            "drive_id": drive_id,
            "name": name,
            "drive_url": drive_url,
            "error": str(exc),
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--missing-json", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--out-jsonl", required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--api-key", default=os.environ.get("OPENTYPHOON_API_KEY", ""))
    args = parser.parse_args()

    if not args.api_key:
        raise SystemExit("Missing API key. Set --api-key or OPENTYPHOON_API_KEY")

    missing = json.loads(Path(args.missing_json).read_text(encoding="utf-8"))
    items = missing.get("items", [])
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    results = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
        futures = [ex.submit(run_one, item, args.api_key, out_dir) for item in items]
        for fut in as_completed(futures):
            row = fut.result()
            results.append(row)
            status = "ok" if row.get("ok") else "fail"
            msg = row.get("error", "")
            print(f"{status}: {row['drive_id']} {row.get('name','')} {msg}")

    out_jsonl = Path(args.out_jsonl)
    with out_jsonl.open("w", encoding="utf-8") as f:
        for row in results:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    ok = sum(1 for r in results if r.get("ok"))
    fail = len(results) - ok
    print(json.dumps({"total": len(results), "ok": ok, "fail": fail}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
