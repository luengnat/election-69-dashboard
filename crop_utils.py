#!/usr/bin/env python3
"""
Form-aware image cropping and path-based form type detection.

Reduces AI cost by ~70% by sending only the vote-count column and summary
section to the model instead of full pages.

Key insight: The ได้คะแนน (vote count) column occupies the rightmost ~32% of
every page. Candidate/party names occupy the middle 55% — we don't need them
because ECT provides names by position.
"""

import os
import tempfile
from pathlib import Path
from typing import Optional

from ballot_types import FormType

# ---------------------------------------------------------------------------
# Crop region definitions (left, top, right, bottom) as fractions of page
# ---------------------------------------------------------------------------
CROP_REGIONS = {
    # Top-right box containing "ก.ส. ๕/๑๘" form code
    "form_code":              (0.76, 0.02, 1.00, 0.09),
    # Valid/invalid/blank ballot counts (first page only, mid-page)
    "summary":                (0.45, 0.28, 1.00, 0.58),
    # ได้คะแนน column: constituency first page (candidates start ~55% down)
    "vote_numbers":           (0.66, 0.55, 1.00, 0.97),
    # ได้คะแนน column: page 2+ where table fills whole page
    "vote_numbers_continuation": (0.66, 0.03, 1.00, 0.97),
}

# Path signals that unambiguously identify a form type (checked in order)
_PATH_SIGNALS: list[tuple[list[str], FormType]] = [
    # Party-list variants (check (บช) first so it takes priority)
    (["(บช)", "ล่วงหน้าในเขต"],  FormType.S5_16_BCH),
    (["(บช)", "ล่วงหน้านอกเขต"], FormType.S5_17_BCH),
    (["(บช)", "ชุดที่"],          FormType.S5_17_BCH),
    (["(บช)", "หน่วยเลือกตั้ง"], FormType.S5_18_BCH),
    (["(บช)", "5ทับ16"],          FormType.S5_16_BCH),
    (["(บช)", "5/16"],            FormType.S5_16_BCH),
    (["(บช)", "5ทับ17"],          FormType.S5_17_BCH),
    (["(บช)", "5/17"],            FormType.S5_17_BCH),
    (["(บช)", "5ทับ18"],          FormType.S5_18_BCH),
    (["(บช)", "5/18"],            FormType.S5_18_BCH),
    # Constituency variants
    (["ล่วงหน้าในเขต"],           FormType.S5_16),
    (["5ทับ16"],                  FormType.S5_16),
    (["5/16"],                    FormType.S5_16),
    (["ล่วงหน้านอกเขต"],          FormType.S5_17),
    (["ชุดที่"],                   FormType.S5_17),
    (["5ทับ17"],                  FormType.S5_17),
    (["5/17"],                    FormType.S5_17),
    (["หน่วยเลือกตั้ง"],          FormType.S5_18),
    (["5ทับ18"],                  FormType.S5_18),
    (["5/18"],                    FormType.S5_18),
]


def detect_form_type_from_path(file_path: str) -> Optional[FormType]:
    """
    Infer FormType from path/filename signals without any AI call.

    Checks path components and filename for known Thai text patterns.
    Returns None if the path is ambiguous (caller should fall back to AI).
    """
    # Combine full path for searching
    combined = file_path.replace("\\", "/")

    for signals, form_type in _PATH_SIGNALS:
        if all(sig in combined for sig in signals):
            return form_type

    return None


def crop_page_image(
    image_path: str,
    region: tuple[float, float, float, float],
    output_path: Optional[str] = None,
) -> str:
    """
    Crop a page image to the given region (fractions of width/height).

    Args:
        image_path: Path to the source PNG/JPEG image.
        region: (left, top, right, bottom) as fractions 0.0–1.0.
        output_path: Where to save the crop. If None, a temp file is created.

    Returns:
        Path to the cropped image file.

    Raises:
        ImportError: If Pillow is not installed.
        FileNotFoundError: If image_path does not exist.
    """
    try:
        from PIL import Image
    except ImportError:
        raise ImportError("Pillow is required for cropping. Install with: pip install Pillow")

    if not os.path.isfile(image_path):
        raise FileNotFoundError(f"Image not found: {image_path}")

    left_frac, top_frac, right_frac, bottom_frac = region

    with Image.open(image_path) as img:
        w, h = img.size
        box = (
            int(w * left_frac),
            int(h * top_frac),
            int(w * right_frac),
            int(h * bottom_frac),
        )
        cropped = img.crop(box)

        if output_path is None:
            suffix = Path(image_path).suffix or ".png"
            fd, output_path = tempfile.mkstemp(suffix=suffix, prefix="ballot_crop_")
            os.close(fd)

        cropped.save(output_path)

    return output_path


def get_crops_for_ballot(
    image_paths: list[str],
    form_type: FormType,
) -> dict[str, list[str]]:
    """
    Produce focused crops for a ballot's image list.

    Args:
        image_paths: Ordered list of page images (page 1 first).
        form_type: The detected form type.

    Returns:
        Dict with keys:
          "summary"      → [path to summary crop from page 1]
          "vote_numbers" → [path per page, cropped to vote-count column]

    All returned paths are temp files; callers are responsible for cleanup.
    """
    result: dict[str, list[str]] = {"summary": [], "vote_numbers": []}

    if not image_paths:
        return result

    # Summary crop: first page only
    try:
        summary_crop = crop_page_image(image_paths[0], CROP_REGIONS["summary"])
        result["summary"].append(summary_crop)
    except Exception:
        pass  # Non-fatal: fall back to full-page extraction

    # Vote-numbers crops: each page
    for i, page_path in enumerate(image_paths):
        region_key = "vote_numbers" if i == 0 else "vote_numbers_continuation"
        try:
            vote_crop = crop_page_image(page_path, CROP_REGIONS[region_key])
            result["vote_numbers"].append(vote_crop)
        except Exception:
            pass  # Non-fatal: fall back to full-page extraction

    return result
