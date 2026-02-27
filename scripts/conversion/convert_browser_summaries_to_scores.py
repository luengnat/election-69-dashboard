#!/usr/bin/env python3
"""Convert browser Gemini summaries into structured score rows with ECT validation."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from ect_api import ect_data

ALLOWED_FORM_TYPES = {
    "ส.ส. 5/16",
    "ส.ส. 5/16 (บช)",
    "ส.ส. 5/17",
    "ส.ส. 5/17 (บช)",
    "ส.ส. 5/18",
    "ส.ส. 5/18 (บช)",
}
MANUAL_MULTI_FORM_BY_ID = {
    # User-confirmed bundled file with two forms in one source.
    "1d38UDsY78IKJqe0IKKy1SdXx2RsAXfbZ": ["ส.ส. 5/17", "ส.ส. 5/17 (บช)"],
    # User-confirmed bundled file with multiple forms.
    "1D_eWiEflgcY6-JSra1XBF8VaiZGNp93d": ["ส.ส. 5/18", "ส.ส. 5/18 (บช)"],
}

THAI_TO_ARABIC = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")


def _read_jsonl(path: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    p = Path(path)
    if not p.exists():
        return out
    for line in p.read_text(encoding="utf-8").splitlines():
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


def _to_int(x: Any) -> int | None:
    try:
        if x is None:
            return None
        s = str(x).strip().replace(",", "")
        if not s:
            return None
        return int(float(s))
    except Exception:
        return None


def _norm_text(s: str) -> str:
    return (s or "").translate(THAI_TO_ARABIC)


def _detect_form_type(row: dict[str, Any]) -> str | None:
    ft = str(row.get("form_type_hint", "")).strip()
    if ft in ALLOWED_FORM_TYPES:
        return ft
    txt = _norm_text("\n".join([str(row.get("name", "")), str(row.get("summary", "")), str(row.get("raw_text", ""))])).lower()
    code = None
    if "5/16" in txt:
        code = "5/16"
    elif "5/17" in txt:
        code = "5/17"
    elif "5/18" in txt:
        code = "5/18"
    if not code:
        return None
    is_bch = bool(re.search(r"\(บช\)|\bbch\b|บัญชีรายชื่อ|party\s*list", txt, re.IGNORECASE))
    cand = f"ส.ส. {code} (บช)" if is_bch else f"ส.ส. {code}"
    return cand if cand in ALLOWED_FORM_TYPES else None


def _extract_vote_rows(text: str, is_party_list: bool) -> list[dict[str, Any]]:
    t = _norm_text(text)
    rows: list[dict[str, Any]] = []
    seen: set[tuple[int, int]] = set()

    # Thai pattern: หมายเลข 46 ... ได้ 509 คะแนน
    for m in re.finditer(r"หมายเลข\s*([0-9]{1,3})\s*[:\-]?\s*([^\n]{0,120}?)\s*ได้\s*([0-9][0-9,]{0,8})\s*คะแนน", t):
        num = _to_int(m.group(1))
        score = _to_int(m.group(3))
        if num is None or score is None:
            continue
        key = (num, score)
        if key in seen:
            continue
        seen.add(key)
        name = m.group(2).strip(" :-\t")
        rows.append(
            {
                "number": num,
                "name": name or None,
                "score": score,
                "row_type": "party" if is_party_list else "candidate",
            }
        )

    # English-ish fallback: "2  ...  62"
    for line in t.splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^([0-9]{1,3})\s+(.{1,120}?)\s+([0-9][0-9,]{0,8})$", line)
        if not m:
            continue
        num = _to_int(m.group(1))
        score = _to_int(m.group(3))
        if num is None or score is None:
            continue
        key = (num, score)
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "number": num,
                "name": m.group(2).strip(),
                "score": score,
                "row_type": "party" if is_party_list else "candidate",
            }
        )

    return rows


def _extract_location_candidates(text: str, location_kind: str) -> list[int]:
    t = _norm_text(text)
    nums: set[int] = set()
    if location_kind == "committee_number":
        pats = [
            r"ชุดที่\s*\(?\s*([0-9]{1,4})\s*\)?",
            r"set\s*(?:no\.?|number)?\s*\(?\s*([0-9]{1,4})\s*\)?",
        ]
    else:
        pats = [
            r"หน่วยเลือกตั้งที่\s*\(?\s*([0-9]{1,4})\s*\)?",
            r"หน่วยที่\s*\(?\s*([0-9]{1,4})\s*\)?",
            r"หน่วย\s*\(?\s*([0-9]{1,4})\s*\)?",
            r"(?:polling\s*unit|unit)\s*(?:no\.?|number)?\s*\(?\s*([0-9]{1,4})\s*\)?",
            r"polling\s*station\s*(?:no\.?|number)?\s*\(?\s*([0-9]{1,4})\s*\)?",
            r"polling\s*station\s*\(?\s*([0-9]{1,4})\s*\)?",
        ]
    for pat in pats:
        for m in re.finditer(pat, t, flags=re.IGNORECASE):
            n = _to_int(m.group(1))
            if n is not None and n > 0:
                nums.add(n)
    # Table fallback for bundled unit summaries:
    # e.g. lines like "103 ศรีภูมิ 433 คน ..."
    if location_kind == "unit_number" and "หน่วยเลือกตั้ง" in t and not nums:
        for line in t.splitlines():
            line = line.strip()
            if not line:
                continue
            m = re.match(r"^([0-9]{1,4})\s+[^\d]{1,40}\s+[0-9]{1,6}\s*คน", line)
            if not m:
                continue
            n = _to_int(m.group(1))
            if n is not None and n > 0:
                nums.add(n)
    # English table fallback:
    # e.g. "1  1  เวียงพางคำ  364  234  ..."
    if location_kind == "unit_number" and ("polling station" in t.lower()) and not nums:
        for line in t.splitlines():
            line = line.strip()
            if not line:
                continue
            m = re.match(r"^([0-9]{1,4})\s+[0-9]{1,4}\s+\S+\s+[0-9]{2,6}\s+[0-9]{2,6}", line, flags=re.IGNORECASE)
            if not m:
                continue
            n = _to_int(m.group(1))
            if n is not None and n > 0:
                nums.add(n)
    return sorted(nums)


def _split_text_by_location(text: str, location_kind: str) -> dict[int, str]:
    """
    Split a bundled text into per-location chunks.
    Returns {location_number: chunk_text}.
    """
    t = _norm_text(text)
    if location_kind == "committee_number":
        pat = re.compile(r"(?:ชุดที่|ชุด|set\s*(?:no\.?|number)?|committee\s*set)\s*\(?\s*([0-9]{1,4})\s*\)?", re.IGNORECASE)
    else:
        pat = re.compile(
            r"(?:หน่วยเลือกตั้งที่|หน่วยที่|หน่วย)\s*\(?\s*([0-9]{1,4})\s*\)?|(?:polling\s*unit|unit)\s*(?:no\.?|number)?\s*\(?\s*([0-9]{1,4})\s*\)?|polling\s*station\s*(?:no\.?|number)?\s*\(?\s*([0-9]{1,4})\s*\)?|polling\s*station\s*\(?\s*([0-9]{1,4})\s*\)?",
            re.IGNORECASE,
        )

    marks: list[tuple[int, int]] = []  # (start_index, location_number)
    for m in pat.finditer(t):
        n = _to_int(m.group(1) or m.group(2) or m.group(3) or m.group(4))
        if n is not None and n > 0:
            marks.append((m.start(), n))
    if not marks:
        # Table fallback for bundled unit summaries.
        if location_kind == "unit_number" and "หน่วยเลือกตั้ง" in t:
            line_marks: list[tuple[int, int]] = []
            cursor = 0
            for line in t.splitlines(True):
                m = re.match(r"^\s*([0-9]{1,4})\s+[^\d]{1,40}\s+[0-9]{1,6}\s*คน", line.strip())
                if m:
                    n = _to_int(m.group(1))
                    if n is not None and n > 0:
                        line_marks.append((cursor, n))
                cursor += len(line)
            if not line_marks:
                # English table fallback:
                # e.g. "1  1  เวียงพางคำ  364  234 ..."
                if "polling station" in t.lower():
                    cursor = 0
                    for line in t.splitlines(True):
                        m = re.match(
                            r"^\s*([0-9]{1,4})\s+[0-9]{1,4}\s+\S+\s+[0-9]{2,6}\s+[0-9]{2,6}",
                            line.strip(),
                            flags=re.IGNORECASE,
                        )
                        if m:
                            n = _to_int(m.group(1))
                            if n is not None and n > 0:
                                line_marks.append((cursor, n))
                        cursor += len(line)
                if not line_marks:
                    return {}
            marks = sorted(line_marks, key=lambda x: x[0])
        else:
            return {}
    marks.sort(key=lambda x: x[0])

    out: dict[int, str] = {}
    for i, (start, n) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(t)
        chunk = t[start:end].strip()
        if not chunk:
            continue
        prev = out.get(n, "")
        out[n] = (prev + "\n" + chunk).strip() if prev else chunk
    return out


def _apply_ect_validation(
    *,
    province: str,
    district_number: int,
    election_type: str,
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in rows:
        number = _to_int(r.get("number"))
        name = str(r.get("name", "") or "").strip()
        item = dict(r)
        item["ect_match"] = False
        item["ect_name"] = None
        if number is None:
            out.append(item)
            continue
        if election_type == "party_list":
            party = ect_data.get_party_by_number(number)
            if party:
                item["ect_match"] = True
                item["ect_name"] = party.name
                if not name:
                    item["name"] = party.name
        else:
            cand = ect_data.get_candidate_by_thai_province(province, district_number, number)
            if cand:
                item["ect_match"] = True
                item["ect_name"] = cand.mp_app_name
                if not name:
                    item["name"] = cand.mp_app_name
        out.append(item)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert browser summaries to structured score rows")
    parser.add_argument("--input-jsonl", default="drive2_pdf_summary_browser_deep.jsonl")
    parser.add_argument("--hints-jsonl", default="drive2_form_type_hints.jsonl")
    parser.add_argument("--output-jsonl", default="drive2_scores_structured.jsonl")
    parser.add_argument("--output-json", default="drive2_scores_structured.json")
    parser.add_argument("--merge-continuations", action="store_true", default=True)
    parser.add_argument("--no-merge-continuations", dest="merge_continuations", action="store_false")
    args = parser.parse_args()

    ect_data.load()
    summary_rows = _read_jsonl(args.input_jsonl)
    hints_rows = _read_jsonl(args.hints_jsonl)
    hints_by_id = {str(r.get("drive_id", "")).strip(): r for r in hints_rows if str(r.get("drive_id", "")).strip()}

    raw_docs: list[dict[str, Any]] = []
    for row in summary_rows:
        did = str(row.get("drive_id", "")).strip()
        if not did:
            continue
        hint = hints_by_id.get(did, {})
        form_type = _detect_form_type(row) or str(hint.get("form_type_hint", "")).strip() or None
        if form_type not in ALLOWED_FORM_TYPES:
            continue
        election_type = "party_list" if "(บช)" in form_type else "constituency"

        province_raw = str(hint.get("province") or row.get("province_hint") or "").strip()
        ok_prov, canonical = ect_data.validate_province_name(province_raw) if province_raw else (False, None)
        province = canonical if (ok_prov and canonical) else province_raw
        district_number = _to_int(hint.get("district_number")) or _to_int(hint.get("constituency_number")) or _to_int(row.get("district_number_hint")) or 0
        if district_number <= 0:
            continue

        # Respect explicit hint override first.
        hint_location_kind = str(hint.get("location_kind", "") or "").strip()
        hint_location_number = _to_int(hint.get("location_number"))
        if hint_location_kind in {"unit_number", "committee_number"} and hint_location_number is not None:
            location_kind = hint_location_kind
            location_number = hint_location_number
        elif form_type in {"ส.ส. 5/17", "ส.ส. 5/17 (บช)"}:
            location_kind = "committee_number"
            location_number = _to_int(row.get("committee_number_hint")) or _to_int(hint.get("committee_number")) or None
        else:
            location_kind = "unit_number"
            location_number = _to_int(row.get("unit_number_hint")) or _to_int(hint.get("unit_number")) or None

        text = str(row.get("summary", "") or "") + "\n" + str(row.get("raw_text", "") or "")

        candidates = _extract_location_candidates(text, location_kind)
        if location_number is not None and location_number not in candidates:
            candidates = [location_number, *candidates]
        if not candidates:
            candidates = [location_number] if location_number is not None else []
        if not candidates:
            candidates = [None]

        chunks = _split_text_by_location(text, location_kind)

        bundled = len([c for c in candidates if c is not None]) > 1
        for c in candidates:
            per_text = chunks.get(c, text) if c is not None else text
            rows = _extract_vote_rows(per_text, is_party_list=(election_type == "party_list"))
            rows = _apply_ect_validation(
                province=province,
                district_number=district_number,
                election_type=election_type,
                rows=rows,
            )
            forced_forms = MANUAL_MULTI_FORM_BY_ID.get(did)
            if forced_forms:
                for forced_form in forced_forms:
                    forced_type = "party_list" if "(บช)" in forced_form else "constituency"
                    forced_rows = _apply_ect_validation(
                        province=province,
                        district_number=district_number,
                        election_type=forced_type,
                        rows=rows,
                    )
                    raw_docs.append(
                        {
                            "drive_id": did,
                            "name": row.get("name", ""),
                            "province": province,
                            "district_number": district_number,
                            "election_type": forced_type,
                            "form_type": forced_form,
                            "location_kind": location_kind,
                            "location_number": c,
                            "location_candidates": candidates,
                            "bundled_multi_form_source": True,
                            "rows": forced_rows,
                        }
                    )
            else:
                raw_docs.append(
                    {
                        "drive_id": did,
                        "name": row.get("name", ""),
                        "province": province,
                        "district_number": district_number,
                        "election_type": election_type,
                        "form_type": form_type,
                        "location_kind": location_kind,
                        "location_number": c,
                        "location_candidates": candidates,
                        "bundled_multi_form_source": bundled,
                        "rows": rows,
                    }
                )

    def _merge_doc_group(docs: list[dict[str, Any]]) -> dict[str, Any]:
        first = docs[0]
        merged_map: dict[int, dict[str, Any]] = {}
        all_candidates: set[int] = set()
        any_bundled = False
        for d in docs:
            for c in d.get("location_candidates", []) or []:
                n = _to_int(c)
                if n is not None:
                    all_candidates.add(n)
            any_bundled = any_bundled or bool(d.get("bundled_multi_form_source"))
            for rr in d.get("rows", []):
                n = _to_int(rr.get("number"))
                if n is None:
                    continue
                existing = merged_map.get(n)
                if existing is None:
                    merged_map[n] = dict(rr)
                    continue
                # Prefer matched rows and preserve non-empty name.
                existing["ect_match"] = bool(existing.get("ect_match")) or bool(rr.get("ect_match"))
                existing["ect_name"] = existing.get("ect_name") or rr.get("ect_name")
                if not existing.get("name") and rr.get("name"):
                    existing["name"] = rr.get("name")
                # If duplicate number appears, keep the larger score.
                old_score = _to_int(existing.get("score")) or 0
                new_score = _to_int(rr.get("score")) or 0
                if new_score > old_score:
                    existing["score"] = new_score

        merged_rows = sorted(merged_map.values(), key=lambda x: _to_int(x.get("number")) or 0)
        return {
            "drive_id": first.get("drive_id"),
            "drive_ids": [d.get("drive_id") for d in docs],
            "source_names": [d.get("name") for d in docs],
            "merged_from_count": len(docs),
            "province": first.get("province"),
            "district_number": first.get("district_number"),
            "election_type": first.get("election_type"),
            "form_type": first.get("form_type"),
            "location_kind": first.get("location_kind"),
            "location_number": first.get("location_number"),
            "location_candidates": sorted(all_candidates) if all_candidates else None,
            "bundled_multi_form_source": any_bundled,
            "rows": merged_rows,
        }

    if args.merge_continuations:
        groups: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
        for d in raw_docs:
            key = (
                d.get("province"),
                d.get("district_number"),
                d.get("form_type"),
                d.get("election_type"),
                d.get("location_kind"),
                d.get("location_number"),
            )
            groups.setdefault(key, []).append(d)
        out_rows = [_merge_doc_group(v) for v in groups.values()]
    else:
        out_rows = raw_docs

    out_jsonl = Path(args.output_jsonl)
    out_json = Path(args.output_json)
    out_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with out_jsonl.open("w", encoding="utf-8") as fh:
        for r in out_rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    out_json.write_text(json.dumps({"count": len(out_rows), "items": out_rows}, ensure_ascii=False, indent=2), encoding="utf-8")

    with_rows = sum(1 for r in out_rows if r.get("rows"))
    total_score_rows = sum(len(r.get("rows", [])) for r in out_rows)
    matched = sum(sum(1 for rr in r.get("rows", []) if rr.get("ect_match")) for r in out_rows)
    print(f"documents={len(out_rows)} with_rows={with_rows} total_rows={total_score_rows} ect_matched_rows={matched}")
    print(f"jsonl={out_jsonl}")
    print(f"json={out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
