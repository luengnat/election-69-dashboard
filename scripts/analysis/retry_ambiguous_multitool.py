#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from ballot_extraction import extract_ballot_data_with_ai, pdf_to_images_native
from opentyphoon_ocr import call_opentyphoon_ocr, download_drive_file

REPO = Path(__file__).resolve().parent
AMBIGUOUS_JSON = REPO / "killernay_mismatch_ambiguous.json"
BASE_ADJ_JSON = REPO / "killernay_mismatch_auto_adjudication.json"
OUT_JSON = REPO / "killernay_ambiguous_multitool_retry.json"
GEMINI_CACHE_CANDIDATES = [
    REPO / "official_manifest_part2A_raw.jsonl",
    REPO / "official_manifest_part2A_retry_raw.jsonl",
    REPO / "official_manifest_part2A_failed_retry_raw.jsonl",
    REPO / "tmp_expand60b_B_raw.jsonl",
    REPO / "tmp_expand60_A_raw.jsonl",
]


def _load_existing_results() -> dict[str, dict[str, Any]]:
    if not OUT_JSON.exists():
        return {}
    try:
        payload = json.loads(OUT_JSON.read_text(encoding="utf-8"))
    except Exception:
        return {}
    items = payload.get("items")
    if not isinstance(items, list):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for row in items:
        if not isinstance(row, dict):
            continue
        drive_id = str(row.get("drive_id", "")).strip()
        if drive_id:
            out[drive_id] = row
    return out


def _save_results(items: list[dict[str, Any]]) -> None:
    OUT_JSON.write_text(
        json.dumps({"rows": len(items), "items": items}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _to_int(v: Any) -> int | None:
    if v is None or v == "":
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return int(v)
    s = str(v).translate(str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789"))
    m = re.findall(r"\d+", s.replace(",", ""))
    if not m:
        return None
    try:
        return int("".join(m))
    except Exception:
        return None


def _parse_json_object(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    if not raw:
        return None
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else None
    except Exception:
        pass
    i = raw.find("{")
    j = raw.rfind("}")
    if i >= 0 and j > i:
        try:
            obj = json.loads(raw[i : j + 1])
            return obj if isinstance(obj, dict) else None
        except Exception:
            return None
    return None


def _extract_gemini_cached(drive_id: str) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for path in GEMINI_CACHE_CANDIDATES:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            if str(row.get("drive_id", "")).strip() != drive_id:
                continue
            obj = _parse_json_object(str(row.get("summary", ""))) or _parse_json_object(str(row.get("raw_text", "")))
            if not obj:
                continue
            valid = _to_int(obj.get("valid_votes"))
            district = _to_int(obj.get("district_number") or obj.get("constituency_number"))
            rows.append(
                {
                    "file": path.name,
                    "valid_votes": valid,
                    "district_number": district,
                    "election_type": str(obj.get("election_type", "")).strip() or None,
                    "raw": obj,
                }
            )
    return {"attempt_count": len(rows), "attempts": rows}


def _extract_from_ballotdata(obj) -> dict[str, Any]:
    if obj is None:
        return {"ok": False}
    votes = obj.vote_counts if obj.form_category == "constituency" else obj.party_votes
    vote_sum = sum(int(v) for v in (votes or {}).values())
    return {
        "ok": True,
        "form_category": obj.form_category,
        "form_type": obj.form_type.value if obj.form_type else None,
        "province": obj.province,
        "district_number": _to_int(obj.constituency_number),
        "valid_votes": _to_int(obj.valid_votes),
        "invalid_votes": _to_int(obj.invalid_votes),
        "blank_votes": _to_int(obj.blank_votes),
        "vote_sum": vote_sum,
    }


def _run_local_ocr(drive_id: str, drive_url: str) -> dict[str, Any]:
    out: dict[str, Any] = {"download_ok": False}
    with tempfile.TemporaryDirectory(prefix=f"amb_{drive_id}_") as td:
        tmp_dir = Path(td)
        try:
            file_bytes, filename = download_drive_file(drive_id)
            pdf_path = tmp_dir / (filename or f"{drive_id}.pdf")
            pdf_path.write_bytes(file_bytes)
            out["download_ok"] = True
        except Exception as exc:
            out["download_error"] = str(exc)
            return out

        pages_dir = tmp_dir / "pages"
        pages_dir.mkdir(parents=True, exist_ok=True)
        try:
            images = pdf_to_images_native(str(pdf_path), str(pages_dir))
        except Exception as exc:
            out["pdf_to_images_error"] = str(exc)
            return out
        if not images:
            out["pdf_to_images_error"] = "no_pages"
            return out

        # Use first page for totals/header (page 2+ often continuation only).
        p1 = images[0]
        out["page1_image"] = p1
        try:
            t_only = extract_ballot_data_with_ai(p1, backend_spec="tesseract")
            out["tesseract"] = _extract_from_ballotdata(t_only)
        except Exception as exc:
            out["tesseract"] = {"ok": False, "error": str(exc)}
        try:
            ens = extract_ballot_data_with_ai(p1, backend_spec="trocr,tesseract")
            out["trocr_tesseract"] = _extract_from_ballotdata(ens)
        except Exception as exc:
            out["trocr_tesseract"] = {"ok": False, "error": str(exc)}
    return out


def _run_typhoon(drive_id: str, drive_url: str) -> dict[str, Any]:
    api_key = os.environ.get("OPENTYPHOON_API_KEY", "").strip()
    if not api_key:
        return {"ok": False, "skipped": "missing_OPENTYPHOON_API_KEY"}
    try:
        file_bytes, filename = download_drive_file(drive_id)
        result = call_opentyphoon_ocr(
            file_bytes=file_bytes,
            filename=filename or f"{drive_id}.pdf",
            api_key=api_key,
            model="typhoon-ocr",
            task_type="default",
            max_tokens=16384,
            temperature=0.1,
            top_p=0.6,
            repetition_penalty=1.2,
            pages=[1],
            timeout=300,
        )
        # typhoon output can be text/json; keep raw envelope and best-effort parse
        page0 = None
        if isinstance(result, dict):
            rows = result.get("results") or []
            if isinstance(rows, list) and rows:
                page0 = rows[0]
        return {"ok": True, "raw_page1": page0}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def main() -> int:
    ambiguous = json.loads(AMBIGUOUS_JSON.read_text(encoding="utf-8")).get("items", [])
    base = json.loads(BASE_ADJ_JSON.read_text(encoding="utf-8")).get("items", [])
    base_idx = {str(x.get("drive_id", "")): x for x in base}
    existing = _load_existing_results()

    results: list[dict[str, Any]] = []
    for i, item in enumerate(ambiguous, start=1):
        drive_id = str(item.get("drive_id", "")).strip()
        if not drive_id:
            continue
        if drive_id in existing:
            print(f"[{i}/{len(ambiguous)}] reuse {drive_id} (already processed)")
            results.append(existing[drive_id])
            continue
        drive_url = str(item.get("drive_url", f"https://drive.google.com/file/d/{drive_id}/view")).strip()
        print(f"[{i}/{len(ambiguous)}] retry {drive_id} ...")
        row = {
            "drive_id": drive_id,
            "name": item.get("name"),
            "province": item.get("province"),
            "district": item.get("district"),
            "election_type": item.get("election_type") or item.get("type"),
            "our_valid": item.get("our_valid"),
            "killernay_csv_valid": item.get("killernay_csv_valid"),
            "killernay_drive_valid": item.get("killernay_drive_valid"),
            "base_verdict": (base_idx.get(drive_id) or {}).get("verdict"),
            "drive_url": drive_url,
        }
        row["gemini_cached"] = _extract_gemini_cached(drive_id)
        row["local_ocr"] = _run_local_ocr(drive_id, drive_url)
        row["typhoon"] = _run_typhoon(drive_id, drive_url)
        results.append(row)
        _save_results(results)

    _save_results(results)
    print(f"wrote {OUT_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
