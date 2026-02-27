#!/usr/bin/env python3
"""
Download ballot images from ECT Google Drive folders.
Uses gdrivedl.py for public folder access (no auth required).
"""

import os
import sys
import argparse
import re
from pathlib import Path
from typing import Optional

from province_folders import get_all_provinces, get_drive_url


def find_pdf_files(directory: str) -> list[str]:
    """Find all PDF files in directory recursively."""
    pdfs = []
    for root, dirs, files in os.walk(directory):
        for f in files:
            if f.lower().endswith('.pdf'):
                pdfs.append(os.path.join(root, f))
    return sorted(pdfs)


def extract_metadata_from_path(file_path: str) -> dict:
    """Extract province, constituency, district from file path.

    Path structure example:
    ballots/Phrae/เขตเลือกตั้งที่ 1 จังหวัดแพร่/อําเภอสูงเม่น/ตําบลดอนมูล/หน่วยเลือกตั้งที่1/สส5ทับ18.pdf
    """
    metadata = {}

    # Extract constituency number
    cons_match = re.search(r'เขตเลือกตั้งที่\s*(\d+)', file_path)
    if cons_match:
        metadata['constituency_number'] = int(cons_match.group(1))

    # Extract district (อําเภอ)
    district_match = re.search(r'อําเภอ([^/]+)', file_path)
    if district_match:
        metadata['district'] = district_match.group(1).strip()

    # Extract subdistrict (ตําบล)
    subdist_match = re.search(r'ตําบล([^/]+)', file_path)
    if subdist_match:
        metadata['subdistrict'] = subdist_match.group(1).strip()

    # Extract polling unit (หน่วยเลือกตั้ง)
    unit_match = re.search(r'หน่วยเลือกตั้งที่\s*(\d+)', file_path)
    if unit_match:
        metadata['polling_unit'] = int(unit_match.group(1))

    # Extract form type from filename
    filename = os.path.basename(file_path)
    if '5ทับ18' in filename or '5/18' in filename:
        metadata['form_type'] = 'constituency'
    elif '5ทับ16' in filename or '5/16' in filename:
        metadata['form_type'] = 'constituency'
    elif '5ทับ17' in filename or '5/17' in filename:
        metadata['form_type'] = 'party_list'
    elif '(บช)' in filename:
        metadata['form_type'] = 'party_list'

    return metadata


def download_province_ballots(
    province_name: str,
    output_dir: str = "ballots",
    max_files: int = None,
    verbose: bool = False,
    dry_run: bool = False
):
    """Download ballot images for a specific province.

    Args:
        province_name: Province name (Thai or English)
        output_dir: Base output directory
        max_files: Maximum files to download (None = all)
        verbose: Enable verbose output
        dry_run: Just list what would be downloaded

    Returns:
        List of downloaded file paths
    """
    from gdrivedl import GDriveDL

    provinces = get_all_provinces()

    # Find province by name (Thai or English)
    province = None
    for p in provinces:
        if p["name_th"] == province_name or p["name_en"].lower() == province_name.lower():
            province = p
            break

    if not province:
        print(f"Province not found: {province_name}")
        print(f"Available provinces: {[p['name_en'] for p in provinces]}")
        return []

    folder_id = province["folder_id"]
    province_dir = os.path.join(output_dir, province["name_en"].replace(" ", "_"))

    print(f"\nDownloading ballots for {province['name_th']} ({province['name_en']})")
    print(f"Folder ID: {folder_id}")
    print(f"Output: {province_dir}")
    print(f"URL: {get_drive_url(folder_id)}")

    if dry_run:
        print("\n[DRY RUN] Would download from this folder")
        return []

    # Create output directory
    os.makedirs(province_dir, exist_ok=True)

    # Download using gdrivedl
    downloader = GDriveDL(
        quiet=False,
        overwrite=False,
        mtimes=True,
        continue_on_errors=True
    )

    url = get_drive_url(folder_id)
    downloader.process_url(url, province_dir, verbose=verbose)

    if downloader.errors:
        print(f"\nErrors encountered: {len(downloader.errors)}")
        for err in downloader.errors:
            print(f"  - {err}")

    # Find all downloaded PDFs
    pdfs = find_pdf_files(province_dir)
    print(f"\nDownloaded {len(pdfs)} PDF files to {province_dir}")

    # Limit if max_files specified
    if max_files and len(pdfs) > max_files:
        print(f"Note: Downloaded {len(pdfs)} files (max_files limit is for reference)")

    return pdfs


def download_sample_ballots(output_dir: str = "ballots", samples_per_province: int = 5, dry_run: bool = False):
    """Download sample ballots from a few test provinces.

    Downloads from:
    - Phrae (แพร่)
    - Chiang Mai (เชียงใหม่)
    - Sukhothai (สุโขทัย)
    """
    test_provinces = ["แพร่", "เชียงใหม่", "สุโขทัย"]
    all_downloaded = []

    for province in test_provinces:
        print(f"\n{'='*60}")
        downloaded = download_province_ballots(
            province,
            output_dir=output_dir,
            max_files=samples_per_province,
            dry_run=dry_run
        )
        all_downloaded.extend(downloaded)

    print(f"\n{'='*60}")
    print(f"Total downloaded: {len(all_downloaded)} files")

    return all_downloaded


def list_available_provinces():
    """List all available provinces with their Google Drive URLs."""
    provinces = get_all_provinces()

    print(f"\nTotal provinces: {len(provinces)}")
    print("\nAvailable provinces:")
    print("-" * 80)

    # Group by region
    regions = {}
    for p in provinces:
        region = p["region"]
        if region not in regions:
            regions[region] = []
        regions[region].append(p)

    region_names = {
        "north": "Northern Region (ภาคเหนือ)",
        "central": "Central Region (ภาคกลาง)",
        "northeast": "Northeastern Region (ภาคตะวันออกเฉียงเหนือ)",
        "east": "Eastern Region (ภาคตะวันออก)",
        "west": "Western Region (ภาคตะวันตก)",
        "south": "Southern Region (ภาคใต้)",
    }

    for region, provs in regions.items():
        print(f"\n{region_names.get(region, region)}:")
        for p in provs:
            print(f"  {p['name_th']} ({p['name_en']})")


def main():
    parser = argparse.ArgumentParser(
        description="Download ballot images from ECT Google Drive folders"
    )
    parser.add_argument(
        "province",
        nargs="?",
        help="Province name (Thai or English). Use 'all' for sample download."
    )
    parser.add_argument(
        "-o", "--output",
        default="ballots",
        help="Output directory (default: ballots)"
    )
    parser.add_argument(
        "-n", "--max-files",
        type=int,
        default=None,
        help="Maximum files to download per province (note: downloads full folder)"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all available provinces"
    )
    parser.add_argument(
        "--list-files",
        metavar="DIR",
        help="List PDF files in a directory"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be downloaded without downloading"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose output"
    )

    args = parser.parse_args()

    if args.list:
        list_available_provinces()
        return

    if args.list_files:
        pdfs = find_pdf_files(args.list_files)
        print(f"\nFound {len(pdfs)} PDF files in {args.list_files}:")
        for pdf in pdfs[:20]:
            print(f"  {pdf}")
            meta = extract_metadata_from_path(pdf)
            if meta:
                print(f"    Metadata: {meta}")
        if len(pdfs) > 20:
            print(f"  ... and {len(pdfs) - 20} more")
        return

    if not args.province:
        parser.print_help()
        print("\nExamples:")
        print("  python download_ballots.py --list")
        print("  python download_ballots.py แพร่")
        print("  python download_ballots.py Phrae -o my_ballots")
        print("  python download_ballots.py --list-files ballots/Phrae")
        print("  python download_ballots.py all  # Sample from 3 provinces")
        return

    if args.province.lower() == "all":
        download_sample_ballots(args.output, args.max_files or 5, dry_run=args.dry_run)
    else:
        download_province_ballots(
            args.province,
            output_dir=args.output,
            max_files=args.max_files,
            verbose=args.verbose,
            dry_run=args.dry_run
        )


if __name__ == "__main__":
    main()
