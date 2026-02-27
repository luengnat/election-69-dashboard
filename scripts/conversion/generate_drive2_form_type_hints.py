#!/usr/bin/env python3
"""Generate form-type hints from Drive mapping using name, folder path, and summaries."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from ect_api import ect_data

THAI_TO_ARABIC = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")
ALLOWED_FORM_TYPES = {
    "ส.ส. 5/16",
    "ส.ส. 5/16 (บช)",
    "ส.ส. 5/17",
    "ส.ส. 5/17 (บช)",
    "ส.ส. 5/18",
    "ส.ส. 5/18 (บช)",
}
MANUAL_FORM_TYPE_BY_ID = {
    "1m4_T-gwKA8cOHB8Dn4SQrTt58yEvIjjf": "ส.ส. 5/17",
    "1Jj0xNvZDyDaITCzuFru-qXDv2_b63CRL": "ส.ส. 5/17",
    "1t0qNTFDOeOrzcHOQlJePV_fF0WfdUEtb": "ส.ส. 5/17",
    "1PbFBVAHQzHhqVyQTTyUMUcgIuU2dqnDE": "ส.ส. 5/17",
    "1kWXub_Grymd5hXpv2gQUDMN_w6nDOh3I": "ส.ส. 5/17",
    "1d38UDsY78IKJqe0IKKy1SdXx2RsAXfbZ": "ส.ส. 5/17",
}
MANUAL_LOCATION_OVERRIDE_BY_ID = {
    # User-provided corrections from browser inspection.
    "13MsOk_IXzlZMNcXcV7LsCtkctiSW5Nmt": {"location_kind": "unit_number", "location_number": 1},
    "1D_eWiEflgcY6-JSra1XBF8VaiZGNp93d": {"location_kind": "unit_number", "location_number": 1},
    "1NgNuuFvqX53rzWvyfvvXEhWJcL45sIjB": {"location_kind": "committee_number", "location_number": 6},
    "1Xvzsz1nnw7BUxW2x2_wvxrRa5YWnRhuj": {"district_number": 3, "location_kind": "committee_number", "location_number": 6},
    "1rqKWMdoKru1ez9Eo0XY67iBVu9NE3vv2": {
        "province": "สงขลา",
        "district_number": 2,
        "location_kind": "unit_number",
        "location_number": 92,
    },
    "1ULY8MA93hnXMfSHnxMF-l1X0FPDiD85X": {
        "province": "ราชบุรี",
        "district_number": 4,
        "location_kind": "unit_number",
        "location_number": 1,
    },
    "1iKO-A8WmBisDLNT-LwzrTBZ3FV7VMY5_": {
        "district_number": 4,
        "location_kind": "unit_number",
        "location_number": 4,
    },
    "1G9DrNUZUGCTz2ebDS0o3NO1lUYRjOD2c": {"location_kind": "unit_number", "location_number": 1},
    "1F9qY8b-hYXrNj54-f2SUNZ0WP2cv2om9": {"location_kind": "unit_number", "location_number": 92},
    "1J4qAAa4wpk2dXTptrnbhStBxPzYcCrea": {"location_kind": "committee_number", "location_number": 4},
    "1avl2eV35ckLXkaDt8tybuOH3JZgFXpJe": {"location_kind": "unit_number", "location_number": 21},
    "1cCndqaX3-HR3WMYRetJ06PxQMNV7VDdZ": {"location_kind": "unit_number", "location_number": 1},
}


def _load_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def _load_summary_by_id(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
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
        did = str(obj.get("drive_id", "")).strip()
        if not did:
            continue
        text = str(obj.get("summary", "") or obj.get("raw_text", "")).strip()
        if text:
            out[did] = text
    return out


def _normalize(text: str) -> str:
    s = (text or "").translate(THAI_TO_ARABIC).lower()
    s = s.replace("ทับ", "/")
    s = s.replace("_", "/").replace("-", "/")
    s = s.replace(" ", "")
    return s


def _detect_code(*parts: str) -> str | None:
    n = _normalize("\n".join([p for p in parts if p]))
    if "5/16" in n:
        return "5/16"
    if "5/17" in n:
        return "5/17"
    if "5/18" in n:
        return "5/18"
    return None


def _detect_category(*parts: str) -> str | None:
    raw = "\n".join([p for p in parts if p])
    n = _normalize(raw)
    if re.search(r"\(บช\)|\bbch\b|partylist|บัญชีรายชื่อ|บช", raw, re.IGNORECASE):
        return "party_list"
    if "บัญชีรายชื่อ" in raw:
        return "party_list"
    if "แบ่งเขต" in raw or "constituency" in n:
        return "constituency"
    return None


def _infer_code_from_folder_context(*parts: str) -> str | None:
    raw = "\n".join([p for p in parts if p])
    n = _normalize(raw)
    # Contextual hints when explicit code is absent.
    if "ล่วงหน้านอกเขต" in raw or "นอกราชอาณาจักร" in raw:
        return "5/17"
    if "ล่วงหน้าในเขต" in raw:
        return "5/16"
    if any(k in raw for k in ["หน่วย", "เทศบาล", "อำเภอ"]):
        return "5/18"
    # Normalized English-like fallback
    if "advanceout" in n or "outsidekingdom" in n:
        return "5/17"
    return None


def _detect_district_number_from_name(name: str) -> int | None:
    raw = (name or "").translate(THAI_TO_ARABIC)
    # Examples:
    # - "เทศบาลเมืองเนินพระ - 002 - แบ่งเขต.pdf"
    # - "xxx-12-บัญชีรายชื่อ.pdf"
    patterns = [
        r"\-\s*0*([0-9]{1,3})\s*\-",
        r"[_\s\-]0*([0-9]{1,3})[_\s\-]",
    ]
    for pat in patterns:
        m = re.search(pat, raw)
        if not m:
            continue
        try:
            val = int(m.group(1))
        except Exception:
            continue
        if val > 0:
            return val
    return None


def _detect_unit_number(name: str, folder_text: str, summary_text: str) -> int | None:
    """Best-effort polling unit extraction from name/folder/summary text."""
    parts = [name or "", folder_text or "", summary_text or ""]
    for raw in parts:
        if not raw:
            continue
        txt = raw.translate(THAI_TO_ARABIC)
        patterns = [
            r"หน่วยเลือกตั้งที่\s*\(?\s*([0-9]{1,4})\s*\)?",
            r"หน่วยที่\s*\(?\s*([0-9]{1,4})\s*\)?",
            r"หน่วย\s*\(?\s*([0-9]{1,4})\s*\)?",
            r"unit\s*(?:no\.?|number)?\s*\(?\s*([0-9]{1,4})\s*\)?",
            r"polling\s*unit\s*(?:no\.?|number)?\s*\(?\s*([0-9]{1,4})\s*\)?",
            r"polling\s*station\s*(?:no\.?|number)?\s*\(?\s*([0-9]{1,4})\s*\)?",
            r"polling\s*station\s*\(?\s*([0-9]{1,4})\s*\)?",
        ]
        for pat in patterns:
            m = re.search(pat, txt, flags=re.IGNORECASE)
            if not m:
                continue
            try:
                val = int(m.group(1))
            except Exception:
                continue
            if val > 0:
                return val
    return None


def _detect_committee_number(name: str, folder_text: str, summary_text: str) -> int | None:
    """Best-effort committee set extraction for form 5/17."""
    parts = [name or "", folder_text or "", summary_text or ""]
    for raw in parts:
        if not raw:
            continue
        txt = raw.translate(THAI_TO_ARABIC)
        patterns = [
            r"ชุดที่\s*\(?\s*([0-9]{1,4})\s*\)?",
            r"ชุด\s*\(?\s*([0-9]{1,4})\s*\)?",
            r"set\s*(?:no\.?|number)?\s*\(?\s*([0-9]{1,4})\s*\)?",
            r"committee\s*set\s*\(?\s*([0-9]{1,4})\s*\)?",
        ]
        for pat in patterns:
            m = re.search(pat, txt, flags=re.IGNORECASE)
            if not m:
                continue
            try:
                val = int(m.group(1))
            except Exception:
                continue
            if val > 0:
                return val
    return None


def _to_form_type(code: str | None, category: str | None) -> str | None:
    if not code:
        return None
    if category == "party_list":
        out = f"ส.ส. {code} (บช)"
        return out if out in ALLOWED_FORM_TYPES else None
    if category == "constituency":
        out = f"ส.ส. {code}"
        return out if out in ALLOWED_FORM_TYPES else None
    out = f"ส.ส. {code}"
    return out if out in ALLOWED_FORM_TYPES else None


def _code_from_form_type(form_type: str | None) -> str | None:
    if not form_type:
        return None
    m = re.search(r"5/1[678]", form_type)
    return m.group(0) if m else None


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate drive2 form type hints")
    parser.add_argument("--mapping-json", default="drive2_mapping.json")
    parser.add_argument("--summary-jsonl", default="drive2_pdf_summary.jsonl")
    parser.add_argument("--out-json", default="drive2_form_type_hints.json")
    parser.add_argument("--out-jsonl", default="drive2_form_type_hints.jsonl")
    parser.add_argument(
        "--exclude-referendum",
        action="store_true",
        default=True,
        help="Exclude files that look like referendum content (ประชามติ) (default: true)",
    )
    parser.add_argument(
        "--include-referendum",
        dest="exclude_referendum",
        action="store_false",
        help="Include referendum-like files",
    )
    args = parser.parse_args()

    mapping = _load_json(Path(args.mapping_json), {"files": {}})
    files = mapping.get("files", {}) if isinstance(mapping, dict) else {}
    if not isinstance(files, dict):
        print("ERROR: invalid mapping")
        return 1
    summaries = _load_summary_by_id(Path(args.summary_jsonl))
    ect_data.load()

    rows: list[dict[str, Any]] = []
    for did, entry in files.items():
        if not isinstance(entry, dict):
            continue
        drive_id = str(entry.get("drive_id") or did).strip()
        if not drive_id:
            continue
        name = str(entry.get("name", "")).strip()
        if args.exclude_referendum and ("ประชามติ" in name):
            continue
        folder_path = entry.get("folder_path", [])
        folder_text = " / ".join(str(x) for x in folder_path) if isinstance(folder_path, list) else str(folder_path or "")
        if args.exclude_referendum and ("ประชามติ" in folder_text):
            continue
        summary_text = summaries.get(drive_id, "")
        if args.exclude_referendum and ("ประชามติ" in summary_text):
            continue

        code = _detect_code(summary_text, name, folder_text)
        category = _detect_category(summary_text, name, folder_text)
        if not code:
            code = _infer_code_from_folder_context(name, folder_text)
        form_type = _to_form_type(code, category)

        # ECT grounding
        province_raw = str(entry.get("province", ""))
        cons_no = int(entry.get("constituency_number", 0) or 0)
        prov_valid, prov_canonical = ect_data.validate_province_name(province_raw)
        prov_name = prov_canonical if (prov_valid and prov_canonical) else province_raw
        prov_abbr = ect_data.get_province_abbr(prov_name) if prov_name else None
        cons_id = f"{prov_abbr}_{cons_no}" if (prov_abbr and cons_no > 0) else None
        cons_exists = bool(cons_id and ect_data.get_constituency(cons_id))

        if drive_id in MANUAL_FORM_TYPE_BY_ID:
            form_type = MANUAL_FORM_TYPE_BY_ID[drive_id]
            source = "manual_override"
        elif form_type and summary_text:
            source = "summary+name+folder"
        elif form_type and folder_text:
            source = "name+folder"
        elif form_type:
            source = "name"
        else:
            source = "unknown"

        unit_number = _detect_unit_number(name, folder_text, summary_text)
        committee_number = _detect_committee_number(name, folder_text, summary_text)

        # 5/17 forms are committee-set based (ชุดที่...), not polling-unit based.
        if form_type in {"ส.ส. 5/17", "ส.ส. 5/17 (บช)"}:
            unit_number = None

        rows.append(
            {
                "drive_id": drive_id,
                "name": name,
                "province": province_raw,
                "constituency_number": cons_no,
                "district_number": cons_no,
                "district_number_hint": _detect_district_number_from_name(name),
                "unit_number": unit_number,
                "committee_number": committee_number,
                "location_number": committee_number if form_type in {"ส.ส. 5/17", "ส.ส. 5/17 (บช)"} else unit_number,
                "location_kind": "committee_number" if form_type in {"ส.ส. 5/17", "ส.ส. 5/17 (บช)"} else "unit_number",
                "form_category_hint": category,
                "category_hint": category,
                "form_type_hint": form_type,
                "hint_source": source,
                "folder_path": folder_path if isinstance(folder_path, list) else [],
                "ect_province_valid": bool(prov_valid),
                "ect_province_canonical": prov_canonical,
                "ect_province_abbr": prov_abbr,
                "ect_constituency_id": cons_id,
                "ect_constituency_exists": cons_exists,
            }
        )

    # Second pass: if code is missing but category is known, infer code from
    # dominant known code within same province+constituency group.
    group_code_counts: dict[tuple[str, int], dict[str, int]] = {}
    for r in rows:
        prov = str(r.get("province", "")).strip()
        cons = int(r.get("constituency_number", 0) or 0)
        if not prov or cons <= 0:
            continue
        code = _code_from_form_type(r.get("form_type_hint"))
        if not code:
            continue
        key = (prov, cons)
        cc = group_code_counts.setdefault(key, {})
        cc[code] = cc.get(code, 0) + 1

    for r in rows:
        if r.get("form_type_hint"):
            continue
        category = r.get("category_hint")
        if category not in {"party_list", "constituency"}:
            continue
        prov = str(r.get("province", "")).strip()
        cons = int(r.get("constituency_number", 0) or 0)
        key = (prov, cons)
        cc = group_code_counts.get(key, {})
        if not cc:
            continue
        code = max(cc.items(), key=lambda kv: kv[1])[0]
        inferred = _to_form_type(code, str(category))
        if inferred:
            r["form_type_hint"] = inferred
            r["hint_source"] = "group_inference_from_name+folder"

    out_json = Path(args.out_json)
    out_jsonl = Path(args.out_jsonl)

    # Enforce whitelist: only 6 canonical form types, else unknown.
    for r in rows:
        ft = r.get("form_type_hint")
        if ft and ft not in ALLOWED_FORM_TYPES:
            r["form_type_hint"] = None
            r["hint_source"] = "unknown"

    # Apply manual location overrides last.
    for r in rows:
        did = str(r.get("drive_id", "")).strip()
        ov = MANUAL_LOCATION_OVERRIDE_BY_ID.get(did)
        if not ov:
            continue
        ov_prov = str(ov.get("province", "")).strip()
        if ov_prov:
            r["province"] = ov_prov
        ov_dist = ov.get("district_number")
        if ov_dist is not None:
            d = int(ov_dist)
            r["district_number"] = d
            r["constituency_number"] = d
        lk = str(ov.get("location_kind", "")).strip()
        ln = ov.get("location_number")
        if lk == "unit_number":
            r["unit_number"] = int(ln) if ln is not None else None
            r["committee_number"] = r.get("committee_number")
        elif lk == "committee_number":
            r["committee_number"] = int(ln) if ln is not None else None
        r["location_kind"] = lk or r.get("location_kind")
        r["location_number"] = int(ln) if ln is not None else r.get("location_number")

    out_json.write_text(json.dumps({"count": len(rows), "items": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    with out_jsonl.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    known = sum(1 for r in rows if r["form_type_hint"])
    by_source: dict[str, int] = {}
    for r in rows:
        src = str(r["hint_source"])
        by_source[src] = by_source.get(src, 0) + 1
    print(f"rows={len(rows)} known={known} unknown={len(rows)-known}")
    print("sources=" + json.dumps(by_source, ensure_ascii=False))
    print(f"out_json={out_json}")
    print(f"out_jsonl={out_jsonl}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
