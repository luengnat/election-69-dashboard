#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class ValidationIssue:
    issue_type: str
    province: str
    district_number: int | None
    form_type: str
    drive_id: str
    detail: str


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


def _sum_votes(votes: dict[str, Any], party_list_only: bool) -> int:
    total = 0
    for key, value in votes.items():
        if not str(key).isdigit():
            continue
        n_key = int(key)
        if party_list_only and not (1 <= n_key <= 57):
            continue
        n_val = _to_int(value)
        if n_val is None:
            continue
        total += n_val
    return total


def validate_dashboard_data(payload: dict[str, Any]) -> tuple[list[ValidationIssue], dict[str, int]]:
    items = payload.get("items", [])
    issues: list[ValidationIssue] = []
    stats = {
        "rows": 0,
        "party_list_rows": 0,
        "constituency_rows": 0,
        "party_list_sum_checks": 0,
        "total_ballot_checks": 0,
    }

    for row in items:
        stats["rows"] += 1
        province = str(row.get("province") or "")
        district_number = _to_int(row.get("district_number"))
        form_type = str(row.get("form_type") or "")
        drive_id = str(row.get("drive_id") or "")
        availability = row.get("availability") or {}
        has_extracted = bool(availability.get("has_extracted"))
        votes = row.get("votes") or {}
        validation_notes = set(row.get("validation_notes") or [])
        doc_total_inconsistent = "document_total_inconsistent" in validation_notes
        valid = _to_int(row.get("valid_votes_extracted"))
        invalid = _to_int(row.get("invalid_votes"))
        blank = _to_int(row.get("blank_votes"))
        total_votes = _to_int(row.get("total_votes"))

        if form_type == "party_list":
            stats["party_list_rows"] += 1
            # Skip sum-vs-valid checks for no-file/no-read rows.
            if has_extracted and isinstance(votes, dict) and valid is not None:
                stats["party_list_sum_checks"] += 1
                vote_sum = _sum_votes(votes, party_list_only=True)
                if vote_sum != valid:
                    issues.append(
                        ValidationIssue(
                            issue_type="party_list_sum_mismatch",
                            province=province,
                            district_number=district_number,
                            form_type=form_type,
                            drive_id=drive_id,
                            detail=f"sum(votes)={vote_sum} but valid_votes_extracted={valid}",
                        )
                    )
        elif form_type == "constituency":
            stats["constituency_rows"] += 1

        if valid is not None and invalid is not None and blank is not None and total_votes is not None:
            stats["total_ballot_checks"] += 1
            expected_total = valid + invalid + blank
            if expected_total != total_votes and not doc_total_inconsistent:
                issues.append(
                    ValidationIssue(
                        issue_type="total_ballot_mismatch",
                        province=province,
                        district_number=district_number,
                        form_type=form_type,
                        drive_id=drive_id,
                        detail=f"valid+invalid+blank={expected_total} but total_votes={total_votes}",
                    )
                )

    return issues, stats


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate docs/data/district_dashboard_data.json integrity")
    parser.add_argument(
        "--input",
        default="docs/data/district_dashboard_data.json",
        help="Path to dashboard data JSON",
    )
    parser.add_argument(
        "--report",
        default="docs/data/validation_report.json",
        help="Output report JSON path",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    report_path = Path(args.report)

    payload = json.loads(input_path.read_text(encoding="utf-8"))
    issues, stats = validate_dashboard_data(payload)

    report = {
        "input": str(input_path),
        "stats": stats,
        "issue_count": len(issues),
        "issues": [issue.__dict__ for issue in issues],
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Validation complete: {len(issues)} issue(s)")
    print(f"Report: {report_path}")
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
