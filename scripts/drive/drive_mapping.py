#!/usr/bin/env python3
"""Drive file mapping utilities for local-path and Gemini-context lookup."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

DEFAULT_MAPPING_FILE = "drive_file_mapping.json"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _normalize_local_path(local_path: str) -> str:
    return str(Path(local_path).expanduser().resolve())


def load_mapping(mapping_path: str = DEFAULT_MAPPING_FILE) -> dict[str, Any]:
    path = Path(mapping_path)
    if not path.exists():
        return {"version": 1, "files": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "files": {}}
    if not isinstance(data, dict):
        return {"version": 1, "files": {}}
    if "files" not in data or not isinstance(data.get("files"), dict):
        data["files"] = {}
    if "version" not in data:
        data["version"] = 1
    return data


def save_mapping(data: dict[str, Any], mapping_path: str = DEFAULT_MAPPING_FILE) -> None:
    path = Path(mapping_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def upsert_mapping_entry(
    *,
    drive_id: str,
    drive_url: str,
    name: str,
    local_path: str | None = None,
    folder_path: list[str] | None = None,
    gemini_summary: str = "",
    gemini_raw_overview: str = "",
    mapping_path: str = DEFAULT_MAPPING_FILE,
) -> dict[str, Any]:
    data = load_mapping(mapping_path)
    files = data.setdefault("files", {})
    entry = files.get(drive_id, {})
    if not isinstance(entry, dict):
        entry = {}

    entry["drive_id"] = drive_id
    entry["drive_url"] = drive_url
    entry["name"] = name
    if local_path:
        entry["local_path"] = _normalize_local_path(local_path)
    elif "local_path" not in entry:
        entry["local_path"] = ""
    if folder_path is not None:
        entry["folder_path"] = [str(p).strip() for p in folder_path if str(p).strip()]
    elif "folder_path" not in entry:
        entry["folder_path"] = []
    if gemini_summary:
        entry["gemini_summary"] = gemini_summary
    elif "gemini_summary" not in entry:
        entry["gemini_summary"] = ""
    if gemini_raw_overview:
        entry["gemini_raw_overview"] = gemini_raw_overview
    elif "gemini_raw_overview" not in entry:
        entry["gemini_raw_overview"] = ""
    entry["gemini_fetched_at"] = _utc_now_iso()

    files[drive_id] = entry
    save_mapping(data, mapping_path)
    return entry


def find_by_drive_id(drive_id: str, mapping_path: str = DEFAULT_MAPPING_FILE) -> Optional[dict[str, Any]]:
    data = load_mapping(mapping_path)
    files = data.get("files", {})
    if not isinstance(files, dict):
        return None
    entry = files.get(drive_id)
    return entry if isinstance(entry, dict) else None


def find_by_local_path(local_path: str, mapping_path: str = DEFAULT_MAPPING_FILE) -> Optional[dict[str, Any]]:
    wanted = _normalize_local_path(local_path)
    data = load_mapping(mapping_path)
    files = data.get("files", {})
    if not isinstance(files, dict):
        return None
    for entry in files.values():
        if not isinstance(entry, dict):
            continue
        existing = entry.get("local_path")
        if not existing:
            continue
        try:
            existing_norm = _normalize_local_path(str(existing))
        except Exception:
            continue
        if existing_norm == wanted:
            return entry
    return None
