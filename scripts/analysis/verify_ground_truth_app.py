#!/usr/bin/env python3
"""
Advanced Ground Truth Verification App.
Allows users to verify and correct OCR results with a structured form.
Shows side-by-side comparison of AI Detected vs Human Verified data.
"""

import gradio as gr
import os
import json
import re
import asyncio
import urllib.request
import pandas as pd
from pathlib import Path
from typing import Optional, List

# Project imports
from ocr_cache import cache
from ballot_types import FormType, BallotData
from ect_api import ect_data
from vote62_api import get_unit_score_reference
from drive_mapping import upsert_mapping_entry, find_by_local_path

# Configuration
PREVIEW_DIR = "verification_previews"
OUTPUT_FILE = "verified_ground_truth.json"
ORIGINAL_IMAGES_DIR = "test_images" 

FORM_TYPES = [ft.value for ft in FormType]
PROVINCE_LIST: list[str] = []
image_files: list[str] = []
current_data: dict = {}
_drive_mapping_cache: Optional[list[dict]] = None


def _load_province_list() -> list[str]:
    """Load province names from ECT lazily to avoid import-time network calls."""
    try:
        ect_data.load()
        return sorted(ect_data.list_provinces())
    except Exception:
        return []

def load_previews():
    """
    Build review list from original images, not preview availability.
    This prevents page-order gaps when a preview image is missing.
    """
    if not os.path.isdir(ORIGINAL_IMAGES_DIR):
        return []
    files = [
        os.path.join(ORIGINAL_IMAGES_DIR, f)
        for f in os.listdir(ORIGINAL_IMAGES_DIR)
        if f.lower().endswith((".png", ".jpg", ".jpeg"))
    ]
    files.sort(key=lambda p: _sort_key_for_image(os.path.basename(p)))
    return files

def load_existing_truth():
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, "r") as f:
                return json.load(f)
        except:
            return {}
    return {}

def _ensure_runtime_state_loaded():
    """Initialize module runtime state lazily."""
    global image_files, current_data, PROVINCE_LIST
    if not image_files:
        image_files = load_previews()
    if not current_data:
        current_data = load_existing_truth()
    if not PROVINCE_LIST:
        PROVINCE_LIST = _load_province_list()

def get_original_path(item_path):
    """
    Resolve original image path from either preview path or original path.
    """
    filename = os.path.basename(item_path)
    if filename.endswith("_preview.jpg"):
        filename = filename.replace("_preview.jpg", ".png")
    candidate = os.path.join(ORIGINAL_IMAGES_DIR, filename)
    if os.path.exists(candidate):
        return candidate
    return item_path


def _original_filename_from_preview(path_value: str) -> str:
    filename = os.path.basename(path_value)
    if filename.endswith("_preview.jpg"):
        return filename.replace("_preview.jpg", ".png")
    return filename


def _display_image_path(original_path: str) -> str:
    """Always display the original image for verification clarity."""
    return original_path


def _load_drive_mapping_entries() -> list[dict]:
    """Load Drive mapping entries once; used for source-metadata fallback."""
    global _drive_mapping_cache
    if _drive_mapping_cache is not None:
        return _drive_mapping_cache

    mapping_file = Path("drive_file_mapping.json")
    if not mapping_file.exists():
        _drive_mapping_cache = []
        return _drive_mapping_cache

    try:
        payload = json.loads(mapping_file.read_text(encoding="utf-8"))
        files_obj = payload.get("files", {}) if isinstance(payload, dict) else {}
        if isinstance(files_obj, dict):
            _drive_mapping_cache = [v for v in files_obj.values() if isinstance(v, dict)]
        else:
            _drive_mapping_cache = []
    except Exception:
        _drive_mapping_cache = []
    return _drive_mapping_cache


def _infer_form_from_text(text: str, is_bch: bool) -> str:
    hint = (text or "").lower()
    if "5/18" in hint or "5ทับ18" in hint:
        return "ส.ส. 5/18 (บช)" if is_bch else "ส.ส. 5/18"
    if "5/17" in hint or "5ทับ17" in hint:
        return "ส.ส. 5/17 (บช)" if is_bch else "ส.ส. 5/17"
    if "5/16" in hint or "5ทับ16" in hint:
        return "ส.ส. 5/16 (บช)" if is_bch else "ส.ส. 5/16"
    return ""


def _infer_metadata_from_source(original_path: str, filename: str) -> dict:
    """
    Infer province/constituency/unit/form from known source paths (Drive mapping first),
    then local image path. Returns empty dict when no strong signal exists.
    """
    try:
        from metadata_parser import PathMetadataParser
    except Exception:
        return {}

    parser = PathMetadataParser()
    best: tuple[float, dict] = (0.0, {})
    basename = Path(filename).name
    is_bch = "bch" in basename.lower() or "(บช)" in basename
    original_abs = str(Path(original_path).expanduser().resolve())
    candidates: list[str] = [original_abs]

    # Provenance sidecar produced by pdf_to_images* keeps source PDF linkage.
    sidecar = Path(f"{original_abs}.source.json")
    if sidecar.exists():
        try:
            side_payload = json.loads(sidecar.read_text(encoding="utf-8"))
            source_pdf = str(side_payload.get("source_pdf", "")).strip()
            if source_pdf:
                candidates.append(source_pdf)
        except Exception:
            pass

    for entry in _load_drive_mapping_entries():
        try:
            local_path = str(entry.get("local_path", "")).strip()
            name = str(entry.get("name", "")).strip()
            if local_path and Path(local_path).name == basename:
                candidates.append(local_path)
            elif name and name == basename and local_path:
                candidates.append(local_path)
        except Exception:
            continue

    for path_hint in list(dict.fromkeys(candidates)):
        inferred = parser.parse_path(path_hint)
        form_guess = _infer_form_from_text(path_hint, is_bch or inferred.form_type == "party_list")
        data = {
            "province": inferred.province or "",
            "constituency": _safe_int(inferred.constituency_number, 0),
            "unit": _safe_int(inferred.polling_unit, 0),
            "form_type": form_guess,
            "confidence": float(inferred.confidence or 0.0),
            "path_hint": path_hint,
        }
        score = data["confidence"]
        if data["province"]:
            score += 0.4
        if data["constituency"] > 0:
            score += 0.2
        if score > best[0]:
            best = (score, data)

    return best[1]


def _page_group_and_number(filename: str) -> tuple[str, int]:
    """
    Parse filename into a logical page group and page number.
    Examples:
      bch_page-2.png -> ("bch", 2)
      high_res_page-1.png -> ("high_res", 1)
      page-3.png -> ("", 3)
    """
    stem = Path(filename).stem.lower()
    # Accept variants: page-5, page_5, page 5, and extra suffixes after page number.
    match = None
    for m in re.finditer(r"page[\s_-]*0*(\d+)", stem, flags=re.IGNORECASE):
        match = m
    if not match:
        return stem, 1
    group = stem[:match.start()].rstrip("_- ")
    page_no = _safe_int(match.group(1), 1)
    return group, max(1, page_no)


def _sort_key_for_image(filename: str):
    """Stable ordering by logical document group + numeric page number."""
    group, page_no = _page_group_and_number(filename)
    stem = Path(filename).stem.lower()
    return (group, page_no, stem)


def _is_continuation_page(filename: str) -> bool:
    _, page_no = _page_group_and_number(filename)
    return page_no > 1


def _build_page_to_entry_map() -> dict[str, str]:
    """
    Build a map of page filename -> persisted entry key.

    Supports legacy single-page entries (no "pages" list) and new grouped entries.
    """
    mapping: dict[str, str] = {}
    for entry_key, entry in current_data.items():
        if not isinstance(entry, dict):
            continue
        pages = entry.get("pages")
        if isinstance(pages, list) and pages:
            for page_name in pages:
                if isinstance(page_name, str) and page_name.strip():
                    mapping[page_name] = entry_key
        else:
            # Legacy format: key itself is the page filename.
            mapping[entry_key] = entry_key
    return mapping


def _find_entry_key_for_page(index: int, filename: str, force_new_entry: bool = False) -> str:
    """
    Resolve storage entry key for a page.

    Rules:
    - Page 1 starts a new entry (key = page filename), unless already mapped.
    - Continuation pages (2+) reuse nearest previous saved entry in same group.
    - If force_new_entry is True, always start a new entry at this page.
    """
    page_map = _build_page_to_entry_map()

    if force_new_entry:
        return filename

    # Reuse an existing mapping for this page if present.
    if filename in page_map:
        return page_map[filename]

    if not _is_continuation_page(filename):
        return filename

    current_group, _ = _page_group_and_number(filename)
    for prev_idx in range(index - 1, -1, -1):
        prev_filename = _original_filename_from_preview(image_files[prev_idx])
        prev_group, _ = _page_group_and_number(prev_filename)
        if prev_group != current_group:
            continue
        prev_entry_key = page_map.get(prev_filename)
        if prev_entry_key:
            return prev_entry_key

    return filename


def _get_saved_entry_for_page(index: int, filename: str) -> tuple[Optional[str], Optional[dict]]:
    """Return (entry_key, entry_dict) for the given page filename."""
    page_map = _build_page_to_entry_map()
    entry_key = page_map.get(filename)
    if entry_key and isinstance(current_data.get(entry_key), dict):
        return entry_key, current_data.get(entry_key)

    # Fallback for direct legacy key lookup.
    direct = current_data.get(filename)
    if isinstance(direct, dict):
        return filename, direct

    # For continuation pages, fallback to nearest previous entry in same group.
    if _is_continuation_page(filename):
        current_group, _ = _page_group_and_number(filename)
        for prev_idx in range(index - 1, -1, -1):
            prev_filename = _original_filename_from_preview(image_files[prev_idx])
            prev_group, _ = _page_group_and_number(prev_filename)
            if prev_group != current_group:
                continue
            prev_entry_key = page_map.get(prev_filename)
            if prev_entry_key and isinstance(current_data.get(prev_entry_key), dict):
                return prev_entry_key, current_data.get(prev_entry_key)

    return None, None


def _get_inherited_context(index: int) -> Optional[dict]:
    """
    For continuation pages, inherit context from the nearest previous page
    in the same document group (saved truth preferred, OCR fallback).
    """
    if index <= 0:
        return None
    current_filename = _original_filename_from_preview(image_files[index])
    current_group, current_page = _page_group_and_number(current_filename)
    if current_page <= 1:
        return None

    # Pass 1: use nearest saved human-verified context in the same group.
    for prev_idx in range(index - 1, -1, -1):
        prev_filename = _original_filename_from_preview(image_files[prev_idx])
        prev_group, prev_page = _page_group_and_number(prev_filename)
        if prev_group != current_group:
            continue
        _, saved = _get_saved_entry_for_page(prev_idx, prev_filename)
        if saved:
            return {
                "source": f"saved page {prev_page}",
                "form_type": saved.get("form_type", ""),
                "province": saved.get("province", ""),
                "constituency": _safe_int(saved.get("constituency", 0), 0),
                "unit": _safe_int(saved.get("unit", 0), 0),
                "total_ballots": _safe_int(saved.get("total_ballots", saved.get("total_votes", 0)), 0),
                "valid_votes": _safe_int(saved.get("valid_votes", 0), 0),
                "invalid_votes": _safe_int(saved.get("invalid_votes", 0), 0),
                "blank_votes": _safe_int(saved.get("blank_votes", 0), 0),
                "votes": {str(k): _safe_int(v, 0) for k, v in saved.get("votes", {}).items()},
            }

    # Pass 2: if no saved context exists, fallback to nearest OCR context.
    for prev_idx in range(index - 1, -1, -1):
        prev_filename = _original_filename_from_preview(image_files[prev_idx])
        prev_group, prev_page = _page_group_and_number(prev_filename)
        if prev_group != current_group:
            continue
        prev_preview = image_files[prev_idx]
        ocr_prev = get_ocr_data(prev_preview)
        if ocr_prev:
            raw_votes = ocr_prev.vote_counts if ocr_prev.form_category == "constituency" else ocr_prev.party_votes
            return {
                "source": f"OCR page {prev_page}",
                "form_type": ocr_prev.form_type,
                "province": ocr_prev.province,
                "constituency": _safe_int(ocr_prev.constituency_number, 0),
                "unit": _safe_int(ocr_prev.polling_unit, 0),
                "total_ballots": _safe_int(ocr_prev.total_votes, 0),
                "valid_votes": _safe_int(ocr_prev.valid_votes, 0),
                "invalid_votes": _safe_int(ocr_prev.invalid_votes, 0),
                "blank_votes": _safe_int(ocr_prev.blank_votes, 0),
                "votes": {str(k): _safe_int(v, 0) for k, v in raw_votes.items()},
            }
    return None

def get_ocr_data(preview_path) -> Optional[BallotData]:
    """Fetch OCR result from cache, with live-extraction fallback."""
    orig_path = get_original_path(preview_path)
    cached = cache.get(orig_path)
    if cached is not None:
        return cached

    if not os.path.exists(orig_path):
        return None

    # Cache miss fallback: run extraction so AI panel is populated.
    try:
        from ballot_extraction import extract_ballot_data_with_ai
        extracted = extract_ballot_data_with_ai(orig_path)
        if extracted is not None:
            cache.set(orig_path, extracted)
        return extracted
    except Exception:
        return None

def format_votes_for_df(votes_dict: dict) -> List[List]:
    if not votes_dict:
        return []
    return [[str(k), v] for k, v in sorted(votes_dict.items(), key=lambda x: int(x[0]) if str(x[0]).isdigit() else 999)]


def _extract_votes_map(votes_df) -> dict[str, int]:
    """Normalize vote dataframe/list into {number: votes} map."""
    votes_dict: dict[str, int] = {}
    if votes_df is None:
        return votes_dict
    data = votes_df.values.tolist() if hasattr(votes_df, "values") else votes_df
    for row in data:
        try:
            if not row:
                continue
            key_raw = str(row[0]).strip()
            if not key_raw:
                continue
            votes_idx = 2 if len(row) >= 3 else 1
            vote_raw = row[votes_idx]
            vote_int = int(float(vote_raw)) if str(vote_raw).strip() else 0
            key = str(int(float(key_raw))) if key_raw.replace(".", "", 1).isdigit() else key_raw
            if not key.isdigit():
                continue
            votes_dict[key] = vote_int
        except Exception:
            continue
    return votes_dict


def _is_party_list_form(form_type: str) -> bool:
    return "(บช)" in (form_type or "")


def _safe_int(value, default: int = 0) -> int:
    """Parse int-like values safely."""
    try:
        if value in (None, ""):
            return default
        return int(float(value))
    except Exception:
        return default


def _totals_consistency_message(total_ballots, valid_votes, invalid_votes, blank_votes) -> str:
    total = _safe_int(total_ballots, 0)
    valid = _safe_int(valid_votes, 0)
    invalid = _safe_int(invalid_votes, 0)
    blank = _safe_int(blank_votes, 0)
    summed = valid + invalid + blank
    if total and summed != total:
        return f"Warning: valid+invalid+blank = {summed}, but total = {total}"
    return "Totals look consistent"


def _build_vote_score_comparison_rows(
    *,
    ai_votes: dict,
    vote62_votes: dict,
    human_votes: dict,
    labels_by_no: Optional[dict[str, str]] = None,
) -> list[list]:
    """Build side-by-side candidate/party score rows."""
    ai_votes = {str(k): _safe_int(v, 0) for k, v in (ai_votes or {}).items()}
    vote62_votes = {str(k): _safe_int(v, 0) for k, v in (vote62_votes or {}).items()}
    human_votes = {str(k): _safe_int(v, 0) for k, v in (human_votes or {}).items()}
    labels_by_no = labels_by_no or {}

    keys = sorted(
        set(ai_votes.keys()) | set(vote62_votes.keys()) | set(human_votes.keys()),
        key=lambda x: int(x) if str(x).isdigit() else 999999,
    )
    rows: list[list] = []
    for key in keys:
        rows.append([
            key,
            labels_by_no.get(str(key), ""),
            ai_votes.get(str(key), 0),
            vote62_votes.get(str(key), 0),
            human_votes.get(str(key), 0),
        ])
    return rows


def _build_totals_comparison_rows(
    *,
    ai_total: int,
    ai_valid: int,
    ai_invalid: int,
    ai_blank: int,
    ai_votes: dict,
    vote62_total: int,
    vote62_valid: int,
    vote62_invalid: int,
    vote62_blank: int,
    vote62_votes: dict,
    human_total: int,
    human_valid: int,
    human_invalid: int,
    human_blank: int,
    human_votes: dict,
) -> list[list]:
    """Build side-by-side totals rows by metric."""
    ai_vote_sum = sum(_safe_int(v, 0) for v in (ai_votes or {}).values())
    vote62_vote_sum = sum(_safe_int(v, 0) for v in (vote62_votes or {}).values())
    human_vote_sum = sum(_safe_int(v, 0) for v in (human_votes or {}).values())
    return [
        ["Total Ballots", _safe_int(ai_total, 0), _safe_int(vote62_total, 0), _safe_int(human_total, 0)],
        ["Valid", _safe_int(ai_valid, 0), _safe_int(vote62_valid, 0), _safe_int(human_valid, 0)],
        ["Invalid", _safe_int(ai_invalid, 0), _safe_int(vote62_invalid, 0), _safe_int(human_invalid, 0)],
        ["Blank", _safe_int(ai_blank, 0), _safe_int(vote62_blank, 0), _safe_int(human_blank, 0)],
        ["Vote Sum", ai_vote_sum, vote62_vote_sum, human_vote_sum],
    ]


def _extract_gemini_summary_text(page_text: str) -> str:
    """Extract Gemini summary block from Google Drive file page text."""
    if not page_text:
        return ""
    start_idx = page_text.find("Summary")
    if start_idx < 0:
        return ""
    tail = page_text[start_idx + len("Summary"):].strip()
    stop_tokens = [
        "\nShow more",
        "\nList the main points for this file",
        "\nAsk a question about this file",
        "\nAsk Gemini",
        "\nGood suggestion",
        "\nBad suggestion",
    ]
    end_idx = len(tail)
    for token in stop_tokens:
        pos = tail.find(token)
        if pos >= 0:
            end_idx = min(end_idx, pos)
    return tail[:end_idx].strip()


def _extract_drive_file_id(url: str) -> str:
    """Extract Drive file ID from URL."""
    match = re.search(r"/file/d/([0-9A-Za-z_-]{10,})", url or "")
    return match.group(1) if match else ""


def _find_drive_mapping_entry_for_image(original_path: str, filename: str) -> Optional[dict]:
    """Best-effort mapping lookup for current image/page."""
    try:
        direct = find_by_local_path(original_path)
        if isinstance(direct, dict):
            return direct
    except Exception:
        pass

    target_name = Path(filename).name
    for entry in _load_drive_mapping_entries():
        try:
            local_path = str(entry.get("local_path", "")).strip()
            if local_path and Path(local_path).name == target_name:
                return entry
            if str(entry.get("name", "")).strip() == target_name:
                return entry
        except Exception:
            continue
    return None


def _display_name_from_title(title: str, drive_id: str) -> str:
    """Clean Drive file title to get display name."""
    clean = (title or "").strip()
    suffix = " - Google Drive"
    if clean.endswith(suffix):
        clean = clean[: -len(suffix)].strip()
    return clean or drive_id


def _get_drive_file_target(devtools_url: str = "http://127.0.0.1:9222/json") -> Optional[dict]:
    """Get a likely Google Drive file tab target from Chrome DevTools."""
    try:
        with urllib.request.urlopen(devtools_url, timeout=3) as resp:
            targets = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
    if not isinstance(targets, list):
        return None
    # Prefer file preview tabs first.
    for t in targets:
        if not isinstance(t, dict):
            continue
        if t.get("type") != "page":
            continue
        url = str(t.get("url", ""))
        if "drive.google.com/file/d/" in url and "google drive" in str(t.get("title", "")).lower():
            return t
    # Fallback: any Drive page.
    for t in targets:
        if not isinstance(t, dict):
            continue
        if t.get("type") != "page":
            continue
        url = str(t.get("url", ""))
        if "drive.google.com/" in url:
            return t
    return None


async def _read_cdp_page_text(ws_url: str, max_chars: int = 30000) -> str:
    """Read visible page text from a Chrome DevTools page target."""
    try:
        import websockets  # optional runtime dependency
    except Exception as exc:
        raise RuntimeError("Missing dependency: install 'websockets' in the venv") from exc

    async with websockets.connect(ws_url, max_size=20_000_000) as sock:
        msg_id = 0

        async def send(method: str, params: Optional[dict] = None):
            nonlocal msg_id
            msg_id += 1
            payload = {"id": msg_id, "method": method, "params": params or {}}
            await sock.send(json.dumps(payload))
            while True:
                obj = json.loads(await sock.recv())
                if obj.get("id") == msg_id:
                    return obj

        await send("Runtime.enable")
        expr = f"document.body ? document.body.innerText.slice(0, {max_chars}) : ''"
        res = await send("Runtime.evaluate", {"expression": expr, "returnByValue": True})
        return str(res.get("result", {}).get("result", {}).get("value", "") or "")


def fetch_drive_context_click():
    """
    Fetch Gemini context from an open Google Drive tab in local Chrome.
    Requires Chrome to be launched with --remote-debugging-port=9222.
    Persists the mapping to drive_file_mapping.json.
    """
    target = _get_drive_file_target()
    if not target:
        return (
            "No Google Drive tab found in Chrome DevTools. Open a Drive file tab first.",
            "",
        )
    ws_url = target.get("webSocketDebuggerUrl")
    if not ws_url:
        return ("Could not access DevTools websocket for selected tab.", "")

    drive_url = str(target.get("url", ""))
    drive_id = _extract_drive_file_id(drive_url)
    title = str(target.get("title", ""))

    try:
        page_text = asyncio.run(_read_cdp_page_text(str(ws_url)))
    except Exception as exc:
        return (f"Failed to read Drive tab: {exc}", "")

    summary = _extract_gemini_summary_text(page_text)
    content = summary if summary else (page_text[:12000] if page_text.strip() else "")

    # Persist to mapping file
    if drive_id and content:
        name = _display_name_from_title(title, drive_id)
        try:
            upsert_mapping_entry(
                drive_id=drive_id,
                drive_url=drive_url,
                name=name,
                gemini_summary=content,
            )
            persist_status = f"Saved to mapping (id={drive_id[:12]}...)"
        except Exception as e:
            persist_status = f"Warning: could not save mapping: {e}"
    else:
        persist_status = "No Drive ID or content to save"

    if summary:
        status = f"Gemini summary extracted. {persist_status}"
        return status, summary
    if page_text.strip():
        status = f"Drive tab text captured (no Gemini summary). {persist_status}"
        return status, page_text[:12000]
    return ("Drive tab loaded but no visible text was captured", "")


def _is_missing_text(value) -> bool:
    return value is None or str(value).strip() == "" or str(value).lower() == "none"


def _build_vote_template_rows(
    form_type: str,
    province: str,
    constituency: int,
    existing_votes: Optional[dict[str, int]] = None,
) -> tuple[list[list], str]:
    """
    Build vote entry rows as [number, label, votes].
    Returns (rows, source_label).
    """
    _ensure_runtime_state_loaded()
    existing_votes = existing_votes or {}
    rows: list[list] = []

    if _is_party_list_form(form_type):
        try:
            parties = ect_data.list_parties()
            seen_party_numbers: set[str] = set()
            for party_no, party_name in parties:
                if party_no in seen_party_numbers:
                    continue
                seen_party_numbers.add(party_no)
                party_obj = ect_data.get_party_by_number(int(party_no))
                abbr = party_obj.abbr if party_obj else ""
                label = f"{party_name} ({abbr})" if abbr else party_name
                rows.append([str(party_no), label, existing_votes.get(str(party_no), 0)])
            return rows, "party"
        except Exception:
            pass
    else:
        try:
            cons_no = int(float(constituency)) if constituency else 0
            lookup_province = _resolve_province_name(province or "")
            if lookup_province and cons_no > 0:
                candidates = ect_data.get_candidates_by_thai_province(lookup_province, cons_no)
                for c in candidates:
                    party = ect_data.get_party_for_candidate(c)
                    party_abbr = party.abbr if party else ""
                    label = f"{c.mp_app_name} ({party_abbr})" if party_abbr else c.mp_app_name
                    key = str(c.position)
                    rows.append([key, label, existing_votes.get(key, 0)])
                if rows:
                    return rows, "candidate"
        except Exception:
            pass

    # Fallback: keep whatever keys already exist so user doesn't lose entered work.
    for k in sorted(existing_votes.keys(), key=lambda x: int(x) if str(x).isdigit() else 999):
        rows.append([str(k), "", existing_votes.get(str(k), 0)])
    return rows, "existing"


def _resolve_province_name(province: str) -> str:
    """
    Resolve user-entered province text to canonical ECT Thai province name.
    Handles common variants like whitespace and "จังหวัด" prefix.
    """
    raw = (province or "").strip()
    if not raw:
        return ""

    try:
        is_valid, canonical = ect_data.validate_province_name(raw)
        if is_valid and canonical:
            return canonical
    except Exception:
        pass

    normalized = raw.replace(" ", "")
    if normalized.startswith("จังหวัด"):
        normalized = normalized[7:]

    try:
        candidates = ect_data.list_provinces()
    except Exception:
        return raw

    for p in candidates:
        p_norm = p.replace(" ", "")
        if p_norm == normalized:
            return p
    for p in candidates:
        p_norm = p.replace(" ", "")
        if normalized and (normalized in p_norm or p_norm in normalized):
            return p
    return raw


def refresh_vote_template(form_type, province, constituency, votes_df):
    """Auto-populate candidate/party rows while preserving entered vote values."""
    existing_votes = _extract_votes_map(votes_df)
    cons_no = _safe_int(constituency, 0)
    resolved_province = _resolve_province_name(province or "")
    rows, source = _build_vote_template_rows(form_type, resolved_province, cons_no, existing_votes)
    if source == "candidate":
        msg = "Auto-filled candidate list from ECT data"
    elif source == "party":
        msg = "Auto-filled party list from ECT data"
    elif source == "existing":
        msg = "Using existing vote rows (candidate/party list not found yet)"
    else:
        msg = "Vote template updated"
    return rows, msg

def load_all_data(index):
    _ensure_runtime_state_loaded()
    if not (0 <= index < len(image_files)):
        # Return empty/dummy values matching the output signature
        return (
            None, "Done", "Done", "",
            [],
            [],
            "", "", 0, 0, 0, 0, 0, 0, [],
            "", 0, 0, 0, 0, [],
            "", 0, 0, 0, 0, [],
            "No Drive mapping", "",
            "", "", 0, 0, 0, 0, 0, 0, [], index
            , False, False
        )

    original_path = image_files[index]
    img_path = _display_image_path(original_path)
    filename = _original_filename_from_preview(original_path)
    source_meta = _infer_metadata_from_source(original_path, filename)
    continuation = _is_continuation_page(filename)
    lock_metadata = False
    force_new_entry = False
    
    # 1. Get OCR Data (AI Prediction)
    ocr_result = get_ocr_data(img_path)
    
    ocr_form = ""
    ocr_prov = ""
    ocr_cons = 0
    ocr_unit = 0
    ocr_total = 0
    ocr_valid = 0
    ocr_invalid = 0
    ocr_blank = 0
    ocr_votes = []
    
    if ocr_result:
        ocr_form = ocr_result.form_type
        ocr_prov = ocr_result.province
        ocr_cons = ocr_result.constituency_number
        ocr_unit = ocr_result.polling_unit
        ocr_total = ocr_result.total_votes
        ocr_valid = ocr_result.valid_votes
        ocr_invalid = ocr_result.invalid_votes
        ocr_blank = ocr_result.blank_votes
        raw_votes = ocr_result.vote_counts if ocr_result.form_category == "constituency" else ocr_result.party_votes
        ocr_votes = format_votes_for_df(raw_votes)

    # Optional unit-level reference from Vote62 (kept as a separate source panel).
    vote62_note = ""
    vote62_ref = None
    vote62_status = "No Vote62 reference"
    vote62_total = 0
    vote62_valid = 0
    vote62_invalid = 0
    vote62_blank = 0
    vote62_votes = []
    lookup_form = ocr_form or source_meta.get("form_type", "")
    lookup_prov = ocr_prov or source_meta.get("province", "")
    lookup_cons = _safe_int(ocr_cons, 0) or _safe_int(source_meta.get("constituency", 0), 0)
    lookup_unit = _safe_int(ocr_unit, 0) or _safe_int(source_meta.get("unit", 0), 0)
    if lookup_prov and lookup_cons > 0 and lookup_unit > 0:
        try:
            vote62_ref = get_unit_score_reference(
                province=lookup_prov,
                constituency_no=lookup_cons,
                polling_unit=lookup_unit,
                form_type=lookup_form,
            )
        except Exception:
            vote62_ref = None
    if vote62_ref:
        vote62_total = _safe_int(vote62_ref.get("total_ballots", 0), 0)
        vote62_valid = _safe_int(vote62_ref.get("valid_votes", 0), 0)
        vote62_invalid = _safe_int(vote62_ref.get("invalid_votes", 0), 0)
        vote62_blank = _safe_int(vote62_ref.get("blank_votes", 0), 0)
        vote62_votes = format_votes_for_df(vote62_ref.get("votes", {}))
        station = str(vote62_ref.get("station_name", "")).strip()
        vote62_status = "Vote62 unit-level reference loaded"
        if station:
            vote62_status = f"{vote62_status}: {station}"
        vote62_note = " (Vote62 reference available)"

    # Optional ECT constituency-level aggregate reference.
    ect_status = "No ECT reference"
    ect_total = 0
    ect_valid = 0
    ect_invalid = 0
    ect_blank = 0
    ect_votes: dict = {}
    ect_votes_df = []
    ect_prov = _resolve_province_name(lookup_prov)
    ect_cons = lookup_cons
    if ect_prov and ect_cons > 0:
        try:
            prov_abbr = ect_data.get_province_abbr(ect_prov)
            if prov_abbr:
                cons_id = f"{prov_abbr}_{ect_cons}"
                official = ect_data.get_official_constituency_results(cons_id)
                if official:
                    is_party = _is_party_list_form(lookup_form)
                    raw_ect_votes = official.get("party_votes", {}) if is_party else official.get("vote_counts", {})
                    ect_votes = {str(k): _safe_int(v, 0) for k, v in (raw_ect_votes or {}).items()}
                    ect_votes_df = format_votes_for_df(ect_votes)
                    ect_total = _safe_int(official.get("total", 0), 0)
                    ect_valid = _safe_int(official.get("valid_votes", 0), 0)
                    ect_invalid = _safe_int(official.get("invalid_votes", 0), 0)
                    ect_blank = _safe_int(official.get("blank_votes", 0), 0)
                    ect_status = "ECT constituency aggregate loaded"
                    if lookup_unit > 0:
                        ect_status = f"{ect_status} (unit {lookup_unit} comparison is aggregate-only)"
                else:
                    ect_status = "No official ECT constituency aggregate found"
            else:
                ect_status = "Province not found in ECT reference"
        except Exception:
            ect_status = "Failed to load ECT aggregate"

    # Optional Drive/Gemini context from mapping for this image.
    drive_status = "No Drive mapping"
    drive_summary = ""
    drive_entry = _find_drive_mapping_entry_for_image(original_path, filename)
    if isinstance(drive_entry, dict):
        drive_id = str(drive_entry.get("drive_id", "")).strip()
        drive_summary = str(drive_entry.get("gemini_summary", "")).strip()
        if not drive_summary:
            drive_summary = str(drive_entry.get("gemini_raw_overview", "")).strip()
        if drive_summary:
            drive_status = f"Loaded from mapping ({drive_id[:12]}...)" if drive_id else "Loaded from mapping"
        else:
            drive_status = f"Drive mapping found ({drive_id[:12]}...), but no summary yet" if drive_id else "Drive mapping found, but no summary yet"

    # 2. Get Manual Data (Saved Truth)
    entry_key, saved_entry = _get_saved_entry_for_page(index, filename)
    
    # Defaults for manual form (pre-fill with OCR if not saved)
    man_form = source_meta.get("form_type") or (ocr_form if ocr_form else FORM_TYPES[0])
    man_prov = source_meta.get("province") or (ocr_prov if ocr_prov else "")
    man_cons = _safe_int(source_meta.get("constituency", 0), 0) or _safe_int(ocr_cons, 0)
    man_unit = _safe_int(source_meta.get("unit", 0), 0) or _safe_int(ocr_unit, 0)
    man_total = ocr_total
    man_valid = ocr_valid
    man_invalid = ocr_invalid
    man_blank = ocr_blank
    ocr_votes_map = {str(k): v for k, v in (raw_votes.items() if ocr_result else [])}
    # Always initialize manual vote map to avoid branch-specific unbound errors.
    man_votes_map = dict(ocr_votes_map)
    man_votes = []
    
    status = "Reviewing New Image"
    if source_meta.get("province") or source_meta.get("constituency"):
        status = "Reviewing New Image (source metadata prefilled)"
    
    if saved_entry:
        man_form = saved_entry.get("form_type", man_form)
        man_prov = saved_entry.get("province", man_prov)
        man_cons = saved_entry.get("constituency", man_cons)
        man_unit = saved_entry.get("unit", man_unit)
        man_total = saved_entry.get("total_ballots", saved_entry.get("total_votes", man_total))
        man_valid = saved_entry.get("valid_votes", man_valid)
        man_invalid = saved_entry.get("invalid_votes", man_invalid)
        man_blank = saved_entry.get("blank_votes", man_blank)
        man_votes_map = {str(k): v for k, v in saved_entry.get("votes", {}).items()}
        page_force_map = saved_entry.get("page_force_new_entry", {}) if isinstance(saved_entry, dict) else {}
        if not isinstance(page_force_map, dict):
            page_force_map = {}
        force_new_entry = bool(page_force_map.get(filename, saved_entry.get("force_new_entry", False)))
        status = "Loaded Saved Verification"

        # Continuation rule: unless explicitly forced as new entry, header metadata
        # follows the previous page context.
        if continuation and not force_new_entry:
            inherited = _get_inherited_context(index)
            if inherited:
                man_form = inherited.get("form_type") or man_form
                man_prov = inherited.get("province") or man_prov
                man_cons = inherited.get("constituency", man_cons)
                man_unit = inherited.get("unit", man_unit)
                man_total = inherited.get("total_ballots", man_total)
                man_valid = inherited.get("valid_votes", man_valid)
                man_invalid = inherited.get("invalid_votes", man_invalid)
                man_blank = inherited.get("blank_votes", man_blank)
                # If current page has no saved votes yet, inherit previous page vote figures.
                if not man_votes_map and inherited.get("votes"):
                    man_votes_map = {str(k): _safe_int(v, 0) for k, v in inherited["votes"].items()}
                status = f"{status} (continuation header synced from {inherited.get('source', 'previous page')})"
    else:
        # Continuation pages inherit metadata/totals from the previous page in the same group.
        if continuation:
            inherited = _get_inherited_context(index)
            if inherited:
                man_form = inherited.get("form_type") or man_form
                man_prov = inherited.get("province") or man_prov
                man_cons = inherited.get("constituency", man_cons)
                man_unit = inherited.get("unit", man_unit)
                man_total = inherited.get("total_ballots", man_total)
                man_valid = inherited.get("valid_votes", man_valid)
                man_invalid = inherited.get("invalid_votes", man_invalid)
                man_blank = inherited.get("blank_votes", man_blank)
                if inherited.get("votes"):
                    man_votes_map = {str(k): _safe_int(v, 0) for k, v in inherited["votes"].items()}
                status = f"Continuation page: inherited metadata from {inherited.get('source', 'previous page')}"
            else:
                status = "Continuation page: no inherited metadata found; enter metadata to populate candidate/party rows"
                man_votes_map = ocr_votes_map

    if not ocr_result:
        status = f"{status} (AI detection unavailable)"
    if vote62_note:
        status = f"{status}{vote62_note}"

    man_votes, template_source = _build_vote_template_rows(man_form, man_prov, man_cons, man_votes_map)
    labels_by_no = {str(r[0]).strip(): str(r[1]).strip() for r in man_votes if isinstance(r, list) and len(r) >= 2}
    man_votes_map_for_compare = _extract_votes_map(man_votes)
    ai_votes_map_for_compare = {str(k): _safe_int(v, 0) for k, v in (ocr_votes_map or {}).items()}
    vote62_votes_map_for_compare = {str(k): _safe_int(v, 0) for k, v in (vote62_ref.get("votes", {}) if vote62_ref else {}).items()}
    score_comparison_rows = _build_vote_score_comparison_rows(
        ai_votes=ai_votes_map_for_compare,
        vote62_votes=vote62_votes_map_for_compare,
        human_votes=man_votes_map_for_compare,
        labels_by_no=labels_by_no,
    )
    totals_comparison_rows = _build_totals_comparison_rows(
        ai_total=_safe_int(ocr_total, 0),
        ai_valid=_safe_int(ocr_valid, 0),
        ai_invalid=_safe_int(ocr_invalid, 0),
        ai_blank=_safe_int(ocr_blank, 0),
        ai_votes=ai_votes_map_for_compare,
        vote62_total=vote62_total,
        vote62_valid=vote62_valid,
        vote62_invalid=vote62_invalid,
        vote62_blank=vote62_blank,
        vote62_votes=vote62_votes_map_for_compare,
        human_total=_safe_int(man_total, 0),
        human_valid=_safe_int(man_valid, 0),
        human_invalid=_safe_int(man_invalid, 0),
        human_blank=_safe_int(man_blank, 0),
        human_votes=man_votes_map_for_compare,
    )
    if continuation and template_source in {"candidate", "party"} and not force_new_entry:
        lock_metadata = True

    progress = f"{index + 1} / {len(image_files)}"
    
    return (
        img_path, filename, status, progress,
        score_comparison_rows,
        totals_comparison_rows,
        # OCR Data
        ocr_form, ocr_prov, ocr_cons, ocr_unit, ocr_total, ocr_valid, ocr_invalid, ocr_blank, ocr_votes,
        # ECT aggregate data
        ect_status, ect_total, ect_valid, ect_invalid, ect_blank, ect_votes_df,
        # Vote62 Reference Data
        vote62_status, vote62_total, vote62_valid, vote62_invalid, vote62_blank, vote62_votes,
        # Drive/Gemini mapping data
        drive_status, drive_summary,
        # Manual Data
        man_form, man_prov, man_cons, man_unit, man_total, man_valid, man_invalid, man_blank, man_votes,
        # State
        index,
        lock_metadata,
        force_new_entry
    )

def save_current(
    index,
    filename,
    form_type,
    province,
    constituency,
    unit,
    total_ballots,
    valid_votes,
    invalid_votes,
    blank_votes,
    votes_df,
    force_new_entry=False
):
    _ensure_runtime_state_loaded()
    if filename and filename != "Done":
        votes_dict = _extract_votes_map(votes_df)
        entry_key = _find_entry_key_for_page(index, filename, bool(force_new_entry))
        existing_entry = current_data.get(entry_key, {})
        if not isinstance(existing_entry, dict):
            existing_entry = {}

        page_force_map = existing_entry.get("page_force_new_entry", {})
        if not isinstance(page_force_map, dict):
            page_force_map = {}
        page_force_map[filename] = bool(force_new_entry)

        existing_pages = existing_entry.get("pages", [])
        if not isinstance(existing_pages, list):
            existing_pages = []
        pages = list(dict.fromkeys([*existing_pages, filename]))

        current_data[entry_key] = {
            "form_type": form_type,
            "province": province,
            "constituency": _safe_int(constituency, 0),
            "unit": _safe_int(unit, 0),
            "total_ballots": _safe_int(total_ballots, 0),
            "valid_votes": _safe_int(valid_votes, 0),
            "invalid_votes": _safe_int(invalid_votes, 0),
            "blank_votes": _safe_int(blank_votes, 0),
            "force_new_entry": bool(force_new_entry),  # backward compatibility
            "page_force_new_entry": page_force_map,
            "pages": pages,
            "votes": votes_dict if votes_dict else existing_entry.get("votes", {})
        }

        # Clean up legacy per-page duplicate key if this page now belongs to a grouped entry.
        if entry_key != filename and filename in current_data and isinstance(current_data.get(filename), dict):
            del current_data[filename]
        
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(current_data, f, ensure_ascii=False, indent=2)

def next_click(index, filename, form, prov, cons, unit, total_ballots, valid_votes, invalid_votes, blank_votes, votes, force_new_entry):
    save_current(index, filename, form, prov, cons, unit, total_ballots, valid_votes, invalid_votes, blank_votes, votes, force_new_entry)
    return load_all_data(index + 1)

def prev_click(index, filename, form, prov, cons, unit, total_ballots, valid_votes, invalid_votes, blank_votes, votes, force_new_entry):
    save_current(index, filename, form, prov, cons, unit, total_ballots, valid_votes, invalid_votes, blank_votes, votes, force_new_entry)
    return load_all_data(max(0, index - 1))


def _continuation_lock_updates(lock_metadata: bool):
    """Return component updates to lock metadata fields when context is ready."""
    editable = not bool(lock_metadata)
    return (
        gr.update(interactive=editable),  # man_form_input
        gr.update(interactive=editable),  # man_prov_input
        gr.update(interactive=editable),  # man_cons_input
        gr.update(interactive=editable),  # man_unit_input
        gr.update(interactive=editable),  # man_total_input
        gr.update(interactive=editable),  # man_valid_input
        gr.update(interactive=editable),  # man_invalid_input
        gr.update(interactive=editable),  # man_blank_input
    )


def _continuation_banner(lock_metadata: bool, force_new_entry: bool = False):
    """Render page mode message."""
    if force_new_entry:
        return (
            "<div style='padding:10px; border-radius:8px; background:#cfe2ff; "
            "border:1px solid #9ec5fe; color:#084298; font-weight:600;'>"
            "Page Mode: New entry override. Continuation inheritance is disabled for this page. "
            "Fill metadata/totals as a new header."
            "</div>"
        )
    if lock_metadata:
        return (
            "<div style='padding:10px; border-radius:8px; background:#fff3cd; "
            "border:1px solid #ffecb5; color:#664d03; font-weight:600;'>"
            "Page Mode: Continuation page (page 2+). "
            "Metadata and totals are inherited from previous saved page and locked. "
            "Enter only vote counts."
            "</div>"
        )
    return (
        "<div style='padding:10px; border-radius:8px; background:#d1e7dd; "
        "border:1px solid #badbcc; color:#0f5132; font-weight:600;'>"
        "Page Mode: Editable. Fill or adjust metadata/totals, then enter vote counts. "
        "For continuation pages, fields lock automatically after template population."
        "</div>"
    )


def _apply_mode_updates(lock_metadata: bool, force_new_entry: bool):
    """
    Apply effective lock state and banner.
    force_new_entry always unlocks metadata fields.
    """
    effective_lock = bool(lock_metadata) and not bool(force_new_entry)
    lock_updates = _continuation_lock_updates(effective_lock)
    banner = _continuation_banner(effective_lock, bool(force_new_entry))
    return (*lock_updates, banner)

def build_demo() -> gr.Blocks:
    """Build verifier UI lazily."""
    _ensure_runtime_state_loaded()

    with gr.Blocks(title="Ballot Ground Truth Verifier") as demo:
        gr.Markdown("# Ballot Ground Truth Verifier")
        gr.Markdown(
            "Reference note: ECT API vote figures are constituency-level aggregates "
            "(district totals), not per-polling-unit breakdowns. This screen uses ECT "
            "data only to populate candidate/party labels."
        )
        current_index = gr.State(value=0)
        lock_state = gr.State(value=False)

        # Keep key ballot identity fields pinned at the top.
        with gr.Row():
            man_form_input = gr.Dropdown(choices=FORM_TYPES, label="Form Type", allow_custom_value=True, scale=2)
            man_prov_input = gr.Dropdown(choices=PROVINCE_LIST, label="Province", allow_custom_value=True, scale=2)
            man_cons_input = gr.Number(label="Constituency", precision=0, scale=1)
            man_unit_input = gr.Number(label="Unit", precision=0, scale=1)
        
        with gr.Row():
            # Left: ballot image
            with gr.Column(scale=3):
                image_display = gr.Image(label="Preview", type="filepath", height=760)

            # Right: compact verification form
            with gr.Column(scale=2):
                gr.Markdown("### 👤 Human Verification")
                with gr.Row():
                    filename_display = gr.Textbox(label="Filename", interactive=False, scale=2)
                    progress_display = gr.Textbox(label="Progress", interactive=False, scale=1)
                status_display = gr.Textbox(label="Status", interactive=False)
                page_mode_banner = gr.Markdown("")
                override_new_entry_chk = gr.Checkbox(
                    label="Treat this page as NEW entry (override continuation inheritance)",
                    value=False
                )

                with gr.Row():
                    man_total_input = gr.Number(label="Total", precision=0)
                    man_valid_input = gr.Number(label="Valid", precision=0)
                    man_invalid_input = gr.Number(label="Invalid", precision=0)
                    man_blank_input = gr.Number(label="Blank", precision=0)

                refresh_template_btn = gr.Button("Refresh Candidate/Party List")
                score_comparison_disp = gr.Dataframe(
                    headers=["No.", "Name / Party", "AI", "Vote62", "Human"],
                    datatype=["str", "str", "number", "number", "number"],
                    label="Candidate/Party Scores (AI vs Vote62 vs Human)",
                    interactive=False,
                )
                totals_comparison_disp = gr.Dataframe(
                    headers=["Metric", "AI", "Vote62", "Human"],
                    datatype=["str", "number", "number", "number"],
                    label="Totals (AI vs Vote62 vs Human)",
                    interactive=False,
                )

                man_votes_input = gr.Dataframe(
                    headers=["No.", "Name / Party", "Votes"],
                    datatype=["str", "str", "number"],
                    label="Verified Votes",
                    interactive=True,
                    column_count=(3, "fixed")
                )

                with gr.Row():
                    prev_btn = gr.Button("<< Previous")
                    next_btn = gr.Button("Save & Next >>", variant="primary")

                with gr.Accordion("AI / ECT / Vote62 / Drive Details", open=False):
                    with gr.Tabs():
                        with gr.Tab("AI"):
                            ocr_form_disp = gr.Textbox(label="Form Type", interactive=False)
                            with gr.Row():
                                ocr_prov_disp = gr.Textbox(label="Province", interactive=False)
                                ocr_cons_disp = gr.Number(label="Constituency", interactive=False)
                                ocr_unit_disp = gr.Number(label="Unit", interactive=False)
                            with gr.Row():
                                ocr_total_disp = gr.Number(label="Total", interactive=False)
                                ocr_valid_disp = gr.Number(label="Valid", interactive=False)
                                ocr_invalid_disp = gr.Number(label="Invalid", interactive=False)
                                ocr_blank_disp = gr.Number(label="Blank", interactive=False)
                            ocr_votes_disp = gr.Dataframe(
                                headers=["No.", "Votes"],
                                datatype=["str", "number"],
                                label="Detected Votes",
                                interactive=False
                            )
                        with gr.Tab("ECT"):
                            ect_status_disp = gr.Textbox(label="ECT Status", interactive=False)
                            with gr.Row():
                                ect_total_disp = gr.Number(label="Total", interactive=False)
                                ect_valid_disp = gr.Number(label="Valid", interactive=False)
                                ect_invalid_disp = gr.Number(label="Invalid", interactive=False)
                                ect_blank_disp = gr.Number(label="Blank", interactive=False)
                            ect_votes_disp = gr.Dataframe(
                                headers=["No.", "Votes"],
                                datatype=["str", "number"],
                                label="ECT Aggregate Votes",
                                interactive=False
                            )
                        with gr.Tab("Vote62"):
                            vote62_status_disp = gr.Textbox(label="Vote62 Status", interactive=False)
                            with gr.Row():
                                vote62_total_disp = gr.Number(label="Total", interactive=False)
                                vote62_valid_disp = gr.Number(label="Valid", interactive=False)
                                vote62_invalid_disp = gr.Number(label="Invalid", interactive=False)
                                vote62_blank_disp = gr.Number(label="Blank", interactive=False)
                            vote62_votes_disp = gr.Dataframe(
                                headers=["No.", "Votes"],
                                datatype=["str", "number"],
                                label="Vote62 Votes",
                                interactive=False
                            )
                        with gr.Tab("Drive"):
                            drive_fetch_btn = gr.Button("Fetch from Open Chrome Drive Tab")
                            drive_status_disp = gr.Textbox(label="Drive Gemini Status", interactive=False)
                            drive_summary_disp = gr.Textbox(
                                label="Gemini Summary / Context",
                                interactive=False,
                                lines=8,
                                max_lines=16
                            )

        # Initial Load
        demo.load(
            fn=lambda: load_all_data(0),
            inputs=[],
            outputs=[
                image_display, filename_display, status_display, progress_display,
                score_comparison_disp, totals_comparison_disp,
                ocr_form_disp, ocr_prov_disp, ocr_cons_disp, ocr_unit_disp,
                ocr_total_disp, ocr_valid_disp, ocr_invalid_disp, ocr_blank_disp, ocr_votes_disp,
                ect_status_disp, ect_total_disp, ect_valid_disp, ect_invalid_disp, ect_blank_disp, ect_votes_disp,
                vote62_status_disp, vote62_total_disp, vote62_valid_disp, vote62_invalid_disp, vote62_blank_disp, vote62_votes_disp,
                drive_status_disp, drive_summary_disp,
                man_form_input, man_prov_input, man_cons_input, man_unit_input,
                man_total_input, man_valid_input, man_invalid_input, man_blank_input, man_votes_input,
                current_index, lock_state, override_new_entry_chk
            ]
        ).then(
            fn=_apply_mode_updates,
            inputs=[lock_state, override_new_entry_chk],
            outputs=[
                man_form_input, man_prov_input, man_cons_input, man_unit_input,
                man_total_input, man_valid_input, man_invalid_input, man_blank_input,
                page_mode_banner
            ]
        )
        
        # Events
        next_btn.click(
            fn=next_click,
            inputs=[
                current_index, filename_display, man_form_input, man_prov_input, man_cons_input, man_unit_input,
                man_total_input, man_valid_input, man_invalid_input, man_blank_input, man_votes_input,
                override_new_entry_chk
            ],
            outputs=[
                image_display, filename_display, status_display, progress_display,
                score_comparison_disp, totals_comparison_disp,
                ocr_form_disp, ocr_prov_disp, ocr_cons_disp, ocr_unit_disp,
                ocr_total_disp, ocr_valid_disp, ocr_invalid_disp, ocr_blank_disp, ocr_votes_disp,
                ect_status_disp, ect_total_disp, ect_valid_disp, ect_invalid_disp, ect_blank_disp, ect_votes_disp,
                vote62_status_disp, vote62_total_disp, vote62_valid_disp, vote62_invalid_disp, vote62_blank_disp, vote62_votes_disp,
                drive_status_disp, drive_summary_disp,
                man_form_input, man_prov_input, man_cons_input, man_unit_input,
                man_total_input, man_valid_input, man_invalid_input, man_blank_input, man_votes_input,
                current_index, lock_state, override_new_entry_chk
            ]
        ).then(
            fn=_apply_mode_updates,
            inputs=[lock_state, override_new_entry_chk],
            outputs=[
                man_form_input, man_prov_input, man_cons_input, man_unit_input,
                man_total_input, man_valid_input, man_invalid_input, man_blank_input,
                page_mode_banner
            ]
        )
        
        prev_btn.click(
            fn=prev_click,
            inputs=[
                current_index, filename_display, man_form_input, man_prov_input, man_cons_input, man_unit_input,
                man_total_input, man_valid_input, man_invalid_input, man_blank_input, man_votes_input,
                override_new_entry_chk
            ],
            outputs=[
                image_display, filename_display, status_display, progress_display,
                score_comparison_disp, totals_comparison_disp,
                ocr_form_disp, ocr_prov_disp, ocr_cons_disp, ocr_unit_disp,
                ocr_total_disp, ocr_valid_disp, ocr_invalid_disp, ocr_blank_disp, ocr_votes_disp,
                ect_status_disp, ect_total_disp, ect_valid_disp, ect_invalid_disp, ect_blank_disp, ect_votes_disp,
                vote62_status_disp, vote62_total_disp, vote62_valid_disp, vote62_invalid_disp, vote62_blank_disp, vote62_votes_disp,
                drive_status_disp, drive_summary_disp,
                man_form_input, man_prov_input, man_cons_input, man_unit_input,
                man_total_input, man_valid_input, man_invalid_input, man_blank_input, man_votes_input,
                current_index, lock_state, override_new_entry_chk
            ]
        ).then(
            fn=_apply_mode_updates,
            inputs=[lock_state, override_new_entry_chk],
            outputs=[
                man_form_input, man_prov_input, man_cons_input, man_unit_input,
                man_total_input, man_valid_input, man_invalid_input, man_blank_input,
                page_mode_banner
            ]
        )

        override_new_entry_chk.change(
            fn=_apply_mode_updates,
            inputs=[lock_state, override_new_entry_chk],
            outputs=[
                man_form_input, man_prov_input, man_cons_input, man_unit_input,
                man_total_input, man_valid_input, man_invalid_input, man_blank_input,
                page_mode_banner
            ]
        )

        # Auto-refresh vote template when keys change.
        man_form_input.change(
            fn=refresh_vote_template,
            inputs=[man_form_input, man_prov_input, man_cons_input, man_votes_input],
            outputs=[man_votes_input, status_display]
        )
        man_form_input.input(
            fn=refresh_vote_template,
            inputs=[man_form_input, man_prov_input, man_cons_input, man_votes_input],
            outputs=[man_votes_input, status_display]
        )
        man_prov_input.change(
            fn=refresh_vote_template,
            inputs=[man_form_input, man_prov_input, man_cons_input, man_votes_input],
            outputs=[man_votes_input, status_display]
        )
        man_prov_input.input(
            fn=refresh_vote_template,
            inputs=[man_form_input, man_prov_input, man_cons_input, man_votes_input],
            outputs=[man_votes_input, status_display]
        )
        man_cons_input.change(
            fn=refresh_vote_template,
            inputs=[man_form_input, man_prov_input, man_cons_input, man_votes_input],
            outputs=[man_votes_input, status_display]
        )
        man_cons_input.input(
            fn=refresh_vote_template,
            inputs=[man_form_input, man_prov_input, man_cons_input, man_votes_input],
            outputs=[man_votes_input, status_display]
        )
        refresh_template_btn.click(
            fn=refresh_vote_template,
            inputs=[man_form_input, man_prov_input, man_cons_input, man_votes_input],
            outputs=[man_votes_input, status_display]
        )
        man_total_input.change(
            fn=_totals_consistency_message,
            inputs=[man_total_input, man_valid_input, man_invalid_input, man_blank_input],
            outputs=[status_display]
        )
        man_valid_input.change(
            fn=_totals_consistency_message,
            inputs=[man_total_input, man_valid_input, man_invalid_input, man_blank_input],
            outputs=[status_display]
        )
        man_invalid_input.change(
            fn=_totals_consistency_message,
            inputs=[man_total_input, man_valid_input, man_invalid_input, man_blank_input],
            outputs=[status_display]
        )
        drive_fetch_btn.click(
            fn=fetch_drive_context_click,
            inputs=[],
            outputs=[drive_status_disp, drive_summary_disp]
        )
        man_blank_input.change(
            fn=_totals_consistency_message,
            inputs=[man_total_input, man_valid_input, man_invalid_input, man_blank_input],
            outputs=[status_display]
        )

    return demo

if __name__ == "__main__":
    print("Starting verifier...")
    demo = build_demo()
    demo.launch(server_name="0.0.0.0", server_port=7861)
