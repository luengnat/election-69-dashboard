#!/usr/bin/env python3
from __future__ import annotations

import json
import csv
from collections import defaultdict
from pathlib import Path

from ect_api import ECTData
from vote62_api import list_polling_stations

PROVINCE_ALIASES = {
    "Bangkok": "กรุงเทพมหานคร",
    "Nakhon Si Thammarat": "นครศรีธรรมราช",
    "Sakon Nakhon": "สกลนคร",
}


def _normalize_province_name(name: str) -> str:
    raw = str(name or "").strip()
    return PROVINCE_ALIASES.get(raw, raw)


def _to_int_or_none(value) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except Exception:
        return None


def _expected_rows_from_ect(ect: ECTData) -> list[tuple[str, int, str]]:
    """
    Build complete district/form coverage from ECT constituency definitions.
    Each constituency should have both constituency + party-list district-level rows.
    """
    rows: list[tuple[str, int, str]] = []
    for cons in ect._constituencies.values():
        prov = ect._provinces.get(cons.prov_id)
        if not prov:
            continue
        district = int(cons.cons_no)
        province = str(prov.name)
        rows.append((province, district, "constituency"))
        rows.append((province, district, "party_list"))
    rows.sort(key=lambda x: (x[0], x[1], x[2]))
    return rows


def _placeholder_item(province: str, district: int, form_type: str) -> dict:
    form_label = "บช" if form_type == "party_list" else "แบ่งเขต"
    synthetic_id = f"missing::{province}::{district}::{form_type}"
    return {
        "drive_id": synthetic_id,
        "name": f"{province} เขต {district} ({form_label})",
        "province": province,
        "district_number": district,
        "form_type": form_type,
        "drive_url": "",
        "valid_votes_extracted": None,
        "invalid_votes": None,
        "blank_votes": None,
        "votes": {},
        "candidate_names": {},
        "candidate_parties": {},
        "party_names": {},
        "weak_summary": True,
        "ocr_check": {"exact": False, "delta": None},
        "summary_preview": "No extracted OCR/Gemini row yet for this district/form.",
        "availability": {
            "has_extracted": False,
            "has_ect": False,
            "has_vote62": False,
            "has_killernay": False,
        },
    }


def build_ect_cons_id_map(ect: ECTData) -> dict[tuple[str, int], str]:
    out: dict[tuple[str, int], str] = {}
    # _constituencies are loaded in ect.load()
    for cons in ect._constituencies.values():
        prov = ect._provinces.get(cons.prov_id)
        if not prov:
            continue
        out[(prov.name, int(cons.cons_no))] = cons.cons_id
    return out


def _load_killernay_csv(path: Path) -> dict[tuple[str, int], dict[str, int]]:
    by_dist: dict[tuple[str, int], dict[str, int]] = defaultdict(dict)
    if not path.exists():
        return by_dist
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            prov = _normalize_province_name(row.get("จังหวัด", ""))
            if not prov:
                continue
            try:
                dist = int(float(row.get("เขต", 0) or 0))
                num = int(float(row.get("หมายเลข", 0) or 0))
                score = int(float(row.get("คะแนน", 0) or 0))
            except Exception:
                continue
            if dist <= 0 or num <= 0:
                continue
            by_dist[(prov, dist)][str(num)] = score
    return by_dist


def agg_vote62_district(province: str, district: int, election_type: str) -> dict:
    """
    Aggregate Vote62 polling station finalScoreResults by district.
    election_type: 'Party' | 'FPTP'
    """
    try:
        rows = list_polling_stations(province, district)
    except Exception:
        return {"votes": {}, "valid_votes": None, "invalid_votes": None, "blank_votes": None, "station_count": 0}

    votes: dict[str, int] = defaultdict(int)
    valid_votes = 0
    invalid_votes = 0
    blank_votes = 0
    has_totals = False
    for row in rows:
        raw = row.get("raw") or {}
        final = raw.get("finalScoreResults") or {}
        entries = final.get(election_type) or []
        if not isinstance(entries, list):
            continue
        for e in entries:
            label = str(e.get("label", "")).strip()
            try:
                value = int(float(e.get("value", 0) or 0))
            except Exception:
                value = 0
            if label.isdigit():
                votes[label] += value
            elif label == "goodVote":
                valid_votes += value
                has_totals = True
            elif label == "void":
                invalid_votes += value
                has_totals = True
            elif label == "noVote":
                blank_votes += value
                has_totals = True

    if not has_totals:
        valid_votes = None
        invalid_votes = None
        blank_votes = None
    return {
        "votes": dict(sorted(votes.items(), key=lambda kv: int(kv[0]))),
        "valid_votes": valid_votes,
        "invalid_votes": invalid_votes,
        "blank_votes": blank_votes,
        "station_count": len(rows),
    }


def main() -> int:
    candidate_paths = [
        Path("/tmp/e69-dashboard-publish/docs/data/district_dashboard_data.json"),
        Path(__file__).resolve().parent / "docs/data/district_dashboard_data.json",
    ]
    data_path = next((p for p in candidate_paths if p.exists()), candidate_paths[0])
    data = json.loads(data_path.read_text(encoding="utf-8"))
    raw_items = data.get("items", [])

    ect = ECTData()
    ect.load()
    ect.load_official_results()
    cons_id_map = build_ect_cons_id_map(ect)

    killernay_bases = [
        Path("/tmp/election-69-OCR-result-codex-latest/data/csv"),
        Path("/tmp/election-69-OCR-result-codex/data/csv"),
    ]
    killernay_base = next((p for p in killernay_bases if p.exists()), killernay_bases[0])
    killernay_party = _load_killernay_csv(killernay_base / "party_list.csv")
    killernay_cons = _load_killernay_csv(killernay_base / "constituency.csv")

    # Build a complete row set so every district/form is visible even if extraction is missing.
    existing_by_key: dict[tuple[str, int, str], dict] = {}
    extra_items: list[dict] = []
    for it in raw_items:
        province_norm = _normalize_province_name(it.get("province", ""))
        district = _to_int_or_none(it.get("district_number")) or 0
        form_type = str(it.get("form_type") or "")
        if not province_norm or district <= 0 or form_type not in {"constituency", "party_list"}:
            extra_items.append(it)
            continue
        key = (province_norm, district, form_type)
        if key not in existing_by_key:
            it["province"] = province_norm
            existing_by_key[key] = it
            continue
        # Preserve duplicate rows as extras so we do not silently drop data.
        extra_items.append(it)

    complete_items: list[dict] = []
    expected_rows = _expected_rows_from_ect(ect)
    for province, district, form_type in expected_rows:
        key = (province, district, form_type)
        row = existing_by_key.get(key)
        if row is None:
            row = _placeholder_item(province, district, form_type)
        complete_items.append(row)

    # Keep unkeyed/duplicate legacy rows at the end.
    items = complete_items + extra_items

    vote62_cache: dict[tuple[str, int, str], dict] = {}

    with_ect = 0
    with_vote62 = 0
    with_killernay = 0
    for it in items:
        province = it.get("province", "")
        province_norm = _normalize_province_name(province)
        district = int(it.get("district_number") or 0)
        form_type = it.get("form_type")
        my_votes = {str(k): int(v) for k, v in (it.get("votes") or {}).items()}
        my_valid = _to_int_or_none(it.get("valid_votes_extracted"))
        my_invalid = _to_int_or_none(it.get("invalid_votes"))
        my_blank = _to_int_or_none(it.get("blank_votes"))

        # ECT aggregate
        ect_votes = {}
        ect_valid = None
        ect_invalid = None
        ect_blank = None
        cons_id = cons_id_map.get((province_norm, district))
        if cons_id:
            r = ect.get_official_constituency_results(cons_id)
            if r:
                if form_type == "party_list":
                    ect_votes = {str(k): int(v) for k, v in (r.get("party_votes") or {}).items()}
                else:
                    ect_votes = {str(k): int(v) for k, v in (r.get("vote_counts") or {}).items()}
                ect_valid = int(r.get("valid_votes") or 0)
                ect_invalid = int(r.get("invalid_votes") or 0)
                ect_blank = int(r.get("blank_votes") or 0)
                with_ect += 1

        # Vote62 aggregate from polling stations
        vote62_type = "Party" if form_type == "party_list" else "FPTP"
        cache_key = (province_norm, district, vote62_type)
        if cache_key not in vote62_cache:
            vote62_cache[cache_key] = agg_vote62_district(province_norm, district, vote62_type)
        v62 = vote62_cache[cache_key]
        if v62.get("votes"):
            with_vote62 += 1

        v62_votes = {str(k): int(v) for k, v in (v62.get("votes") or {}).items()}
        v62_valid = v62.get("valid_votes")
        if isinstance(v62_valid, float):
            v62_valid = int(v62_valid)

        # killernay OCR reference
        if form_type == "party_list":
            k_votes = killernay_party.get((province_norm, district), {})
        else:
            k_votes = killernay_cons.get((province_norm, district), {})
        k_valid = sum(k_votes.values()) if k_votes else None
        if k_votes:
            with_killernay += 1

        it["sources"] = {
            "read": {"votes": my_votes, "valid_votes": my_valid, "invalid_votes": my_invalid, "blank_votes": my_blank},
            "ect": {
                "votes": ect_votes,
                "valid_votes": ect_valid,
                "invalid_votes": ect_invalid,
                "blank_votes": ect_blank,
            },
            "vote62": {"votes": v62_votes, "valid_votes": v62_valid, "station_count": v62.get("station_count", 0)},
            "killernay": {"votes": {str(k): int(v) for k, v in k_votes.items()}, "valid_votes": k_valid},
        }
        it["compare"] = {
            "delta_valid_ect": (my_valid - ect_valid) if (isinstance(my_valid, int) and ect_valid is not None) else None,
            "delta_valid_vote62": (my_valid - v62_valid) if (isinstance(my_valid, int) and isinstance(v62_valid, int)) else None,
            "delta_valid_killernay": (my_valid - k_valid) if (isinstance(my_valid, int) and isinstance(k_valid, int)) else None,
        }
        it["availability"] = {
            "has_extracted": isinstance(my_valid, int),
            "has_ect": ect_valid is not None,
            "has_vote62": isinstance(v62_valid, int),
            "has_killernay": isinstance(k_valid, int),
        }

    data["items"] = items
    summary = data.setdefault("summary", {})
    summary["total_files"] = len(items)
    summary["with_valid_votes"] = sum(1 for it in items if _to_int_or_none(it.get("valid_votes_extracted")) is not None)
    summary["with_ect"] = with_ect
    summary["with_vote62"] = with_vote62
    summary["with_killernay"] = with_killernay
    summary["expected_district_form_rows"] = len(expected_rows)
    summary["missing_extracted_rows"] = sum(1 for it in items if not (it.get("availability") or {}).get("has_extracted"))
    summary["missing_ect_rows"] = sum(1 for it in items if not (it.get("availability") or {}).get("has_ect"))
    summary["missing_vote62_rows"] = sum(1 for it in items if not (it.get("availability") or {}).get("has_vote62"))
    summary["missing_killernay_rows"] = sum(1 for it in items if not (it.get("availability") or {}).get("has_killernay"))
    data["summary"]["with_ect"] = with_ect
    data["summary"]["with_vote62"] = with_vote62
    data["summary"]["with_killernay"] = with_killernay
    data_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"updated {data_path} items={len(items)} with_ect={with_ect} "
        f"with_vote62={with_vote62} with_killernay={with_killernay} "
        f"killernay_base={killernay_base}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
