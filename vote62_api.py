#!/usr/bin/env python3
"""
Vote62 API helper for polling-unit level score reference.

This source provides crowd/digitized unit-level data, useful as a reference
when official ECT APIs only provide constituency aggregates.
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Optional

import requests


STRUCTURE_URL = (
    "https://vote62-general-66-site.s3.ap-southeast-1.amazonaws.com/"
    "structure_f-69-1.json?q=6.20260207.02"
)
API_LIST_URL = "https://api2.vote62.com/query/polling_stations"
API_FULL_URL = "https://api2.vote62.com/query/polling_stations/{polling_station_id}/full"
HEADERS = {"God-Secret": "wrong-way-driving"}


def _safe_int(value, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(float(value))
    except Exception:
        return default


def _extract_unit_number(name: str) -> int:
    """
    Extract polling unit number from Thai station label.
    Examples:
      '12 เต็นท์บริเวณ...' -> 12
      'หน่วยที่ 28 ...' -> 28
      'ชุดที่ 3 ...' -> 3
    """
    if not name:
        return 0
    patterns = [
        r"(?:หน่วยที่|ชุดที่)\s*(\d+)",
        r"^\s*(\d+)\b",
    ]
    for pattern in patterns:
        m = re.search(pattern, name)
        if m:
            return _safe_int(m.group(1), 0)
    return 0


def _is_party_list_form(form_type: str) -> bool:
    return "(บช)" in (form_type or "")


def _vote62_election_type(form_type: str) -> str:
    """Map local form type string to Vote62 electionType key."""
    if _is_party_list_form(form_type):
        return "Party"
    return "FPTP"


def to_vote62_election_type(form_type: str) -> str:
    """Public wrapper for mapping form type to Vote62 election type."""
    return _vote62_election_type(form_type)


@lru_cache(maxsize=1)
def _load_structure() -> dict:
    response = requests.get(STRUCTURE_URL, timeout=30)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        return {}
    return data


def _voting_district_code(province: str, constituency_no: int) -> Optional[str]:
    """
    Resolve Vote62 voting district code (e.g., 'กระบี่.01').
    """
    if not province or constituency_no <= 0:
        return None
    structure = _load_structure()
    candidates = structure.get("votingDistricts", [])
    target_prefix = f"{province}."
    target_suffix = str(constituency_no)
    for row in candidates:
        code = str(row.get("code", "")).strip()
        if not code.startswith(target_prefix):
            continue
        # Prefer exact district number match from display name.
        name_no = _safe_int(row.get("name", 0), 0)
        if name_no == constituency_no:
            return code
    # Fallback by zero-padded convention.
    fallback = f"{province}.{constituency_no:02d}"
    for row in candidates:
        if str(row.get("code", "")).strip() == fallback:
            return fallback
    return None


def get_voting_district_code(province: str, constituency_no: int) -> Optional[str]:
    """Public wrapper for voting district code resolution."""
    return _voting_district_code(province, constituency_no)


@lru_cache(maxsize=256)
def list_polling_stations(province: str, constituency_no: int) -> list[dict]:
    """
    List polling stations for a province + constituency.

    Returns simplified rows:
      [{"id": "...", "unit": 12, "name": "...", "raw": {...}}, ...]
    """
    province = (province or "").strip()
    constituency_no = _safe_int(constituency_no, 0)
    if not province or constituency_no <= 0:
        return []

    voting_district = _voting_district_code(province, constituency_no)
    if not voting_district:
        return []

    params = {"province": province, "votingDistrict": voting_district}
    resp = requests.get(API_LIST_URL, params=params, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, list):
        return []

    out: list[dict] = []
    for row in data:
        station_info = row.get("polling_station") or row.get("pollingStation") or {}
        name = str(station_info.get("name", ""))
        out.append(
            {
                "id": row.get("id"),
                "unit": _extract_unit_number(name),
                "name": name,
                "raw": row,
            }
        )
    return out


@lru_cache(maxsize=2048)
def get_polling_station_full(polling_station_id: str) -> Optional[dict]:
    """Fetch full Vote62 detail for a polling station id."""
    if not polling_station_id:
        return None
    resp = requests.get(
        API_FULL_URL.format(polling_station_id=polling_station_id),
        headers=HEADERS,
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    return data if isinstance(data, dict) else None


def parse_final_score(full_data: dict, election_type: str) -> dict:
    """
    Parse Vote62 finalScoreResults for one election type into numeric map.
    """
    final_results = (full_data.get("finalScoreResults") or {}).get(election_type, [])
    votes: dict[str, int] = {}
    total_ballots = 0
    valid_votes = 0
    invalid_votes = 0
    blank_votes = 0

    if isinstance(final_results, list):
        for item in final_results:
            label = str(item.get("label", "")).strip()
            value = _safe_int(item.get("value", 0), 0)
            if not label:
                continue
            if label.isdigit():
                votes[label] = value
            elif label == "total":
                total_ballots = value
            elif label == "goodVote":
                valid_votes = value
            elif label == "void":
                invalid_votes = value
            elif label == "noVote":
                blank_votes = value

    return {
        "votes": votes,
        "total_ballots": total_ballots,
        "valid_votes": valid_votes,
        "invalid_votes": invalid_votes,
        "blank_votes": blank_votes,
    }


@lru_cache(maxsize=1024)
def get_unit_score_reference(
    province: str,
    constituency_no: int,
    polling_unit: int,
    form_type: str = "",
) -> Optional[dict]:
    """
    Fetch per-unit vote breakdown from Vote62.

    Returns:
      {
        "source": "vote62",
        "province": "...",
        "constituency": 1,
        "unit": 28,
        "station_name": "...",
        "election_type": "FPTP"|"Party",
        "votes": {"1": 12, "2": 244, ...},
        "total_ballots": 681,
        "valid_votes": 630,
        "invalid_votes": 10,
        "blank_votes": 41,
      }
    """
    province = (province or "").strip()
    constituency_no = _safe_int(constituency_no, 0)
    polling_unit = _safe_int(polling_unit, 0)
    if not province or constituency_no <= 0 or polling_unit <= 0:
        return None

    voting_district = _voting_district_code(province, constituency_no)
    if not voting_district:
        return None

    params = {
        "province": province,
        "votingDistrict": voting_district,
    }
    list_resp = requests.get(API_LIST_URL, params=params, headers=HEADERS, timeout=30)
    list_resp.raise_for_status()
    stations = list_resp.json()
    if not isinstance(stations, list):
        return None

    target = None
    for station in stations:
        station_info = station.get("polling_station") or station.get("pollingStation") or {}
        station_name = str(station_info.get("name", ""))
        unit_no = _extract_unit_number(station_name)
        if unit_no == polling_unit:
            target = station
            break
    if not target:
        return None

    polling_station_id = target.get("id")
    if not polling_station_id:
        return None

    full_data = get_polling_station_full(polling_station_id)
    if not full_data:
        return None

    election_type = _vote62_election_type(form_type)
    parsed = parse_final_score(full_data, election_type)
    votes = parsed["votes"]
    total_ballots = parsed["total_ballots"]
    valid_votes = parsed["valid_votes"]
    invalid_votes = parsed["invalid_votes"]
    blank_votes = parsed["blank_votes"]

    station_info = full_data.get("pollingStation") or target.get("polling_station") or {}

    return {
        "source": "vote62",
        "province": province,
        "constituency": constituency_no,
        "unit": polling_unit,
        "station_name": station_info.get("name", ""),
        "voting_district": station_info.get("votingDistrict", voting_district),
        "election_type": election_type,
        "votes": votes,
        "total_ballots": total_ballots,
        "valid_votes": valid_votes,
        "invalid_votes": invalid_votes,
        "blank_votes": blank_votes,
    }
