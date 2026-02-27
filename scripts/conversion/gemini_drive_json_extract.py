#!/usr/bin/env python3
"""Extract structured JSON from Drive PDFs using Gemini API (resumable).

Flow:
1) Read drive_file_mapping.json (drive_id/name/url metadata).
2) Resolve each file bytes (local_path if available, else public Drive download URL).
3) Send PDF + instruction prompt to Gemini generateContent API.
4) Save raw + parsed JSON per drive_id.
5) Persist state for resume.
"""

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


DEFAULT_MAPPING = "drive_file_mapping.json"
DEFAULT_PROMPT = "prompts/gemini_ballot_json_extraction.md"
DEFAULT_OUT_DIR = "gemini_extractions"
DEFAULT_STATE = "gemini_extractions_state.json"
DEFAULT_MODEL = "gemini-2.0-flash"
DEFAULT_SUMMARY_JSONL = "drive_pdf_summary_only_v3.jsonl"


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


def _extract_drive_id(url: str) -> str:
    m = re.search(r"/file/d/([0-9A-Za-z_-]{10,})", url or "")
    return m.group(1) if m else ""


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
    # Try direct parse.
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else None
    except Exception:
        pass
    # Try first balanced {...}
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        try:
            obj = json.loads(raw[start : end + 1])
            return obj if isinstance(obj, dict) else None
        except Exception:
            return None
    return None


def _normalize_digits(text: str) -> str:
    if not text:
        return ""
    table = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")
    return text.translate(table)


def _detect_form_type_hint(*parts: str) -> Optional[str]:
    full = _normalize_digits("\n".join([p for p in parts if p])).lower()
    if not full:
        return None
    is_bch = bool(
        re.search(
            r"\(บช\)|\bbch\b|party-?list|บัญชีรายชื่อ|list-prorated|party list",
            full,
            flags=re.IGNORECASE,
        )
    )
    code: Optional[str] = None
    for cand in ("5/16", "5/17", "5/18"):
        if cand in full or cand.replace("/", "_") in full or cand.replace("/", " ") in full:
            code = cand
            break
    if not code:
        return None
    return f"ส.ส. {code} (บช)" if is_bch else f"ส.ส. {code}"


def _form_specific_focus(form_type: Optional[str]) -> str:
    if not form_type:
        return (
            "- Detect the exact form type first, then extract fields.\n"
            "- Be strict about page grouping and continuation pages.\n"
            "- Use `null` for uncertain fields and explain uncertainty in `notes`."
        )

    if "5/16" in form_type:
        return (
            "- Prioritize early-voting context fields (set number, counting location, constituency/province).\n"
            "- Extract ballot totals and vote rows with Thai numeral normalization.\n"
            "- Carefully validate `total_ballots` vs valid/invalid/blank totals."
        )
    if "5/17" in form_type:
        return (
            "- Prioritize out-of-district/outside-kingdom context fields (envelopes received, committee set, location).\n"
            "- Extract ballot totals and vote rows with Thai numeral normalization.\n"
            "- Carefully validate `total_ballots` vs valid/invalid/blank totals."
        )
    if "5/18" in form_type:
        return (
            "- Prioritize polling-unit election fields (polling unit, district, constituency, province).\n"
            "- Extract all vote rows on each page and merge across continuation pages.\n"
            "- Carefully validate `total_ballots` vs valid/invalid/blank totals."
        )
    return (
        "- Detect the exact form type first, then extract fields.\n"
        "- Be strict about page grouping and continuation pages.\n"
        "- Use `null` for uncertain fields and explain uncertainty in `notes`."
    )


def _build_prompt(
    prompt_template: str,
    source_name: str,
    page_count: Optional[int] = None,
    form_type_hint: Optional[str] = None,
) -> str:
    text = Path(prompt_template).read_text(encoding="utf-8")
    text = text.replace("<file name>", source_name or "<file name>")
    page_count_token = str(page_count) if page_count is not None else "<int|null>"
    text = text.replace("<int|null>", page_count_token)
    focus = _form_specific_focus(form_type_hint)
    hint = form_type_hint or "unknown"
    text += "\n\n## File-specific extraction focus\n"
    text += f"Detected form type hint from filename/summary metadata: {hint}\n"
    text += "Use this as a hint only; if the PDF header clearly disagrees, trust the PDF.\n"
    text += "Focus for this file:\n"
    text += focus
    return text


def _read_jsonl_rows(path: str) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return []
    out: list[dict[str, Any]] = []
    with p.open("r", encoding="utf-8") as fh:
        for line in fh:
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


def _build_summary_index(path: str) -> dict[str, dict[str, Any]]:
    rows = _read_jsonl_rows(path)
    idx: dict[str, dict[str, Any]] = {}
    for row in rows:
        did = str(row.get("drive_id", "")).strip()
        if did:
            idx[did] = row
    return idx


def _gemini_generate_json(
    *,
    api_key: str,
    model: str,
    prompt: str,
    pdf_bytes: bytes,
    max_retries: int = 3,
    retry_sleep: float = 2.0,
) -> tuple[bool, str, Optional[dict[str, Any]]]:
    endpoint = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    )
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Gemini extraction for Drive files -> strict JSON")
    parser.add_argument("--mapping-file", default=DEFAULT_MAPPING)
    parser.add_argument("--prompt-template", default=DEFAULT_PROMPT)
    parser.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    parser.add_argument("--state-file", default=DEFAULT_STATE)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument(
        "--summary-jsonl",
        default=DEFAULT_SUMMARY_JSONL,
        help="Summary-only JSONL from Drive Gemini overview (used for form-type hinting)",
    )
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--resume", action="store_true", default=True)
    parser.add_argument("--no-resume", dest="resume", action="store_false")
    parser.add_argument("--sleep", type=float, default=0.6, help="Delay between files")
    args = parser.parse_args()

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        print("ERROR: GEMINI_API_KEY is not set")
        return 1

    mapping = _load_json(args.mapping_file, {"files": {}})
    files = mapping.get("files", {}) if isinstance(mapping, dict) else {}
    if not isinstance(files, dict) or not files:
        print("ERROR: no entries in mapping file")
        return 1

    items: list[dict[str, Any]] = []
    for did, entry in files.items():
        if not isinstance(entry, dict):
            continue
        drive_id = str(entry.get("drive_id") or did).strip()
        if not drive_id:
            continue
        items.append(entry)
    items = sorted(items, key=lambda x: str(x.get("drive_id", "")))
    if args.limit and args.limit > 0:
        items = items[: args.limit]

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    state = _load_json(args.state_file, {"done_ids": [], "updated_at_epoch": 0})
    done_ids = set(state.get("done_ids", []) if isinstance(state, dict) else [])
    summary_idx = _build_summary_index(args.summary_jsonl)

    total = len(items)
    ok_count = 0
    fail_count = 0
    for idx, entry in enumerate(items, start=1):
        drive_id = str(entry.get("drive_id", "")).strip()
        name = str(entry.get("name", "")).strip() or f"{drive_id}.pdf"
        if args.resume and drive_id in done_ids:
            print(f"[{idx}/{total}] skip(done): {drive_id} {name}")
            continue

        local_path = str(entry.get("local_path", "")).strip()
        pdf_bytes = _read_local_file_bytes(local_path) if local_path else None
        if pdf_bytes is None:
            pdf_bytes = _download_drive_file_bytes(drive_id)
        if pdf_bytes is None:
            print(f"[{idx}/{total}] fail(download): {drive_id} {name}")
            fail_count += 1
            continue

        summary_row = summary_idx.get(drive_id, {})
        summary_text = ""
        if isinstance(summary_row, dict):
            summary_text = str(summary_row.get("summary", "") or summary_row.get("raw_text", "")).strip()
        form_hint = _detect_form_type_hint(
            name,
            str(entry.get("gemini_summary", "")),
            str(entry.get("gemini_raw_overview", "")),
            summary_text,
        )

        prompt = _build_prompt(
            args.prompt_template,
            source_name=name,
            page_count=None,
            form_type_hint=form_hint,
        )
        (out_dir / f"{drive_id}.prompt.txt").write_text(prompt, encoding="utf-8")
        ok, raw_text, parsed = _gemini_generate_json(
            api_key=api_key,
            model=args.model,
            prompt=prompt,
            pdf_bytes=pdf_bytes,
        )

        raw_path = out_dir / f"{drive_id}.raw.txt"
        raw_path.write_text(raw_text or "", encoding="utf-8")
        if ok and parsed is not None:
            json_path = out_dir / f"{drive_id}.json"
            _save_json(str(json_path), parsed)
            print(f"[{idx}/{total}] ok: {drive_id} {name} hint={form_hint or 'unknown'}")
            ok_count += 1
            done_ids.add(drive_id)
            state = {"done_ids": sorted(done_ids), "updated_at_epoch": int(time.time())}
            _save_json(args.state_file, state)
        else:
            print(f"[{idx}/{total}] fail(parse): {drive_id} {name} hint={form_hint or 'unknown'}")
            fail_count += 1

        time.sleep(max(0.0, args.sleep))

    print(f"Done. ok={ok_count}, fail={fail_count}, total={total}")
    print(f"Output dir: {out_dir}")
    print(f"State file: {args.state_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
