#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from vote62_api import list_polling_stations


TARGETS: list[tuple[str, int, str]] = [
    ("เชียงใหม่", 1, "68.83%"),
    ("สมุทรปราการ", 4, "66.86%"),
    ("สุโขทัย", 2, "64.82%"),
    ("มหาสารคาม", 1, "64.81%"),
    ("ระยอง", 1, "64.00%"),
    ("เชียงราย", 6, "53.75%"),
    ("สกลนคร", 1, "51.50%"),
    ("ขอนแก่น", 2, "47.43%"),
    ("สงขลา", 2, "47.42%"),
    ("นครราชสีมา", 2, "47.42%"),
    ("นราธิวาส", 3, "43.35%"),
    ("นครราชสีมา", 1, "39.41%"),
    ("อุดรธานี", 1, "28.18%"),
    ("ราชบุรี", 4, "27.67%"),
    ("ศรีสะเกษ", 1, "17.54%"),
]

REPO = Path(__file__).resolve().parent
DISTRICT_DATA = REPO / "docs" / "data" / "district_dashboard_data.json"
OUT_SUMMARY_JSON = REPO / "analysis_15_unit_vs_district_summary.json"
OUT_SUMMARY_CSV = REPO / "analysis_15_unit_vs_district_summary.csv"
OUT_UNITS_JSON = REPO / "analysis_15_unit_vs_district_units.json"
OUT_UNITS_CSV = REPO / "analysis_15_unit_vs_district_units.csv"


def _safe_int(v: Any) -> int | None:
    if v in (None, ""):
        return None
    try:
        return int(float(v))
    except Exception:
        return None


def _parse_vote62_entries(entries: Any) -> dict[str, Any]:
    votes: dict[str, int] = {}
    valid_votes = 0
    invalid_votes = 0
    blank_votes = 0
    has_totals = False

    if not isinstance(entries, list):
        return {
            "votes": {},
            "valid_votes": None,
            "invalid_votes": None,
            "blank_votes": None,
        }

    for item in entries:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label", "")).strip()
        value = _safe_int(item.get("value")) or 0
        if label.isdigit():
            votes[label] = value
            continue
        if label == "goodVote":
            valid_votes = value
            has_totals = True
        elif label == "void":
            invalid_votes = value
            has_totals = True
        elif label == "noVote":
            blank_votes = value
            has_totals = True

    return {
        "votes": votes,
        "valid_votes": valid_votes if has_totals else None,
        "invalid_votes": invalid_votes if has_totals else None,
        "blank_votes": blank_votes if has_totals else None,
    }


def _extract_station_payload(station_row: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    raw = station_row.get("raw") or {}
    final = raw.get("finalScoreResults") or {}
    fptp = _parse_vote62_entries(final.get("FPTP"))
    party = _parse_vote62_entries(final.get("Party"))
    return fptp, party


def _load_district_rows() -> dict[tuple[str, int, str], dict[str, Any]]:
    payload = json.loads(DISTRICT_DATA.read_text(encoding="utf-8"))
    out: dict[tuple[str, int, str], dict[str, Any]] = {}
    for row in payload.get("items", []):
        if not isinstance(row, dict):
            continue
        province = str(row.get("province", "")).strip()
        district = _safe_int(row.get("district_number")) or 0
        form_type = str(row.get("form_type", "")).strip()
        if not province or district <= 0 or form_type not in {"constituency", "party_list"}:
            continue
        out[(province, district, form_type)] = row
    return out


def _sum_votes(stations: list[dict[str, Any]], election: str) -> dict[str, Any]:
    votes: dict[str, int] = defaultdict(int)
    valid_votes = 0
    invalid_votes = 0
    blank_votes = 0
    with_totals = 0
    with_any_scores = 0

    for s in stations:
        fptp, party = _extract_station_payload(s)
        parsed = fptp if election == "FPTP" else party
        if parsed["votes"]:
            with_any_scores += 1
        for k, v in parsed["votes"].items():
            votes[k] += int(v)
        if parsed["valid_votes"] is not None:
            valid_votes += int(parsed["valid_votes"])
            invalid_votes += int(parsed["invalid_votes"] or 0)
            blank_votes += int(parsed["blank_votes"] or 0)
            with_totals += 1

    return {
        "votes": dict(sorted(votes.items(), key=lambda kv: int(kv[0]))),
        "valid_votes": valid_votes if with_totals else None,
        "invalid_votes": invalid_votes if with_totals else None,
        "blank_votes": blank_votes if with_totals else None,
        "station_count": len(stations),
        "stations_with_scores": with_any_scores,
        "stations_with_totals": with_totals,
    }


def _district_read_metrics(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {"valid_votes": None, "invalid_votes": None, "blank_votes": None}
    src = row.get("sources") or {}
    read = src.get("read") or {}
    ect = src.get("ect") or {}
    return {
        "read_valid_votes": _safe_int(read.get("valid_votes")),
        "read_invalid_votes": _safe_int(read.get("invalid_votes")),
        "read_blank_votes": _safe_int(read.get("blank_votes")),
        "ect_valid_votes": _safe_int(ect.get("valid_votes")),
        "ect_invalid_votes": _safe_int(ect.get("invalid_votes")),
        "ect_blank_votes": _safe_int(ect.get("blank_votes")),
    }


def main() -> int:
    district_rows = _load_district_rows()

    summary_items: list[dict[str, Any]] = []
    unit_rows: list[dict[str, Any]] = []

    for province, district, hint in TARGETS:
        print(f"[target] {province} เขต {district} ...", flush=True)
        try:
            stations = list_polling_stations(province, district)
        except Exception as exc:
            stations = []
            print(f"  vote62 list error: {exc}", flush=True)

        unit_rows_base = []
        for s in sorted(stations, key=lambda x: int(x.get("unit") or 0)):
            fptp, party = _extract_station_payload(s)
            unit = _safe_int(s.get("unit")) or 0
            sid = str(s.get("id", "")).strip()
            name = str(s.get("name", "")).strip()
            unit_rows_base.append(
                {
                    "province": province,
                    "district_number": district,
                    "unit_number": unit,
                    "station_id": sid,
                    "station_name": name,
                    "fptp_valid_votes": fptp["valid_votes"],
                    "fptp_invalid_votes": fptp["invalid_votes"],
                    "fptp_blank_votes": fptp["blank_votes"],
                    "fptp_votes": fptp["votes"],
                    "party_valid_votes": party["valid_votes"],
                    "party_invalid_votes": party["invalid_votes"],
                    "party_blank_votes": party["blank_votes"],
                    "party_votes": party["votes"],
                }
            )
        unit_rows.extend(unit_rows_base)

        agg_fptp = _sum_votes(stations, "FPTP")
        agg_party = _sum_votes(stations, "Party")
        row_const = district_rows.get((province, district, "constituency"))
        row_party = district_rows.get((province, district, "party_list"))
        m_const = _district_read_metrics(row_const)
        m_party = _district_read_metrics(row_party)

        summary_items.append(
            {
                "province": province,
                "district_number": district,
                "score_hint": hint,
                "stations_total": len(stations),
                "constituency": {
                    "vote62_agg_valid_votes": agg_fptp["valid_votes"],
                    "vote62_agg_invalid_votes": agg_fptp["invalid_votes"],
                    "vote62_agg_blank_votes": agg_fptp["blank_votes"],
                    "vote62_stations_with_scores": agg_fptp["stations_with_scores"],
                    "vote62_stations_with_totals": agg_fptp["stations_with_totals"],
                    **m_const,
                    "delta_vote62_vs_read_valid": (
                        (agg_fptp["valid_votes"] - m_const["read_valid_votes"])
                        if (agg_fptp["valid_votes"] is not None and m_const["read_valid_votes"] is not None)
                        else None
                    ),
                    "delta_vote62_vs_ect_valid": (
                        (agg_fptp["valid_votes"] - m_const["ect_valid_votes"])
                        if (agg_fptp["valid_votes"] is not None and m_const["ect_valid_votes"] is not None)
                        else None
                    ),
                },
                "party_list": {
                    "vote62_agg_valid_votes": agg_party["valid_votes"],
                    "vote62_agg_invalid_votes": agg_party["invalid_votes"],
                    "vote62_agg_blank_votes": agg_party["blank_votes"],
                    "vote62_stations_with_scores": agg_party["stations_with_scores"],
                    "vote62_stations_with_totals": agg_party["stations_with_totals"],
                    **m_party,
                    "delta_vote62_vs_read_valid": (
                        (agg_party["valid_votes"] - m_party["read_valid_votes"])
                        if (agg_party["valid_votes"] is not None and m_party["read_valid_votes"] is not None)
                        else None
                    ),
                    "delta_vote62_vs_ect_valid": (
                        (agg_party["valid_votes"] - m_party["ect_valid_votes"])
                        if (agg_party["valid_votes"] is not None and m_party["ect_valid_votes"] is not None)
                        else None
                    ),
                },
            }
        )

    OUT_SUMMARY_JSON.write_text(
        json.dumps({"rows": len(summary_items), "items": summary_items}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    OUT_UNITS_JSON.write_text(
        json.dumps({"rows": len(unit_rows), "items": unit_rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    summary_fields = [
        "province",
        "district_number",
        "score_hint",
        "stations_total",
        "const_vote62_valid",
        "const_read_valid",
        "const_ect_valid",
        "const_delta_vote62_vs_read",
        "const_delta_vote62_vs_ect",
        "party_vote62_valid",
        "party_read_valid",
        "party_ect_valid",
        "party_delta_vote62_vs_read",
        "party_delta_vote62_vs_ect",
    ]
    with OUT_SUMMARY_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=summary_fields)
        writer.writeheader()
        for row in summary_items:
            writer.writerow(
                {
                    "province": row["province"],
                    "district_number": row["district_number"],
                    "score_hint": row["score_hint"],
                    "stations_total": row["stations_total"],
                    "const_vote62_valid": row["constituency"]["vote62_agg_valid_votes"],
                    "const_read_valid": row["constituency"]["read_valid_votes"],
                    "const_ect_valid": row["constituency"]["ect_valid_votes"],
                    "const_delta_vote62_vs_read": row["constituency"]["delta_vote62_vs_read_valid"],
                    "const_delta_vote62_vs_ect": row["constituency"]["delta_vote62_vs_ect_valid"],
                    "party_vote62_valid": row["party_list"]["vote62_agg_valid_votes"],
                    "party_read_valid": row["party_list"]["read_valid_votes"],
                    "party_ect_valid": row["party_list"]["ect_valid_votes"],
                    "party_delta_vote62_vs_read": row["party_list"]["delta_vote62_vs_read_valid"],
                    "party_delta_vote62_vs_ect": row["party_list"]["delta_vote62_vs_ect_valid"],
                }
            )

    unit_fields = [
        "province",
        "district_number",
        "unit_number",
        "station_id",
        "station_name",
        "fptp_valid_votes",
        "fptp_invalid_votes",
        "fptp_blank_votes",
        "party_valid_votes",
        "party_invalid_votes",
        "party_blank_votes",
    ]
    with OUT_UNITS_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=unit_fields)
        writer.writeheader()
        for row in unit_rows:
            writer.writerow({k: row.get(k) for k in unit_fields})

    print(f"wrote {OUT_SUMMARY_JSON}")
    print(f"wrote {OUT_SUMMARY_CSV}")
    print(f"wrote {OUT_UNITS_JSON}")
    print(f"wrote {OUT_UNITS_CSV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

