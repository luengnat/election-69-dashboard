#!/usr/bin/env python3
"""Build a unified district-level comparison table across ECT + killernay + extracted data."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


def load_extracted(path: Path) -> pd.DataFrame:
    obj = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for it in obj.get("items", []):
        rows.append(
            {
                "province": it.get("province"),
                "district": it.get("district_number"),
                "election_type": it.get("form_type"),
                "drive_id": it.get("drive_id"),
                "extracted_valid": it.get("valid_votes_extracted"),
                "weak_summary": it.get("weak_summary", False),
            }
        )
    return pd.DataFrame(rows)


def load_killernay(base: Path) -> pd.DataFrame:
    summary = pd.read_csv(base / "summary_winners.csv")
    party = pd.read_csv(base / "party_list.csv")

    cons = summary[["จังหวัด", "เขต", "คะแนนดี"]].copy()
    cons.columns = ["province", "district", "ref_valid"]
    cons["election_type"] = "constituency"

    party_agg = (
        party.groupby(["จังหวัด", "เขต"], as_index=False)["คะแนน"].sum()
        .rename(columns={"จังหวัด": "province", "เขต": "district", "คะแนน": "ref_valid"})
    )
    party_agg["election_type"] = "party_list"

    return pd.concat([cons, party_agg], ignore_index=True)


def main() -> int:
    repo = Path("/Users/nat/dev/election")
    extracted = load_extracted(repo / "docs/data/district_dashboard_data.json")
    killernay_candidates = [
        Path("/tmp/election-69-OCR-result-codex-latest/data/csv"),
        Path("/tmp/election-69-OCR-result-codex/data/csv"),
    ]
    killernay_base = next((p for p in killernay_candidates if p.exists()), killernay_candidates[0])
    killernay = load_killernay(killernay_base)

    merged = extracted.merge(
        killernay,
        how="left",
        on=["province", "district", "election_type"],
    )
    merged["delta_valid_vs_killernay"] = merged["extracted_valid"] - merged["ref_valid"]
    merged["exact_killernay"] = merged["delta_valid_vs_killernay"] == 0

    out_json = repo / "comparison_unified_preview.json"
    out_csv = repo / "comparison_unified_preview.csv"

    merged.to_csv(out_csv, index=False)
    out_json.write_text(
        json.dumps(
            {
                "rows": int(len(merged)),
                "with_killernay_ref": int(merged["ref_valid"].notna().sum()),
                "with_extracted_valid": int(merged["extracted_valid"].notna().sum()),
                "exact_killernay": int((merged["exact_killernay"] == True).sum()),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"wrote {out_csv}")
    print(f"wrote {out_json}")
    print(f"killernay_base={killernay_base}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
