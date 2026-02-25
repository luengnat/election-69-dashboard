#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


CSV_COLUMNS = [
    "province",
    "district_number",
    "form_type",
    "drive_id",
    "drive_url",
    "valid_votes",
    "invalid_votes",
    "blank_votes",
    "total_votes",
    "votes_json",
    "updated_by",
    "update_reason",
]


def _to_int_or_blank(value: Any) -> Any:
    if value is None or value == "":
        return ""
    try:
        return int(value)
    except Exception:
        return value


def _sorted_votes_json(votes: dict[str, Any] | None) -> str:
    if not isinstance(votes, dict):
        return "{}"
    items: list[tuple[int, str, Any]] = []
    for key, value in votes.items():
        k = str(key)
        try:
            num = int(k)
        except Exception:
            num = 10**9
        items.append((num, k, value))
    items.sort(key=lambda x: (x[0], x[1]))
    out = {k: v for _, k, v in items}
    return json.dumps(out, ensure_ascii=False)


def _rows_for_form(items: list[dict[str, Any]], form_type: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in items:
        if item.get("form_type") != form_type:
            continue
        rows.append(
            {
                "province": item.get("province") or "",
                "district_number": _to_int_or_blank(item.get("district_number")),
                "form_type": form_type,
                "drive_id": item.get("drive_id") or "",
                "drive_url": item.get("drive_url") or "",
                "valid_votes": _to_int_or_blank(item.get("valid_votes_extracted")),
                "invalid_votes": _to_int_or_blank(item.get("invalid_votes")),
                "blank_votes": _to_int_or_blank(item.get("blank_votes")),
                "total_votes": _to_int_or_blank(item.get("total_votes")),
                "votes_json": _sorted_votes_json(item.get("votes") or {}),
                "updated_by": item.get("updated_by") or "",
                "update_reason": item.get("update_reason") or "",
            }
        )
    rows.sort(key=lambda r: (str(r["province"]), int(r["district_number"] or 0)))
    return rows


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate export_first2 constituency/party-list CSVs from district_dashboard_data.json"
    )
    parser.add_argument("--input", default="docs/data/district_dashboard_data.json")
    parser.add_argument("--out-const", default="export_first2_constituency_100.csv")
    parser.add_argument("--out-party", default="export_first2_party_list_100.csv")
    args = parser.parse_args()

    input_path = Path(args.input)
    out_const = Path(args.out_const)
    out_party = Path(args.out_party)

    data = json.loads(input_path.read_text(encoding="utf-8"))
    items = data.get("items", [])

    rows_const = _rows_for_form(items, "constituency")
    rows_party = _rows_for_form(items, "party_list")
    _write_csv(out_const, rows_const)
    _write_csv(out_party, rows_party)

    print(f"Wrote {out_const} ({len(rows_const)} rows)")
    print(f"Wrote {out_party} ({len(rows_party)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
