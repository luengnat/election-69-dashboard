#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any


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
RAW_JSONL = REPO / "drive2_gemini_detailed_raw.jsonl"
HINTS_JSONL = REPO / "drive2_form_type_hints.jsonl"

OUT_FILES_JSON = REPO / "analysis_15_unit_gemini_files.json"
OUT_FILES_CSV = REPO / "analysis_15_unit_gemini_files.csv"
OUT_SUMMARY_JSON = REPO / "analysis_15_unit_gemini_summary.json"
OUT_SUMMARY_CSV = REPO / "analysis_15_unit_gemini_summary.csv"

THAI_TO_ARABIC = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")


def _safe_int(v: Any) -> int | None:
    if v in (None, ""):
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        try:
            return int(v)
        except Exception:
            return None
    s = str(v).strip().translate(THAI_TO_ARABIC)
    if not s:
        return None
    s = s.replace(",", "")
    m = re.search(r"-?\d+", s)
    if not m:
        return None
    try:
        return int(m.group(0))
    except Exception:
        return None


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out


def _extract_json_block(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    if not raw:
        return None
    raw = re.sub(r"^View more\s*", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"\s*```$", "", raw)

    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end <= start:
        return None
    cand = raw[start : end + 1]
    try:
        obj = json.loads(cand)
    except Exception:
        return None
    return obj if isinstance(obj, dict) else None


def _hint_index(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        did = str(r.get("drive_id", "")).strip()
        if did:
            out[did] = r
    return out


def _normalize_form_type(v: Any) -> str:
    s = str(v or "").strip().translate(THAI_TO_ARABIC)
    s = re.sub(r"\s+", " ", s)
    return s


def _infer_unit_from_name(name: str) -> int | None:
    s = str(name or "").strip().translate(THAI_TO_ARABIC)
    if not s:
        return None
    # Common patterns:
    # - "เทศบาลเมืองเนินพระ - 006 - บัญชีรายชื่อ.pdf"
    # - "7. สส.5-18 บช.pdf"
    # - "หน่วยเลือกตั้งที่ 12 ..."
    for pat in (
        r"หน่วยเลือกตั้งที่\s*([0-9]{1,3})",
        r"หน่วยที่\s*([0-9]{1,3})",
        r"(?:^|[\s\-_])([0-9]{1,3})(?:[\s\-_]|\.pdf|$)",
        r"^([0-9]{1,3})\.",
    ):
        m = re.search(pat, s, flags=re.IGNORECASE)
        if not m:
            continue
        n = _safe_int(m.group(1))
        if n is not None and 1 <= n <= 400:
            return n
    return None


def _extract_totals(form: dict[str, Any]) -> tuple[int | None, int | None, int | None]:
    totals = form.get("totals") if isinstance(form.get("totals"), dict) else {}
    if not totals:
        totals = form
    valid = _safe_int(totals.get("valid_votes"))
    invalid = _safe_int(totals.get("invalid_votes"))
    blank = _safe_int(totals.get("blank_votes"))
    return valid, invalid, blank


def main() -> int:
    target_keys = {(p, d) for p, d, _ in TARGETS}
    score_hints = {(p, d): s for p, d, s in TARGETS}

    hint_rows = _read_jsonl(HINTS_JSONL)
    hints_by_id = _hint_index(hint_rows)
    raw_rows = _read_jsonl(RAW_JSONL)

    per_file: list[dict[str, Any]] = []

    for row in raw_rows:
        drive_id = str(row.get("drive_id", "")).strip()
        if not drive_id:
            continue
        hint = hints_by_id.get(drive_id, {})

        province = str(hint.get("province") or row.get("province_hint") or "").strip()
        district = _safe_int(hint.get("district_number"))
        if district is None:
            district = _safe_int(hint.get("constituency_number"))
        if district is None:
            district = _safe_int(row.get("district_number_hint"))

        if not province or district is None or (province, district) not in target_keys:
            continue

        raw_obj = _extract_json_block(str(row.get("summary") or ""))
        forms = raw_obj.get("forms") if isinstance(raw_obj, dict) else []
        if not isinstance(forms, list):
            forms = []

        if not forms:
            per_file.append(
                {
                    "drive_id": drive_id,
                    "name": str(row.get("name", "")).strip(),
                    "province": province,
                    "district_number": district,
                    "score_hint": score_hints.get((province, district), ""),
                    "parse_status": "no-forms",
                    "form_count": 0,
                    "form_type": None,
                    "location_kind": str(hint.get("location_kind") or row.get("location_kind_hint") or "").strip(),
                    "unit_number": _safe_int(hint.get("unit_number") or row.get("unit_number_hint")),
                    "committee_number": _safe_int(hint.get("committee_number") or row.get("committee_number_hint")),
                    "valid_votes": None,
                    "invalid_votes": None,
                    "blank_votes": None,
                    "row_count": 0,
                }
            )
            continue

        for idx, form in enumerate(forms, start=1):
            if not isinstance(form, dict):
                continue
            valid, invalid, blank = _extract_totals(form)
            rows = form.get("rows") if isinstance(form.get("rows"), list) else []
            form_unit = _safe_int(form.get("unit_number"))
            form_committee = _safe_int(form.get("committee_number"))
            hint_unit = _safe_int(hint.get("unit_number") or row.get("unit_number_hint"))
            hint_committee = _safe_int(hint.get("committee_number") or row.get("committee_number_hint"))
            location_kind = str(hint.get("location_kind") or row.get("location_kind_hint") or "").strip()
            unit_number = hint_unit if hint_unit is not None else form_unit
            committee_number = hint_committee if hint_committee is not None else form_committee
            if unit_number is None:
                unit_number = _infer_unit_from_name(str(row.get("name", "")))

            per_file.append(
                {
                    "drive_id": drive_id,
                    "name": str(row.get("name", "")).strip(),
                    "province": province,
                    "district_number": district,
                    "score_hint": score_hints.get((province, district), ""),
                    "parse_status": "ok",
                    "form_count": len(forms),
                    "form_index": idx,
                    "form_type": _normalize_form_type(form.get("form_type")),
                    "is_unit_form": bool("5/18" in _normalize_form_type(form.get("form_type"))),
                    "location_kind": location_kind,
                    "unit_number": unit_number,
                    "committee_number": committee_number,
                    "valid_votes": valid,
                    "invalid_votes": invalid,
                    "blank_votes": blank,
                    "row_count": len(rows),
                }
            )

    summary_map: dict[tuple[str, int], dict[str, Any]] = {}
    by_key_rows: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for r in per_file:
        key = (r["province"], r["district_number"])
        by_key_rows[key].append(r)

    for province, district, hint in TARGETS:
        rows = by_key_rows.get((province, district), [])
        ok_rows = [r for r in rows if r.get("parse_status") == "ok"]
        unit_form_rows = [r for r in ok_rows if bool(r.get("is_unit_form"))]
        with_unit = [r for r in ok_rows if r.get("unit_number") is not None]
        with_totals = [
            r
            for r in ok_rows
            if r.get("valid_votes") is not None
            and r.get("invalid_votes") is not None
            and r.get("blank_votes") is not None
        ]
        with_vote_rows = [r for r in ok_rows if (_safe_int(r.get("row_count")) or 0) > 0]

        unit_with_unit = [r for r in unit_form_rows if r.get("unit_number") is not None]
        unit_with_totals = [
            r
            for r in unit_form_rows
            if r.get("valid_votes") is not None
            and r.get("invalid_votes") is not None
            and r.get("blank_votes") is not None
        ]
        unit_with_vote_rows = [r for r in unit_form_rows if (_safe_int(r.get("row_count")) or 0) > 0]

        uniq_units = sorted({int(r["unit_number"]) for r in with_unit if _safe_int(r.get("unit_number")) is not None})
        unit_uniq_units = sorted(
            {int(r["unit_number"]) for r in unit_with_unit if _safe_int(r.get("unit_number")) is not None}
        )
        valid_sum = sum(int(r["valid_votes"]) for r in with_totals)
        invalid_sum = sum(int(r["invalid_votes"]) for r in with_totals)
        blank_sum = sum(int(r["blank_votes"]) for r in with_totals)
        unit_valid_sum = sum(int(r["valid_votes"]) for r in unit_with_totals)
        unit_invalid_sum = sum(int(r["invalid_votes"]) for r in unit_with_totals)
        unit_blank_sum = sum(int(r["blank_votes"]) for r in unit_with_totals)

        summary_map[(province, district)] = {
            "province": province,
            "district_number": district,
            "score_hint": hint,
            "source_files": len(rows),
            "parsed_forms": len(ok_rows),
            "with_unit_number": len(with_unit),
            "unique_unit_count": len(uniq_units),
            "with_totals_complete": len(with_totals),
            "with_vote_rows": len(with_vote_rows),
            "sum_valid_votes_from_complete_rows": valid_sum if with_totals else None,
            "sum_invalid_votes_from_complete_rows": invalid_sum if with_totals else None,
            "sum_blank_votes_from_complete_rows": blank_sum if with_totals else None,
            "unit_form_rows": len(unit_form_rows),
            "unit_form_with_unit_number": len(unit_with_unit),
            "unit_form_unique_unit_count": len(unit_uniq_units),
            "unit_form_with_totals_complete": len(unit_with_totals),
            "unit_form_with_vote_rows": len(unit_with_vote_rows),
            "unit_form_sum_valid_votes": unit_valid_sum if unit_with_totals else None,
            "unit_form_sum_invalid_votes": unit_invalid_sum if unit_with_totals else None,
            "unit_form_sum_blank_votes": unit_blank_sum if unit_with_totals else None,
            "status": "ready-for-review" if unit_with_totals else ("partial" if rows else "missing"),
        }

    summary_items = [summary_map[(p, d)] for p, d, _ in TARGETS]

    OUT_FILES_JSON.write_text(
        json.dumps({"rows": len(per_file), "items": per_file}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    OUT_SUMMARY_JSON.write_text(
        json.dumps({"rows": len(summary_items), "items": summary_items}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    with OUT_FILES_CSV.open("w", newline="", encoding="utf-8") as fh:
        fields = [
            "drive_id",
            "name",
            "province",
            "district_number",
            "score_hint",
            "parse_status",
            "form_count",
            "form_index",
            "form_type",
            "is_unit_form",
            "location_kind",
            "unit_number",
            "committee_number",
            "valid_votes",
            "invalid_votes",
            "blank_votes",
            "row_count",
        ]
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in per_file:
            writer.writerow({k: row.get(k) for k in fields})

    with OUT_SUMMARY_CSV.open("w", newline="", encoding="utf-8") as fh:
        fields = [
            "province",
            "district_number",
            "score_hint",
            "source_files",
            "parsed_forms",
            "with_unit_number",
            "unique_unit_count",
            "with_totals_complete",
            "with_vote_rows",
            "sum_valid_votes_from_complete_rows",
            "sum_invalid_votes_from_complete_rows",
            "sum_blank_votes_from_complete_rows",
            "unit_form_rows",
            "unit_form_with_unit_number",
            "unit_form_unique_unit_count",
            "unit_form_with_totals_complete",
            "unit_form_with_vote_rows",
            "unit_form_sum_valid_votes",
            "unit_form_sum_invalid_votes",
            "unit_form_sum_blank_votes",
            "status",
        ]
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in summary_items:
            writer.writerow({k: row.get(k) for k in fields})

    print(f"wrote {OUT_FILES_JSON}")
    print(f"wrote {OUT_FILES_CSV}")
    print(f"wrote {OUT_SUMMARY_JSON}")
    print(f"wrote {OUT_SUMMARY_CSV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
