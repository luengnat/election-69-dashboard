#!/usr/bin/env python3
"""Download and archive ECT JSON endpoints used by this project."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from ect_api import ECT_ENDPOINTS


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _dest_rel_path(url: str) -> Path:
    parsed = urlparse(url)
    host = parsed.netloc
    path = parsed.path.lstrip("/")
    return Path(host) / Path(path)


def _download(url: str, timeout: int = 60) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return resp.read()


def snapshot_ect_data(base_dir: Path) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%SZ")
    out_dir = base_dir / f"ect_snapshot_{ts}"
    out_dir.mkdir(parents=True, exist_ok=False)

    manifest: dict = {
        "snapshot_utc": datetime.now(timezone.utc).isoformat(),
        "source": "ECT endpoints used in ect_api.ECT_ENDPOINTS",
        "files": [],
    }

    for key, url in ECT_ENDPOINTS.items():
        rel = _dest_rel_path(url)
        dest = out_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)

        print(f"Downloading [{key}] {url}")
        data = _download(url)
        dest.write_bytes(data)

        entry = {
            "key": key,
            "url": url,
            "path": str(rel),
            "bytes": len(data),
            "sha256": _sha256_bytes(data),
        }

        # Validate JSON parse and record top-level shape.
        parsed = json.loads(data.decode("utf-8"))
        if isinstance(parsed, list):
            entry["json_type"] = "list"
            entry["json_len"] = len(parsed)
        elif isinstance(parsed, dict):
            entry["json_type"] = "dict"
            entry["json_keys"] = sorted(list(parsed.keys()))[:20]
        else:
            entry["json_type"] = type(parsed).__name__

        manifest["files"].append(entry)

    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    latest = base_dir / "ect_snapshot_latest"
    if latest.exists() or latest.is_symlink():
        if latest.is_symlink() or latest.is_file():
            latest.unlink()
        else:
            shutil.rmtree(latest)
    shutil.copytree(out_dir, latest)

    print(f"Snapshot saved to: {out_dir}")
    print(f"Latest copy updated: {latest}")
    return out_dir


def main() -> int:
    parser = argparse.ArgumentParser(description="Download ECT JSON snapshot")
    parser.add_argument(
        "--out",
        default="data/ect_snapshots",
        help="Base output directory for snapshots (default: data/ect_snapshots)",
    )
    args = parser.parse_args()

    out_path = Path(args.out).resolve()
    out_path.mkdir(parents=True, exist_ok=True)
    snapshot_ect_data(out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
