#!/usr/bin/env python3
"""Extract scores from Drive PDFs with Gemini and validate against ECT references."""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Optional

import requests

from ect_api import ect_data

ALLOWED_FORM_TYPES = {
    "ส.ส. 5/16",
    "ส.ส. 5/16 (บช)",
    "ส.ส. 5/17",
    "ส.ส. 5/17 (บช)",
    "ส.ส. 5/18",
    "ส.ส. 5/18 (บช)",
}


def _load_json(path: str, fallback: Any) -> Any:
    p = Path(path)
    if not p.exists():
        return fallback
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def _save_json(path: str, obj: Any) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


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


def _download_drive_file_bytes(drive_id: str, timeout: int = 60) -> Optional[bytes]:
    if not drive_id:
        return None
    url = f"https://drive.usercontent.google.com/download?id={drive_id}&export=download&authuser=0"
    try:
        r = requests.get(url, timeout=timeout, allow_redirects=True)
        if r.status_code != 200 or not r.content:
            return None
        return r.content
    except Exception:
        return None


def _read_local_file_bytes(local_path: str) -> Optional[bytes]:
    if not local_path:
        return None
    p = Path(local_path).expanduser()
    if not p.exists() or not p.is_file():
        return None
    try:
        return p.read_bytes()
    except Exception:
        return None


def _extract_json_from_text(text: str) -> Optional[dict[str, Any]]:
    if not text:
        return None
    raw = text.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else None
    except Exception:
        pass
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        try:
            obj = json.loads(raw[start : end + 1])
            return obj if isinstance(obj, dict) else None
        except Exception:
            return None
    return None


def _gemini_generate_json(
    *,
    api_key: str,
    model: str,
    prompt: str,
    pdf_bytes: bytes,
    max_retries: int = 3,
    retry_sleep: float = 2.0,
) -> tuple[bool, str, Optional[dict[str, Any]]]:
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    payload = {
        "generationConfig": {
            "temperature": 0.0,
            "responseMimeType": "application/json",
        },
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": prompt},
                    {
                        "inline_data": {
                            "mime_type": "application/pdf",
                            "data": base64.b64encode(pdf_bytes).decode("ascii"),
                        }
                    },
                ],
            }
        ],
    }
    headers = {"Content-Type": "application/json"}
    last_text = ""
    for attempt in range(1, max_retries + 1):
        try:
            r = requests.post(endpoint, headers=headers, data=json.dumps(payload), timeout=180)
            if r.status_code != 200:
                last_text = r.text
                time.sleep(retry_sleep * attempt)
                continue
            data = r.json()
            candidates = data.get("candidates") or []
            if not candidates:
                last_text = json.dumps(data, ensure_ascii=False)
                time.sleep(retry_sleep * attempt)
                continue
            parts = candidates[0].get("content", {}).get("parts", [])
            text = ""
            for p in parts:
                if isinstance(p, dict) and p.get("text"):
                    text += str(p["text"])
            last_text = text
            obj = _extract_json_from_text(text)
            return (obj is not None), text, obj
        except Exception as exc:
            last_text = f"request_error: {exc}"
            time.sleep(retry_sleep * attempt)
    return False, last_text, None


def _build_prompt(
    prompt_template: str,
    source_name: str,
    hint: dict[str, Any],
) -> str:
    text = Path(prompt_template).read_text(encoding="utf-8")
    text = text.replace("<file name>", source_name or "<file name>")
    text = text.replace("<int|null>", "<int|null>")
    text += "\n\n## File-specific priors\n"
    text += f"- Expected form type: {hint.get('form_type_hint') or 'unknown'}\n"
    text += f"- Province: {hint.get('province') or hint.get('ect_province_canonical') or 'unknown'}\n"
    text += f"- District/Constituency number: {hint.get('district_number') or hint.get('constituency_number') or 'unknown'}\n"
    if hint.get("location_kind") == "committee_number":
        text += f"- Committee set number: {hint.get('location_number') or hint.get('committee_number') or 'unknown'}\n"
    else:
        text += f"- Polling unit number: {hint.get('location_number') or hint.get('unit_number') or 'unknown'}\n"
    text += "- If these priors conflict with the PDF header/table content, trust the PDF."
    return text


def _to_int_safe(x: Any) -> Optional[int]:
    try:
        if x is None:
            return None
        if isinstance(x, bool):
            return None
        return int(str(x).strip())
    except Exception:
        return None


def _normalize_form_type(form_type: Any) -> str:
    return str(form_type or "").strip()


def _validate_form_with_ect(form_obj: dict[str, Any]) -> dict[str, Any]:
    form_type = _normalize_form_type(form_obj.get("form_type"))
    form_category = str(form_obj.get("form_category", "")).strip()
    province_raw = str(form_obj.get("province", "")).strip()
    cons_no = _to_int_safe(form_obj.get("constituency_number")) or 0
    votes = form_obj.get("votes", {})
    if not isinstance(votes, dict):
        votes = {}

    p_valid, p_canonical = ect_data.validate_province_name(province_raw) if province_raw else (False, None)
    province = p_canonical if (p_valid and p_canonical) else province_raw
    prov_abbr = ect_data.get_province_abbr(province) if province else None
    cons_id = f"{prov_abbr}_{cons_no}" if prov_abbr and cons_no > 0 else None
    cons_exists = bool(cons_id and ect_data.get_constituency(cons_id))

    form_type_allowed = form_type in ALLOWED_FORM_TYPES
    expected_category = "party_list" if "(บช)" in form_type else "constituency"
    form_category_matches = bool(form_category == expected_category) if form_type_allowed else None

    out: dict[str, Any] = {
        "form_type_allowed": form_type_allowed,
        "form_category_matches_type": form_category_matches,
        "ect_province_valid": bool(p_valid),
        "ect_province_canonical": p_canonical,
        "ect_province_abbr": prov_abbr,
        "ect_constituency_id": cons_id,
        "ect_constituency_exists": cons_exists,
        "matched_vote_rows": 0,
        "unmatched_vote_rows": 0,
        "unmatched_vote_keys": [],
    }

    if expected_category == "constituency":
        candidates = ect_data.get_candidates_by_thai_province(province, cons_no) if province and cons_no > 0 else []
        valid_positions = {c.position for c in candidates}
        unmatched: list[str] = []
        matched = 0
        for k in votes.keys():
            pos = _to_int_safe(k)
            if pos is not None and pos in valid_positions:
                matched += 1
            else:
                unmatched.append(str(k))
        out["expected_candidate_positions"] = sorted(valid_positions)
        out["matched_vote_rows"] = matched
        out["unmatched_vote_rows"] = len(unmatched)
        out["unmatched_vote_keys"] = unmatched
    else:
        unmatched = []
        matched = 0
        for k in votes.keys():
            party_no = _to_int_safe(k)
            party_obj = ect_data.get_party_by_number(party_no) if party_no is not None else None
            if party_obj:
                matched += 1
            else:
                unmatched.append(str(k))
        out["matched_vote_rows"] = matched
        out["unmatched_vote_rows"] = len(unmatched)
        out["unmatched_vote_keys"] = unmatched

    return out


def _validate_extraction_with_ect(extracted: dict[str, Any]) -> dict[str, Any]:
    forms = extracted.get("forms", [])
    if not isinstance(forms, list):
        forms = []
    form_checks = []
    for f in forms:
        if isinstance(f, dict):
            form_checks.append(_validate_form_with_ect(f))

    total_unmatched = sum(int(fc.get("unmatched_vote_rows", 0) or 0) for fc in form_checks)
    disallowed_types = sum(1 for fc in form_checks if not fc.get("form_type_allowed"))
    bad_category = sum(1 for fc in form_checks if fc.get("form_category_matches_type") is False)
    return {
        "form_checks": form_checks,
        "summary": {
            "form_count": len(form_checks),
            "total_unmatched_vote_rows": total_unmatched,
            "disallowed_form_types": disallowed_types,
            "category_mismatch_forms": bad_category,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract Drive scores with ECT validation")
    parser.add_argument("--hints-jsonl", default="drive2_form_type_hints.jsonl")
    parser.add_argument("--mapping-json", default="drive2_mapping.json")
    parser.add_argument("--prompt-template", default="prompts/gemini_ballot_json_extraction.md")
    parser.add_argument("--out-dir", default="drive2_score_extractions")
    parser.add_argument("--state-file", default="drive2_score_extractions_state.json")
    parser.add_argument("--model", default="gemini-2.0-flash")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--resume", action="store_true", default=True)
    parser.add_argument("--no-resume", dest="resume", action="store_false")
    parser.add_argument("--validate-only", action="store_true", default=False)
    parser.add_argument("--sleep", type=float, default=0.6)
    args = parser.parse_args()

    ect_data.load()

    hints = _read_jsonl(args.hints_jsonl)
    mapping = _load_json(args.mapping_json, {"files": {}})
    files_map = mapping.get("files", {}) if isinstance(mapping, dict) else {}
    if not isinstance(files_map, dict):
        print("ERROR: invalid mapping json")
        return 1

    items = []
    for h in hints:
        did = str(h.get("drive_id", "")).strip()
        if not did:
            continue
        ft = str(h.get("form_type_hint", "") or "").strip()
        if not ft:
            continue
        entry = files_map.get(did, {})
        if not isinstance(entry, dict):
            entry = {}
        items.append({"drive_id": did, "hint": h, "entry": entry})

    items = sorted(items, key=lambda x: x["drive_id"])
    if args.limit and args.limit > 0:
        items = items[: args.limit]

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    state = _load_json(args.state_file, {"done_ids": [], "updated_at_epoch": 0})
    done_ids = set(state.get("done_ids", []) if isinstance(state, dict) else [])

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not args.validate_only and not api_key:
        print("ERROR: GEMINI_API_KEY is not set")
        return 1

    scanned = 0
    ok = 0
    failed = 0
    for idx, item in enumerate(items, start=1):
        did = item["drive_id"]
        hint = item["hint"]
        entry = item["entry"]
        name = str(entry.get("name", "")).strip() or str(hint.get("name", "")).strip() or f"{did}.pdf"

        if args.resume and did in done_ids:
            print(f"[{idx}/{len(items)}] skip(done): {did} {name}")
            continue
        scanned += 1

        raw_path = out_dir / f"{did}.raw.txt"
        json_path = out_dir / f"{did}.json"
        validated_path = out_dir / f"{did}.validated.json"

        parsed: Optional[dict[str, Any]] = None
        raw_text = ""
        if args.validate_only:
            if json_path.exists():
                parsed = _load_json(str(json_path), None)
            elif raw_path.exists():
                raw_text = raw_path.read_text(encoding="utf-8")
                parsed = _extract_json_from_text(raw_text)
            if not parsed:
                print(f"[{idx}/{len(items)}] fail(validate_only_missing_json): {did} {name}")
                failed += 1
                continue
        else:
            local_path = str(entry.get("local_path", "")).strip()
            pdf_bytes = _read_local_file_bytes(local_path) if local_path else None
            if pdf_bytes is None:
                pdf_bytes = _download_drive_file_bytes(did)
            if pdf_bytes is None:
                print(f"[{idx}/{len(items)}] fail(download): {did} {name}")
                failed += 1
                continue

            prompt = _build_prompt(args.prompt_template, name, hint)
            (out_dir / f"{did}.prompt.txt").write_text(prompt, encoding="utf-8")
            ok_parse, raw_text, parsed = _gemini_generate_json(
                api_key=api_key,
                model=args.model,
                prompt=prompt,
                pdf_bytes=pdf_bytes,
            )
            raw_path.write_text(raw_text or "", encoding="utf-8")
            if not ok_parse or not parsed:
                print(f"[{idx}/{len(items)}] fail(parse): {did} {name}")
                failed += 1
                continue
            _save_json(str(json_path), parsed)

        validation = _validate_extraction_with_ect(parsed)
        _save_json(
            str(validated_path),
            {
                "drive_id": did,
                "name": name,
                "form_type_hint": hint.get("form_type_hint"),
                "province": hint.get("province"),
                "district_number": hint.get("district_number"),
                "unit_number": hint.get("unit_number"),
                "committee_number": hint.get("committee_number"),
                "validation": validation,
            },
        )
        ok += 1
        done_ids.add(did)
        state = {"done_ids": sorted(done_ids), "updated_at_epoch": int(time.time())}
        _save_json(args.state_file, state)
        print(
            f"[{idx}/{len(items)}] ok: {did} {name} "
            f"unmatched={validation['summary']['total_unmatched_vote_rows']}"
        )
        time.sleep(max(0.0, args.sleep))

    print(f"Done. scanned={scanned} ok={ok} fail={failed} total_candidates={len(items)}")
    print(f"Out dir: {out_dir}")
    print(f"State: {args.state_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
