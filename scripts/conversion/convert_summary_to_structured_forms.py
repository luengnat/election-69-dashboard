#!/usr/bin/env python3
"""Convert Drive PDF summary text into structured form JSON."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


PROVINCES_TH = [
    "กรุงเทพมหานคร","กระบี่","กาญจนบุรี","กาฬสินธุ์","กำแพงเพชร","ขอนแก่น","จันทบุรี","ฉะเชิงเทรา","ชลบุรี","ชัยนาท",
    "ชัยภูมิ","ชุมพร","เชียงราย","เชียงใหม่","ตรัง","ตราด","ตาก","นครนายก","นครปฐม","นครพนม","นครราชสีมา","นครศรีธรรมราช",
    "นครสวรรค์","นนทบุรี","นราธิวาส","น่าน","บึงกาฬ","บุรีรัมย์","ปทุมธานี","ประจวบคีรีขันธ์","ปราจีนบุรี","ปัตตานี","พระนครศรีอยุธยา",
    "พังงา","พัทลุง","พิจิตร","พิษณุโลก","เพชรบุรี","เพชรบูรณ์","แพร่","พะเยา","ภูเก็ต","มหาสารคาม","มุกดาหาร","แม่ฮ่องสอน",
    "ยโสธร","ยะลา","ร้อยเอ็ด","ระนอง","ระยอง","ราชบุรี","ลพบุรี","ลำปาง","ลำพูน","เลย","ศรีสะเกษ","สกลนคร","สงขลา","สตูล",
    "สมุทรปราการ","สมุทรสงคราม","สมุทรสาคร","สระแก้ว","สระบุรี","สิงห์บุรี","สุโขทัย","สุพรรณบุรี","สุราษฎร์ธานี","สุรินทร์",
    "หนองคาย","หนองบัวลำภู","อ่างทอง","อุดรธานี","อุทัยธานี","อุตรดิตถ์","อุบลราชธานี","อำนาจเจริญ",
]


def _read_jsonl(path: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    p = Path(path)
    if not p.exists():
        return out
    with p.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    out.append(obj)
            except Exception:
                continue
    return out


def _find_int(text: str, patterns: list[str]) -> int | None:
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if not m:
            continue
        raw = re.sub(r"[^\d]", "", m.group(1))
        if raw:
            try:
                return int(raw)
            except Exception:
                continue
    return None


def _detect_form_type(text: str, name: str) -> str | None:
    full = f"{name}\n{text}"
    is_bch = bool(re.search(r"\(บช\)|\bBCH\b|\bBCh\b|party-list|บัญชีรายชื่อ", full, re.IGNORECASE))
    code = None
    if re.search(r"5[/_ ]?16|๕[/_ ]?๑๖", full):
        code = "5/16"
    elif re.search(r"5[/_ ]?17|๕[/_ ]?๑๗", full):
        code = "5/17"
    elif re.search(r"5[/_ ]?18|๕[/_ ]?๑๘", full):
        code = "5/18"
    if not code:
        return None
    return f"ส.ส. {code} (บช)" if is_bch else f"ส.ส. {code}"


def _detect_province(text: str, name: str, folder_path: list[str] | None) -> str | None:
    full = f"{text}\n{name}\n{' '.join(folder_path or [])}"
    m = re.search(r"(?:Province|จังหวัด)\s*[:\-]?\s*([A-Za-zก-๙]+)", full, re.IGNORECASE)
    if m:
        cand = m.group(1).strip()
        if cand:
            # Direct match to Thai province list if possible.
            for p in PROVINCES_TH:
                if p in full:
                    return p
            return cand
    for p in PROVINCES_TH:
        if p in full:
            return p
    return None


def _extract_votes_map(text: str) -> dict[str, int]:
    votes: dict[str, int] = {}
    patterns = [
        r"(?:No\.|Number|Party(?:\s*No\.)?)\s*([0-9]{1,3})[^0-9]{0,40}([0-9][0-9,]{0,6})\s*votes",
        r"([0-9]{1,3})\s*[:\-]\s*([0-9][0-9,]{0,6})\s*votes",
    ]
    for pat in patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            key = m.group(1).strip()
            val = re.sub(r"[^\d]", "", m.group(2))
            if key and val:
                try:
                    votes[key] = int(val)
                except Exception:
                    continue
    return votes


def _extract_form(row: dict[str, Any]) -> dict[str, Any]:
    name = str(row.get("name", "") or "")
    text = str(row.get("summary", "") or "")
    drive_id = str(row.get("drive_id", "") or "")
    drive_url = str(row.get("drive_url", "") or "")
    folder_path = row.get("folder_path", [])
    if not isinstance(folder_path, list):
        folder_path = []

    form_type = _detect_form_type(text, name) or "unknown"
    form_category = "party_list" if "(บช)" in form_type else "constituency"
    province = _detect_province(text, name, folder_path)

    constituency_number = _find_int(
        text,
        [
            r"(?:Constituency|Electoral District|เขตเลือกตั้ง)\s*(?:No\.)?\s*[:\-]?\s*([0-9][0-9,]{0,3})",
        ],
    )
    polling_unit = _find_int(
        text,
        [
            r"(?:Polling Unit|Unit|หน่วยเลือกตั้ง)\s*(?:No\.)?\s*[:\-]?\s*([0-9][0-9,]{0,6})",
        ],
    )
    total_ballots = _find_int(
        text,
        [
            r"(?:Total Ballots|Ballots Received|จำนวนบัตรเลือกตั้งทั้งหมด)\s*[:\-]?\s*([0-9][0-9,]{0,8})",
        ],
    )
    valid_votes = _find_int(
        text,
        [
            r"(?:Valid Ballots|Good Ballots|บัตรดี)\s*[:\-]?\s*([0-9][0-9,]{0,8})",
        ],
    )
    invalid_votes = _find_int(
        text,
        [
            r"(?:Invalid Ballots|Spoiled Ballots|บัตรเสีย)\s*[:\-]?\s*([0-9][0-9,]{0,8})",
        ],
    )
    blank_votes = _find_int(
        text,
        [
            r"(?:Blank Ballots|No party-list selection|ไม่ประสงค์ลงคะแนน)\s*[:\-]?\s*([0-9][0-9,]{0,8})",
        ],
    )
    votes = _extract_votes_map(text)
    computed_sum_votes = sum(votes.values()) if votes else 0
    sum_matches_valid = None if valid_votes is None or not votes else (computed_sum_votes == valid_votes)
    totals_consistent = None
    if total_ballots is not None and valid_votes is not None and invalid_votes is not None and blank_votes is not None:
        totals_consistent = (valid_votes + invalid_votes + blank_votes == total_ballots)

    missing: list[str] = []
    for field, val in [
        ("form_type", form_type if form_type != "unknown" else None),
        ("province", province),
        ("constituency_number", constituency_number),
        ("polling_unit", polling_unit),
        ("total_ballots", total_ballots),
        ("valid_votes", valid_votes),
    ]:
        if val is None:
            missing.append(field)

    conf = 0.0
    if form_type != "unknown":
        conf += 0.35
    if province or constituency_number is not None:
        conf += 0.20
    if total_ballots is not None or valid_votes is not None:
        conf += 0.20
    if votes:
        conf += 0.20
    if (sum_matches_valid is True) or (totals_consistent is True):
        conf += 0.05
    conf = max(0.0, min(1.0, conf))

    return {
        "document": {
            "source_name": name or f"{drive_id}.pdf",
            "page_count": None,
            "drive_id": drive_id,
            "drive_url": drive_url,
            "folder_path": folder_path,
        },
        "forms": [
            {
                "form_id": "form_1",
                "form_type": form_type,
                "form_category": form_category,
                "pages": [1],
                "page_range": "1",
                "continuation_pages": [],
                "province": province,
                "constituency_number": constituency_number,
                "district": None,
                "polling_unit": polling_unit,
                "total_ballots": total_ballots,
                "valid_votes": valid_votes,
                "invalid_votes": invalid_votes,
                "blank_votes": blank_votes,
                "votes": votes,
                "computed_sum_votes": computed_sum_votes,
                "sum_matches_valid": sum_matches_valid,
                "totals_consistent": totals_consistent,
                "confidence": round(conf, 2),
                "missing_fields": missing,
                "notes": "Derived from Gemini summary text (not full-page OCR).",
                "source_evidence": {
                    "header_snippet": text[:220],
                    "totals_snippet": text[:420],
                    "votes_snippet": text[:620],
                },
            }
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert summary-only dataset to structured form JSON")
    parser.add_argument("--input", default="drive_pdf_summary_only_v3.jsonl")
    parser.add_argument("--output-jsonl", default="drive_structured_from_summary.jsonl")
    parser.add_argument("--output-json", default="drive_structured_from_summary.json")
    args = parser.parse_args()

    rows = _read_jsonl(args.input)
    converted = [_extract_form(r) for r in rows]

    with Path(args.output_jsonl).open("w", encoding="utf-8") as f:
        for obj in converted:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")

    Path(args.output_json).write_text(
        json.dumps({"count": len(converted), "items": converted}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # small summary
    form_detected = sum(1 for x in converted if x["forms"][0]["form_type"] != "unknown")
    with_votes = sum(1 for x in converted if x["forms"][0]["votes"])
    with_province = sum(1 for x in converted if x["forms"][0]["province"])
    print(f"converted={len(converted)} form_detected={form_detected} with_votes={with_votes} with_province={with_province}")
    print(f"jsonl={args.output_jsonl}")
    print(f"json={args.output_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

