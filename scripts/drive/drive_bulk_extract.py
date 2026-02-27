#!/usr/bin/env python3
"""Bulk extract Gemini AI overviews from Google Drive files.

This script navigates through Drive folder hierarchies via CDP and extracts
Gemini summaries from each file, saving them to the mapping file for later use.

Usage:
    1. Start Chrome with remote debugging:
       /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
         --remote-debugging-port=9222 \
         --user-data-dir=/tmp/chrome-cdp

    2. Log in to Google Drive in that Chrome window

    3. Navigate to the root folder you want to extract from

    4. Run this script:
       ./venv/bin/python drive_bulk_extract.py --max-files 10

The script will:
    - List files in the current folder
    - Open each file, extract Gemini summary
    - Save to drive_file_mapping.json
    - Navigate back and continue to next file
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import time
import urllib.request
from typing import Any, Optional

from drive_mapping import upsert_mapping_entry, load_mapping, find_by_drive_id

DEFAULT_DEVTOOLS_URL = "http://127.0.0.1:9222/json"
DEFAULT_MAPPING_FILE = "drive_file_mapping.json"
PAGE_LOAD_DELAY = 3.0  # seconds to wait for page load
GEMINI_DELAY = 2.0  # seconds to wait for Gemini panel to load


def _fetch_targets(devtools_url: str) -> list[dict[str, Any]]:
    with urllib.request.urlopen(devtools_url, timeout=5) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if not isinstance(data, list):
        return []
    return [x for x in data if isinstance(x, dict)]


def _pick_drive_target(targets: list[dict[str, Any]], target_id: str | None = None) -> dict[str, Any] | None:
    if target_id:
        for t in targets:
            if t.get("id") == target_id:
                return t
        return None

    for t in targets:
        if t.get("type") != "page":
            continue
        url = str(t.get("url", ""))
        if "drive.google.com/file/d/" in url:
            return t
    for t in targets:
        if t.get("type") != "page":
            continue
        url = str(t.get("url", ""))
        if "drive.google.com/drive/folders/" in url:
            return t
    for t in targets:
        if t.get("type") != "page":
            continue
        url = str(t.get("url", ""))
        if "drive.google.com/" in url:
            return t
    return None


class CdpPage:
    def __init__(self, ws_url: str):
        self.ws_url = ws_url
        self._sock = None
        self._msg_id = 0

    async def __aenter__(self):
        import websockets
        self._sock = await websockets.connect(self.ws_url, max_size=20_000_000)
        await self.send("Runtime.enable")
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self._sock:
            await self._sock.close()

    async def send(self, method: str, params: dict | None = None) -> dict:
        self._msg_id += 1
        msg_id = self._msg_id
        payload = {"id": msg_id, "method": method, "params": params or {}}
        await self._sock.send(json.dumps(payload))
        while True:
            obj = json.loads(await self._sock.recv())
            if obj.get("id") == msg_id:
                return obj

    async def eval(self, expression: str):
        res = await self.send("Runtime.evaluate", {"expression": expression, "returnByValue": True})
        return res.get("result", {}).get("result", {}).get("value")

    async def get_url(self) -> str:
        return str(await self.eval("location.href") or "")

    async def get_title(self) -> str:
        return str(await self.eval("document.title") or "")

    async def get_page_text(self, max_chars: int = 50000) -> str:
        return str(await self.eval(f"document.body ? document.body.innerText.slice(0, {max_chars}) : ''") or "")

    async def navigate(self, url: str) -> None:
        await self.eval(f'location.href = "{url}"')


def _extract_gemini_summary(page_text: str) -> str:
    if not page_text:
        return ""
    marker = "Summary"
    start = page_text.find(marker)
    if start < 0:
        return ""
    tail = page_text[start + len(marker):].strip()
    stops = [
        "\nShow more",
        "\nList the main points for this file",
        "\nAsk a question about this file",
        "\nAsk Gemini",
        "\nGood suggestion",
        "\nBad suggestion",
    ]
    end = len(tail)
    for s in stops:
        pos = tail.find(s)
        if pos >= 0:
            end = min(end, pos)
    return tail[:end].strip()


def _extract_drive_file_id(url: str) -> str:
    match = re.search(r"/file/d/([0-9A-Za-z_-]{10,})", url or "")
    return match.group(1) if match else ""


def _extract_folder_id(url: str) -> str:
    match = re.search(r"/folders/([0-9A-Za-z_-]{10,})", url or "")
    return match.group(1) if match else ""


def _display_name_from_title(title: str, drive_id: str) -> str:
    clean = (title or "").strip()
    suffix = " - Google Drive"
    if clean.endswith(suffix):
        clean = clean[: -len(suffix)].strip()
    return clean or drive_id


async def _list_folder_items(ws_url: str) -> list[dict[str, Any]]:
    """List files and folders in current Drive folder view."""
    async with CdpPage(ws_url) as page:
        rows = await page.eval(
            """(() => {
              return [...document.querySelectorAll('tr[role="row"]')].slice(0, 500).map((r, idx) => {
                const id = r.getAttribute('data-id') || '';
                const name = (r.querySelector('strong.DNoYtb')?.innerText || r.querySelector('.DNoYtb')?.innerText || '').trim();
                const aria = (r.querySelector('.JxSEve[aria-label]')?.getAttribute('aria-label') || '').trim();
                const low = aria.toLowerCase();
                const isFolder = low.includes('folder');
                const isFile = !isFolder && (!!name || !!id);
                return {row: idx + 1, id, name, is_folder: isFolder, is_file: isFile};
              }).filter(x => x.id && x.name);
            })()"""
        )
        if not isinstance(rows, list):
            return []
        return rows


async def _extract_file_gemini(ws_url: str, drive_id: str) -> tuple[str, str, str]:
    """Extract Gemini summary from a file page. Returns (url, title, summary)."""
    async with CdpPage(ws_url) as page:
        url = await page.get_url()
        title = await page.get_title()
        await asyncio.sleep(GEMINI_DELAY)  # Wait for Gemini panel
        text = await page.get_page_text()
        summary = _extract_gemini_summary(text)
        return url, title, summary if summary else text[:15000]


async def bulk_extract(
    ws_url: str,
    max_files: int = 0,
    max_folders: int = 0,
    skip_existing: bool = True,
    mapping_path: str = DEFAULT_MAPPING_FILE,
    depth: int = 0,
    max_depth: int = 10,
    stats: Optional[dict] = None,
) -> dict:
    """Recursively extract Gemini summaries from Drive folder.

    Args:
        ws_url: CDP websocket URL
        max_files: Max files to extract (0 = unlimited)
        max_folders: Max folders to traverse (0 = unlimited)
        skip_existing: Skip files already in mapping
        mapping_path: Path to mapping JSON
        depth: Current recursion depth
        max_depth: Maximum folder depth
        stats: Accumulated statistics dict

    Returns:
        Statistics dict with counts
    """
    if stats is None:
        stats = {"files_extracted": 0, "files_skipped": 0, "folders_entered": 0, "errors": 0}

    if depth > max_depth:
        print(f"{'  ' * depth}Max depth reached, stopping recursion")
        return stats

    async with CdpPage(ws_url) as page:
        current_url = await page.get_url()
        folder_id = _extract_folder_id(current_url)

        print(f"{'  ' * depth}Listing folder: {folder_id[:20]}...")
        items = await _list_folder_items(ws_url)

        if not items:
            print(f"{'  ' * depth}No items found in this folder")
            return stats

        files = [i for i in items if i.get("is_file")]
        folders = [i for i in items if i.get("is_folder")]

        print(f"{'  ' * depth}Found {len(files)} files, {len(folders)} folders")

        # Process files first
        for item in files:
            if max_files and stats["files_extracted"] >= max_files:
                print(f"{'  ' * depth}Max files limit reached")
                return stats

            file_id = item.get("id", "")
            file_name = item.get("name", "")

            # Check if already extracted
            if skip_existing:
                existing = find_by_drive_id(file_id, mapping_path)
                if existing and existing.get("gemini_summary"):
                    print(f"{'  ' * depth}[SKIP] {file_name} (already in mapping)")
                    stats["files_skipped"] += 1
                    continue

            # Navigate to file
            file_url = f"https://drive.google.com/file/d/{file_id}/view"
            print(f"{'  ' * depth}[EXTRACT] {file_name}...")
            try:
                await page.navigate(file_url)
                await asyncio.sleep(PAGE_LOAD_DELAY)

                url, title, summary = await _extract_file_gemini(ws_url, file_id)

                if summary:
                    name = _display_name_from_title(title, file_id)
                    upsert_mapping_entry(
                        drive_id=file_id,
                        drive_url=url,
                        name=name,
                        gemini_summary=summary,
                        mapping_path=mapping_path,
                    )
                    print(f"{'  ' * depth}[SAVED] {file_name} ({len(summary)} chars)")
                    stats["files_extracted"] += 1
                else:
                    print(f"{'  ' * depth}[EMPTY] {file_name} (no Gemini summary)")
                    stats["files_skipped"] += 1

                # Navigate back to folder
                if folder_id:
                    await page.navigate(f"https://drive.google.com/drive/folders/{folder_id}")
                    await asyncio.sleep(1.5)

            except Exception as e:
                print(f"{'  ' * depth}[ERROR] {file_name}: {e}")
                stats["errors"] += 1
                # Try to navigate back
                try:
                    if folder_id:
                        await page.navigate(f"https://drive.google.com/drive/folders/{folder_id}")
                        await asyncio.sleep(1.5)
                except:
                    pass

        # Process folders recursively
        for item in folders:
            if max_folders and stats["folders_entered"] >= max_folders:
                print(f"{'  ' * depth}Max folders limit reached")
                return stats

            folder_name = item.get("name", "")
            subfolder_id = item.get("id", "")

            print(f"{'  ' * depth}[FOLDER] Entering: {folder_name}/")
            stats["folders_entered"] += 1

            try:
                await page.navigate(f"https://drive.google.com/drive/folders/{subfolder_id}")
                await asyncio.sleep(PAGE_LOAD_DELAY)

                stats = await bulk_extract(
                    ws_url,
                    max_files=max_files,
                    max_folders=max_folders,
                    skip_existing=skip_existing,
                    mapping_path=mapping_path,
                    depth=depth + 1,
                    max_depth=max_depth,
                    stats=stats,
                )

                # Navigate back
                if folder_id:
                    await page.navigate(f"https://drive.google.com/drive/folders/{folder_id}")
                    await asyncio.sleep(1.5)

            except Exception as e:
                print(f"{'  ' * depth}[ERROR] Folder {folder_name}: {e}")
                stats["errors"] += 1

        return stats


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Bulk extract Gemini AI overviews from Google Drive files"
    )
    parser.add_argument("--devtools-url", default=DEFAULT_DEVTOOLS_URL, help="Chrome DevTools URL")
    parser.add_argument("--target-id", default=None, help="Specific Chrome tab target ID")
    parser.add_argument("--mapping-file", default=DEFAULT_MAPPING_FILE, help="Mapping JSON path")
    parser.add_argument("--max-files", type=int, default=0, help="Max files to extract (0=unlimited)")
    parser.add_argument("--max-folders", type=int, default=0, help="Max folders to traverse (0=unlimited)")
    parser.add_argument("--max-depth", type=int, default=10, help="Max folder recursion depth")
    parser.add_argument(
        "--include-existing",
        action="store_true",
        help="Re-extract files already in mapping",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Just list what would be extracted without doing it",
    )
    args = parser.parse_args()

    try:
        targets = _fetch_targets(args.devtools_url)
    except Exception as e:
        print(f"ERROR: Cannot connect to Chrome DevTools: {e}")
        print("\nMake sure Chrome is running with:")
        print('  /Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome \\')
        print('    --remote-debugging-port=9222 \\')
        print('    --user-data-dir=/tmp/chrome-cdp')
        return 1

    target = _pick_drive_target(targets, args.target_id)
    if not target:
        print("ERROR: No Google Drive tab found.")
        print("Open a Drive folder in the Chrome window first.")
        return 1

    ws_url = target.get("webSocketDebuggerUrl")
    if not ws_url:
        print("ERROR: No websocket URL for target")
        return 1

    print(f"Using Chrome tab: {target.get('title', '')}")
    print(f"URL: {target.get('url', '')}")
    print(f"Mapping file: {args.mapping_file}")
    print(f"Max files: {args.max_files or 'unlimited'}")
    print(f"Max folders: {args.max_folders or 'unlimited'}")
    print(f"Max depth: {args.max_depth}")
    print(f"Skip existing: {not args.include_existing}")
    print()

    if args.dry_run:
        print("[DRY RUN] Would extract from current folder...")
        items = asyncio.run(_list_folder_items(str(ws_url)))
        for item in items[:20]:
            kind = "DIR" if item.get("is_folder") else "FILE"
            print(f"  [{kind}] {item.get('name', '')}")
        if len(items) > 20:
            print(f"  ... and {len(items) - 20} more items")
        return 0

    print("Starting bulk extraction...")
    print("=" * 60)

    stats = asyncio.run(
        bulk_extract(
            str(ws_url),
            max_files=args.max_files,
            max_folders=args.max_folders,
            skip_existing=not args.include_existing,
            mapping_path=args.mapping_file,
            max_depth=args.max_depth,
        )
    )

    print("=" * 60)
    print("Extraction complete!")
    print(f"  Files extracted: {stats['files_extracted']}")
    print(f"  Files skipped: {stats['files_skipped']}")
    print(f"  Folders entered: {stats['folders_entered']}")
    print(f"  Errors: {stats['errors']}")
    print(f"\nMapping saved to: {args.mapping_file}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
