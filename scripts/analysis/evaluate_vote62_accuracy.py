#!/usr/bin/env python3
"""
Evaluate OCR backend accuracy against Vote62 unit-level final scores.

Example:
  python evaluate_vote62_accuracy.py \
    --province กระบี่ \
    --constituency 1 \
    --form-type "ส.ส. 5/18" \
    --backends tesseract,paddle \
    --limit 20
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from dataclasses import dataclass, asdict
from typing import Optional

import requests

from ballot_types import FormType
from model_backends import EnsembleExtractor, build_backends_from_env
from vote62_api import (
    list_polling_stations,
    get_polling_station_full,
    parse_final_score,
    to_vote62_election_type,
)


def _safe_int(value, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(float(value))
    except Exception:
        return default


def _normalize_votes_map(v: dict) -> dict[str, int]:
    out: dict[str, int] = {}
    for k, val in (v or {}).items():
        key = str(k).strip()
        if not key.isdigit():
            continue
        out[key] = _safe_int(val, 0)
    return out


def _form_type_from_text(text: str) -> Optional[FormType]:
    text = (text or "").strip()
    if not text:
        return None
    try:
        return FormType(text)
    except Exception:
        return None


def _pick_score_image_url(full_data: dict, election_type: str) -> Optional[str]:
    """
    Pick one representative score image URL for the election type.
    """
    score_images = full_data.get("scoreImages", [])
    if isinstance(score_images, list):
        for row in score_images:
            if row.get("electionType") != election_type:
                continue
            photos = row.get("photos", [])
            if isinstance(photos, list) and photos:
                return photos[0]
    reports = full_data.get("reports", [])
    if isinstance(reports, list):
        for rep in reports:
            rows = rep.get("scoreImages", [])
            if not isinstance(rows, list):
                continue
            for row in rows:
                if row.get("electionType") != election_type:
                    continue
                photos = row.get("photos", [])
                if isinstance(photos, list) and photos:
                    return photos[0]
    return None


@dataclass
class UnitEval:
    unit: int
    station_id: str
    station_name: str
    image_url: str
    extracted: bool
    field_total: int
    field_match: int
    abs_error_sum: int
    unit_exact: bool
    truth_votes: dict[str, int]
    pred_votes: dict[str, int]
    error: str = ""


def evaluate(
    province: str,
    constituency: int,
    form_type_text: str,
    backends_spec: str,
    limit: int,
    output_json: str,
):
    os.environ["EXTRACTION_BACKENDS"] = backends_spec
    extractor = EnsembleExtractor(build_backends_from_env())
    election_type = to_vote62_election_type(form_type_text)
    form_type_obj = _form_type_from_text(form_type_text)

    stations = [s for s in list_polling_stations(province, constituency) if s.get("id")]
    stations = sorted(stations, key=lambda x: x.get("unit", 0))
    if limit > 0:
        stations = stations[:limit]

    results: list[UnitEval] = []

    for row in stations:
        station_id = row["id"]
        station_name = row.get("name", "")
        unit_no = _safe_int(row.get("unit", 0), 0)
        full = get_polling_station_full(station_id)
        if not full:
            results.append(
                UnitEval(
                    unit=unit_no,
                    station_id=station_id,
                    station_name=station_name,
                    image_url="",
                    extracted=False,
                    field_total=0,
                    field_match=0,
                    abs_error_sum=0,
                    unit_exact=False,
                    truth_votes={},
                    pred_votes={},
                    error="full_record_missing",
                )
            )
            continue

        truth = parse_final_score(full, election_type)
        truth_votes = _normalize_votes_map(truth["votes"])
        if not truth_votes:
            continue

        image_url = _pick_score_image_url(full, election_type)
        if not image_url:
            results.append(
                UnitEval(
                    unit=unit_no,
                    station_id=station_id,
                    station_name=station_name,
                    image_url="",
                    extracted=False,
                    field_total=len(truth_votes),
                    field_match=0,
                    abs_error_sum=sum(abs(v) for v in truth_votes.values()),
                    unit_exact=False,
                    truth_votes=truth_votes,
                    pred_votes={},
                    error="score_image_missing",
                )
            )
            continue

        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            resp = requests.get(image_url, timeout=30)
            resp.raise_for_status()
            with open(tmp_path, "wb") as f:
                f.write(resp.content)

            ballot = extractor.extract(tmp_path, form_type_obj)
            if ballot is None:
                results.append(
                    UnitEval(
                        unit=unit_no,
                        station_id=station_id,
                        station_name=station_name,
                        image_url=image_url,
                        extracted=False,
                        field_total=len(truth_votes),
                        field_match=0,
                        abs_error_sum=sum(abs(v) for v in truth_votes.values()),
                        unit_exact=False,
                        truth_votes=truth_votes,
                        pred_votes={},
                        error="extract_none",
                    )
                )
                continue

            pred_raw = ballot.party_votes if election_type == "Party" else ballot.vote_counts
            pred_votes = _normalize_votes_map(pred_raw)

            all_keys = sorted(set(truth_votes.keys()) | set(pred_votes.keys()), key=lambda x: int(x))
            field_total = len(all_keys)
            field_match = 0
            abs_error_sum = 0
            for key in all_keys:
                t = _safe_int(truth_votes.get(key, 0), 0)
                p = _safe_int(pred_votes.get(key, 0), 0)
                if t == p:
                    field_match += 1
                abs_error_sum += abs(t - p)

            results.append(
                UnitEval(
                    unit=unit_no,
                    station_id=station_id,
                    station_name=station_name,
                    image_url=image_url,
                    extracted=True,
                    field_total=field_total,
                    field_match=field_match,
                    abs_error_sum=abs_error_sum,
                    unit_exact=(field_total > 0 and field_match == field_total),
                    truth_votes=truth_votes,
                    pred_votes=pred_votes,
                )
            )
        except Exception as e:
            results.append(
                UnitEval(
                    unit=unit_no,
                    station_id=station_id,
                    station_name=station_name,
                    image_url=image_url,
                    extracted=False,
                    field_total=len(truth_votes),
                    field_match=0,
                    abs_error_sum=sum(abs(v) for v in truth_votes.values()),
                    unit_exact=False,
                    truth_votes=truth_votes,
                    pred_votes={},
                    error=str(e),
                )
            )
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    evaluated = [r for r in results if r.field_total > 0]
    units = len(evaluated)
    extracted_units = sum(1 for r in evaluated if r.extracted)
    exact_units = sum(1 for r in evaluated if r.unit_exact)
    total_fields = sum(r.field_total for r in evaluated)
    matched_fields = sum(r.field_match for r in evaluated)
    abs_error_sum = sum(r.abs_error_sum for r in evaluated)

    summary = {
        "province": province,
        "constituency": constituency,
        "form_type": form_type_text,
        "election_type": election_type,
        "backends": backends_spec,
        "units_evaluated": units,
        "units_extracted": extracted_units,
        "unit_exact_match_rate": (exact_units / units) if units else 0.0,
        "field_accuracy": (matched_fields / total_fields) if total_fields else 0.0,
        "mean_abs_error_per_field": (abs_error_sum / total_fields) if total_fields else 0.0,
    }

    report = {"summary": summary, "units": [asdict(r) for r in evaluated]}
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Saved detailed report: {output_json}")


def main():
    parser = argparse.ArgumentParser(description="Evaluate OCR accuracy against Vote62 unit-level labels")
    parser.add_argument("--province", required=True, help="Thai province name, e.g. กระบี่")
    parser.add_argument("--constituency", type=int, required=True, help="Constituency number")
    parser.add_argument(
        "--form-type",
        default="ส.ส. 5/18",
        help='Form type text, e.g. "ส.ส. 5/18" or "ส.ส. 5/18 (บช)"',
    )
    parser.add_argument(
        "--backends",
        default="tesseract,paddle",
        help='EXTRACTION_BACKENDS spec, e.g. "tesseract,trocr,paddle"',
    )
    parser.add_argument("--limit", type=int, default=10, help="Max polling units to evaluate")
    parser.add_argument(
        "--output-json",
        default="vote62_accuracy_report.json",
        help="Output JSON report path",
    )
    args = parser.parse_args()

    evaluate(
        province=args.province,
        constituency=args.constituency,
        form_type_text=args.form_type,
        backends_spec=args.backends,
        limit=args.limit,
        output_json=args.output_json,
    )


if __name__ == "__main__":
    main()

