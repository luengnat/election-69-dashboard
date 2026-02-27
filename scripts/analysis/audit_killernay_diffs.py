#!/usr/bin/env python3
"""
Audit mismatches between our extracted district totals and Killernay reference.

Outputs:
  - killernay_diff_audit.json
  - killernay_diff_audit.csv
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any


REPO = Path("/Users/nat/dev/election")
COMPARISON_CSV = REPO / "comparison_unified_preview.csv"
DASHBOARD_JSON = REPO / "docs/data/district_dashboard_data.json"
OUT_JSON = REPO / "killernay_diff_audit.json"
OUT_CSV = REPO / "killernay_diff_audit.csv"


def _safe_int(v: Any) -> int | None:
    try:
        if v in (None, "", "nan", "NaN"):
            return None
        return int(float(v))
    except Exception:
        return None


def _classify(delta: int, weak_summary: bool, valid_votes: int | None, vote_sum: int | None, vote_count: int) -> str:
    abs_delta = abs(delta)
    if valid_votes is not None and vote_sum is not None and valid_votes != vote_sum:
        return "sum_inconsistency_in_our_data"
    if valid_votes is not None and valid_votes <= 100 and abs_delta >= 10000:
        return "catastrophic_parse_or_truncation"
    if weak_summary and abs_delta > 0:
        return "weak_summary_source_low_confidence"
    if abs_delta <= 50:
        return "small_numeric_noise"
    if 51 <= abs_delta <= 999:
        return "medium_digit_parse_error"
    if abs_delta % 1000 == 0 and abs_delta <= 10000:
        return "likely_thousand_block_or_grouping_error"
    if vote_count <= 2 and abs_delta > 1000:
        return "partial_row_capture"
    if abs_delta > 20000:
        return "major_structural_mismatch"
    return "other_mismatch"


def main() -> int:
    if not COMPARISON_CSV.exists():
        raise FileNotFoundError(f"Missing comparison file: {COMPARISON_CSV}")
    if not DASHBOARD_JSON.exists():
        raise FileNotFoundError(f"Missing dashboard data: {DASHBOARD_JSON}")

    dashboard = json.loads(DASHBOARD_JSON.read_text(encoding="utf-8"))
    by_drive = {str(it.get("drive_id")): it for it in dashboard.get("items", [])}

    mismatches: list[dict[str, Any]] = []
    total_with_ref = 0
    exact = 0

    with COMPARISON_CSV.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            drive_id = str(row.get("drive_id", "")).strip()
            extracted_valid = _safe_int(row.get("extracted_valid"))
            ref_valid = _safe_int(row.get("ref_valid"))
            if extracted_valid is None or ref_valid is None:
                continue

            total_with_ref += 1
            delta = extracted_valid - ref_valid
            if delta == 0:
                exact += 1
                continue

            item = by_drive.get(drive_id, {})
            votes = item.get("votes", {}) if isinstance(item, dict) else {}
            vote_sum = sum(_safe_int(v) or 0 for v in votes.values()) if isinstance(votes, dict) else None
            vote_count = len(votes) if isinstance(votes, dict) else 0
            weak_summary = bool(item.get("weak_summary", False)) if isinstance(item, dict) else False
            valid_votes = _safe_int(item.get("valid_votes_extracted")) if isinstance(item, dict) else extracted_valid

            mismatch_type = _classify(
                delta=delta,
                weak_summary=weak_summary,
                valid_votes=valid_votes,
                vote_sum=vote_sum,
                vote_count=vote_count,
            )

            mismatches.append(
                {
                    "drive_id": drive_id,
                    "name": item.get("name", ""),
                    "province": row.get("province", ""),
                    "district": _safe_int(row.get("district")) or 0,
                    "election_type": row.get("election_type", ""),
                    "our_valid": extracted_valid,
                    "killernay_valid": ref_valid,
                    "delta": delta,
                    "abs_delta": abs(delta),
                    "weak_summary": weak_summary,
                    "vote_count": vote_count,
                    "vote_sum": vote_sum,
                    "mismatch_type": mismatch_type,
                }
            )

    mismatches.sort(key=lambda x: x["abs_delta"], reverse=True)
    type_counts = Counter(x["mismatch_type"] for x in mismatches)

    guidance = {
        "sum_inconsistency_in_our_data": "Recompute totals from row-level votes and reject record when sum != valid_votes.",
        "catastrophic_parse_or_truncation": "Add strict numeric sanity checks and rerun extraction with stronger prompt/OCR fallback.",
        "weak_summary_source_low_confidence": "Prioritize raw image OCR or manual verification for weak summary rows.",
        "small_numeric_noise": "Apply targeted digit normalization and small-value correction pass.",
        "medium_digit_parse_error": "Use per-cell OCR or candidate-row crops for re-read.",
        "likely_thousand_block_or_grouping_error": "Check Thai separators/grouping, missing leading digits, and comma/space parse.",
        "partial_row_capture": "Detect missing rows and run continuation/page-layout-aware extraction.",
        "major_structural_mismatch": "Likely wrong form/page mapping; verify province/district/form assignment first.",
        "other_mismatch": "Manual review needed.",
    }

    OUT_JSON.write_text(
        json.dumps(
            {
                "rows_with_ref": total_with_ref,
                "exact_match": exact,
                "mismatch_rows": len(mismatches),
                "mismatch_rate": (len(mismatches) / total_with_ref) if total_with_ref else 0.0,
                "mismatch_type_counts": dict(type_counts),
                "guidance": guidance,
                "top_mismatches": mismatches[:50],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    with OUT_CSV.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "drive_id",
                "name",
                "province",
                "district",
                "election_type",
                "our_valid",
                "killernay_valid",
                "delta",
                "abs_delta",
                "weak_summary",
                "vote_count",
                "vote_sum",
                "mismatch_type",
            ],
        )
        w.writeheader()
        w.writerows(mismatches)

    print(f"rows_with_ref={total_with_ref} exact={exact} mismatch={len(mismatches)}")
    print(f"wrote {OUT_JSON}")
    print(f"wrote {OUT_CSV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

