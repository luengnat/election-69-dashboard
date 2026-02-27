#!/usr/bin/env python3
"""
Build a compact manual adjudication queue for extracted-vs-killernay mismatches.

Inputs:
  - killernay_diff_audit.csv
  - official_manifest_remaining_mapping.json (Drive URL/name lookup)
  - official_manifest_part2B_structured.jsonl (optional extra context)

Outputs:
  - killernay_manual_review_queue.json
  - killernay_manual_review_queue.md
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent
AUDIT_CSV = REPO / "killernay_diff_audit.csv"
MAPPING_JSON = REPO / "official_manifest_remaining_mapping.json"
STRUCTURED_JSONL = REPO / "official_manifest_part2B_structured.jsonl"
OUT_JSON = REPO / "killernay_manual_review_queue.json"
OUT_MD = REPO / "killernay_manual_review_queue.md"


def _load_mapping() -> dict[str, dict[str, Any]]:
    if not MAPPING_JSON.exists():
        return {}
    try:
        payload = json.loads(MAPPING_JSON.read_text(encoding="utf-8"))
    except Exception:
        return {}
    files = payload.get("files", {})
    return files if isinstance(files, dict) else {}


def _load_structured_notes() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    if not STRUCTURED_JSONL.exists():
        return out
    with STRUCTURED_JSONL.open(encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            doc = row.get("document", {})
            drive_id = str(doc.get("drive_id", "")).strip()
            if not drive_id:
                continue
            forms = row.get("forms", [])
            first_form = forms[0] if isinstance(forms, list) and forms else {}
            out[drive_id] = {
                "structured_form_type": first_form.get("form_type"),
                "structured_province": first_form.get("province"),
                "structured_district": first_form.get("constituency_number"),
                "structured_confidence": first_form.get("confidence"),
                "structured_notes": first_form.get("notes"),
            }
    return out


def _review_focus(mismatch_type: str, delta: int) -> str:
    if mismatch_type == "major_structural_mismatch":
        return "Check document identity first: province, district, form type, and whether pages are mixed with another form."
    if mismatch_type == "likely_thousand_block_or_grouping_error":
        return "Re-check 4-digit blocks and separators. Likely a missing/extra thousand chunk."
    if mismatch_type == "medium_digit_parse_error":
        if abs(delta) <= 100:
            return "Likely small digit error. Verify candidate/party rows around where totals can shift by <100."
        return "Likely row-level digit parse issue. Re-check suspicious rows and total consistency."
    if mismatch_type == "other_mismatch":
        return "Manual cross-check needed against source PDF pages and computed sum of row votes."
    return "Manual review needed."


def main() -> int:
    if not AUDIT_CSV.exists():
        raise SystemExit(f"Missing input: {AUDIT_CSV}")

    mapping = _load_mapping()
    structured = _load_structured_notes()

    queue: list[dict[str, Any]] = []
    with AUDIT_CSV.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            drive_id = str(row.get("drive_id", "")).strip()
            if not drive_id:
                continue
            map_entry = mapping.get(drive_id, {})
            delta = int(float(row.get("delta", 0) or 0))
            mismatch_type = str(row.get("mismatch_type", "")).strip()
            item = {
                "drive_id": drive_id,
                "name": row.get("name"),
                "province": row.get("province"),
                "district": int(float(row.get("district", 0) or 0)),
                "election_type": row.get("election_type"),
                "our_valid": int(float(row.get("our_valid", 0) or 0)),
                "killernay_valid": int(float(row.get("killernay_valid", 0) or 0)),
                "vote_sum": int(float(row.get("vote_sum", 0) or 0)),
                "delta": delta,
                "abs_delta": int(float(row.get("abs_delta", 0) or 0)),
                "mismatch_type": mismatch_type,
                "drive_url": map_entry.get("drive_url", f"https://drive.google.com/file/d/{drive_id}/view"),
                "pdf_name": map_entry.get("name"),
                "folder_path": map_entry.get("folder_path"),
                "structured_context": structured.get(drive_id, {}),
                "review_focus": _review_focus(mismatch_type, delta),
            }
            queue.append(item)

    queue.sort(key=lambda x: x["abs_delta"], reverse=True)
    OUT_JSON.write_text(
        json.dumps(
            {
                "count": len(queue),
                "generated_from": str(AUDIT_CSV.name),
                "items": queue,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    md_lines = [
        "# Killernay Mismatch Manual Review Queue",
        "",
        f"Total cases: {len(queue)}",
        "",
        "Use this list to adjudicate each mismatch in Google Drive (source of truth for this pass).",
        "",
    ]
    for i, item in enumerate(queue, start=1):
        md_lines.extend(
            [
                f"## {i}. {item.get('name') or item['drive_id']}",
                f"- Drive: {item['drive_url']}",
                f"- Province/District: {item.get('province')} / {item.get('district')}",
                f"- Type: {item.get('election_type')}",
                f"- Our valid: {item.get('our_valid')}",
                f"- Killernay valid: {item.get('killernay_valid')}",
                f"- Row vote sum (ours): {item.get('vote_sum')}",
                f"- Delta (ours - killernay): {item.get('delta')}",
                f"- Mismatch class: {item.get('mismatch_type')}",
                f"- Review focus: {item.get('review_focus')}",
                "",
            ]
        )
    OUT_MD.write_text("\n".join(md_lines), encoding="utf-8")

    print(f"wrote {OUT_JSON}")
    print(f"wrote {OUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

