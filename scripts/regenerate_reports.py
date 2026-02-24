#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip().replace(",", "")
    if text.isdigit():
        return int(text)
    return None


def _vote_keys(votes: dict[str, Any]) -> list[str]:
    return sorted(
        [k for k in votes.keys() if str(k).isdigit()],
        key=lambda x: int(x),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Regenerate dashboard cross-check reports")
    parser.add_argument("--input", default="docs/data/district_dashboard_data.json")
    parser.add_argument("--out-dir", default="docs/data")
    args = parser.parse_args()

    input_path = Path(args.input)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    data = json.loads(input_path.read_text(encoding="utf-8"))
    items = data.get("items", [])

    summary = {
        "all_rows": 0,
        "with_killernay": 0,
        "exact_votes_match": 0,
        "diff_votes_rows": 0,
        "party_list_rows": 0,
        "constituency_rows": 0,
        "party_list_diff_rows": 0,
        "constituency_diff_rows": 0,
    }
    diff_rows: list[dict[str, Any]] = []
    sum_issues: list[dict[str, Any]] = []

    for row in items:
        summary["all_rows"] += 1
        form_type = str(row.get("form_type") or "")
        if form_type == "party_list":
            summary["party_list_rows"] += 1
        elif form_type == "constituency":
            summary["constituency_rows"] += 1

        votes_latest = row.get("votes") or {}
        sources = row.get("sources") or {}
        src_k = sources.get("killernay") or {}
        votes_k = src_k.get("votes") or {}

        if votes_k:
            summary["with_killernay"] += 1
            keys = sorted(set(_vote_keys(votes_latest)) | set(_vote_keys(votes_k)), key=lambda x: int(x))
            row_diffs: list[tuple[int, Any, Any, int | None]] = []
            for key in keys:
                v_latest = _to_int(votes_latest.get(key))
                v_k = _to_int(votes_k.get(key))
                if v_latest is not None and v_k is not None:
                    if v_latest != v_k:
                        row_diffs.append((int(key), v_latest, v_k, v_latest - v_k))
                elif v_latest is not None or v_k is not None:
                    row_diffs.append((int(key), v_latest, v_k, None))

            if not row_diffs:
                summary["exact_votes_match"] += 1
            else:
                summary["diff_votes_rows"] += 1
                if form_type == "party_list":
                    summary["party_list_diff_rows"] += 1
                elif form_type == "constituency":
                    summary["constituency_diff_rows"] += 1
                diff_rows.append(
                    {
                        "province": row.get("province"),
                        "district_number": row.get("district_number"),
                        "form_type": row.get("form_type"),
                        "drive_id": row.get("drive_id"),
                        "valid_current": row.get("valid_votes_extracted"),
                        "valid_killernay": src_k.get("valid_votes"),
                        "diff_key_count": len(row_diffs),
                        "abs_delta_sum": sum(abs(x[3]) for x in row_diffs if isinstance(x[3], int)),
                        "sample": " | ".join(f"{x[0]}:{x[1]}->{x[2]}" for x in row_diffs[:8]),
                    }
                )

        if form_type == "party_list":
            valid = _to_int(row.get("valid_votes_extracted"))
            if valid is not None and isinstance(votes_latest, dict):
                sum_votes = sum(
                    _to_int(votes_latest.get(k)) or 0
                    for k in _vote_keys(votes_latest)
                    if 1 <= int(k) <= 57
                )
                if sum_votes != valid:
                    sum_issues.append(
                        {
                            "province": row.get("province"),
                            "district_number": row.get("district_number"),
                            "drive_id": row.get("drive_id"),
                            "valid": valid,
                            "sum_votes": sum_votes,
                            "delta": valid - sum_votes,
                        }
                    )

    summary_json = out_dir / "recheck_all_vs_killernay_summary.json"
    diffs_csv = out_dir / "recheck_all_vs_killernay_diffs.csv"
    sum_csv = out_dir / "recheck_all_partylist_sum_issues.csv"

    summary_json.write_text(
        json.dumps(
            {
                "summary": summary,
                "remaining_partylist_sum_issues": len(sum_issues),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    with diffs_csv.open("w", newline="", encoding="utf-8") as f:
        fields = [
            "province",
            "district_number",
            "form_type",
            "drive_id",
            "valid_current",
            "valid_killernay",
            "diff_key_count",
            "abs_delta_sum",
            "sample",
        ]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(sorted(diff_rows, key=lambda x: (x["abs_delta_sum"], x["diff_key_count"]), reverse=True))

    with sum_csv.open("w", newline="", encoding="utf-8") as f:
        fields = ["province", "district_number", "drive_id", "valid", "sum_votes", "delta"]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(sum_issues)

    print(f"Wrote {summary_json}")
    print(f"Wrote {diffs_csv}")
    print(f"Wrote {sum_csv}")
    print(f"Remaining party_list sum issues: {len(sum_issues)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

