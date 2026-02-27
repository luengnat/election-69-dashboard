#!/usr/bin/env python3
"""Discover Google Drive files for a list of Thai province+constituency targets."""

from __future__ import annotations

import argparse
import json
import re
import urllib.request
from pathlib import Path
from typing import Any

from drive_cdp_browser import PUBLIC_FOLDER_URL, PUBLIC_ITEM_RE, _discover_files_public, _is_folder_url, _url_to_drive_id
from province_folders import get_all_provinces


_THAI_DIGITS_TABLE = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")


def _norm_digits(text: str) -> str:
    return (text or "").translate(_THAI_DIGITS_TABLE)


def _province_folder_map() -> dict[str, str]:
    return {str(p["name_th"]): str(p["folder_id"]) for p in get_all_provinces()}


def _find_constituency_folder(root_folder_id: str, constituency: int, timeout: int = 20) -> tuple[str, str]:
    url = PUBLIC_FOLDER_URL.format(id=root_folder_id)
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        html = resp.read().decode("utf-8", errors="ignore")
    for item_url, item_name, _modified in re.findall(PUBLIC_ITEM_RE, html):
        if not _is_folder_url(item_url):
            continue
        name = str(item_name).strip()
        m = re.search(r"เขตเลือกตั้งที่\s*(\d+)", _norm_digits(name))
        if m and int(m.group(1)) == constituency:
            return _url_to_drive_id(item_url), name
    return "", ""


def _read_locations(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict) and isinstance(payload.get("items"), list):
        return [x for x in payload["items"] if isinstance(x, dict)]
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description="Discover Drive files for province+constituency targets")
    parser.add_argument("--locations-json", default="drive2_locations.json")
    parser.add_argument("--out-json", default="drive2_discovery.json")
    parser.add_argument("--out-files-json", default="drive2_target_files.json")
    parser.add_argument(
        "--max-files-per-location",
        type=int,
        default=300,
        help="Safety cap for discovered files within each constituency folder (0 = unlimited)",
    )
    args = parser.parse_args()

    locations_path = Path(args.locations_json)
    out_json = Path(args.out_json)
    out_files_json = Path(args.out_files_json)

    targets = _read_locations(locations_path)
    if not targets:
        print(f"ERROR: no targets in {locations_path}")
        return 1

    prov_map = _province_folder_map()
    rows: list[dict[str, Any]] = []
    flat_files: list[dict[str, Any]] = []

    for idx, loc in enumerate(targets, start=1):
        province = str(loc.get("province", "")).strip()
        constituency = int(loc.get("constituency_number", 0) or 0)
        print(f"[{idx}/{len(targets)}] discover {province} เขต {constituency} ...", flush=True)

        root_id = prov_map.get(province, "")
        if not root_id:
            rows.append(
                {
                    "province": province,
                    "constituency_number": constituency,
                    "ok": False,
                    "reason": "province_not_found",
                }
            )
            continue

        try:
            cons_folder_id, cons_folder_name = _find_constituency_folder(root_id, constituency)
        except Exception as exc:
            rows.append(
                {
                    "province": province,
                    "constituency_number": constituency,
                    "ok": False,
                    "reason": f"root_fetch_error: {exc}",
                }
            )
            continue

        if not cons_folder_id:
            rows.append(
                {
                    "province": province,
                    "constituency_number": constituency,
                    "ok": False,
                    "reason": "constituency_folder_not_found",
                }
            )
            continue

        try:
            files = _discover_files_public(cons_folder_id, limit=max(0, args.max_files_per_location))
        except Exception as exc:
            rows.append(
                {
                    "province": province,
                    "constituency_number": constituency,
                    "ok": False,
                    "reason": f"discover_error: {exc}",
                    "constituency_folder_id": cons_folder_id,
                    "constituency_folder_name": cons_folder_name,
                }
            )
            continue

        rows.append(
            {
                "province": province,
                "constituency_number": constituency,
                "ok": True,
                "constituency_folder_id": cons_folder_id,
                "constituency_folder_name": cons_folder_name,
                "file_count": len(files),
                "files": files,
            }
        )
        for f in files:
            flat_files.append(
                {
                    "province": province,
                    "constituency_number": constituency,
                    "drive_id": str(f.get("drive_id", "")),
                    "name": str(f.get("name", "")),
                    "drive_url": str(f.get("drive_url", "")),
                    "folder_path": f.get("folder_path", []),
                }
            )
        print(f"  -> files={len(files)}", flush=True)

    out_json.write_text(json.dumps({"count": len(rows), "items": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    out_files_json.write_text(
        json.dumps({"count": len(flat_files), "files": flat_files}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"done: locations={len(rows)} ok={sum(1 for r in rows if r.get('ok'))} files={len(flat_files)}")
    print(f"wrote: {out_json}")
    print(f"wrote: {out_files_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
