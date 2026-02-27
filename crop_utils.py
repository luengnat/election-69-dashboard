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
import shutil
from pathlib import Path
from typing import Optional
from dataclasses import dataclass
import cv2
import numpy as np

from ballot_types import FormType
from config import config

# ---------------------------------------------------------------------------
# Crop region definitions (left, top, right, bottom) as fractions of page
# ---------------------------------------------------------------------------

@dataclass
class FormCropTemplate:
    """Defines crop regions for a specific form type layout."""
    form_code: tuple[float, float, float, float]
    summary: tuple[float, float, float, float]
    vote_numbers_p1: tuple[float, float, float, float]  # Page 1
    vote_numbers_cont: tuple[float, float, float, float]  # Page 2+

# Default regions (Constituency forms)
# Candidates start ~55% down on page 1
_DEFAULT_TEMPLATE = FormCropTemplate(
    form_code=(0.76, 0.02, 1.00, 0.09),
    summary=(0.45, 0.28, 1.00, 0.58),
    vote_numbers_p1=(0.66, 0.55, 1.00, 0.97),
    vote_numbers_cont=(0.66, 0.03, 1.00, 0.97),
)

# Party-List regions (Forms with (บช))
# Table starts much higher (~25% down) to fit 20+ parties per page
_PARTY_LIST_TEMPLATE = FormCropTemplate(
    form_code=(0.76, 0.02, 1.00, 0.09),
    summary=(0.45, 0.28, 1.00, 0.58),  # Summary is usually on last page, might need adjustment
    vote_numbers_p1=(0.66, 0.25, 1.00, 0.97),
    vote_numbers_cont=(0.66, 0.03, 1.00, 0.97),
)

FORM_TEMPLATES: dict[FormType, FormCropTemplate] = {
    # Constituency
    FormType.S5_16: _DEFAULT_TEMPLATE,
    FormType.S5_17: _DEFAULT_TEMPLATE,
    FormType.S5_18: _DEFAULT_TEMPLATE,
    # Party-List
    FormType.S5_16_BCH: _PARTY_LIST_TEMPLATE,
    FormType.S5_17_BCH: _PARTY_LIST_TEMPLATE,
    FormType.S5_18_BCH: _PARTY_LIST_TEMPLATE,
}

# For backward compatibility / generic access
CROP_REGIONS = {
    "form_code": _DEFAULT_TEMPLATE.form_code,
    "summary": _DEFAULT_TEMPLATE.summary,
    "vote_numbers": _DEFAULT_TEMPLATE.vote_numbers_p1,
    "vote_numbers_continuation": _DEFAULT_TEMPLATE.vote_numbers_cont,
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

    # Select template based on form type
    template = FORM_TEMPLATES.get(form_type, _DEFAULT_TEMPLATE)

    # Summary crop: first page only
    try:
        summary_crop = crop_page_image(image_paths[0], template.summary)
        result["summary"].append(summary_crop)
    except Exception:
        pass  # Non-fatal: fall back to full-page extraction

    # Vote-numbers crops: each page
    for i, page_path in enumerate(image_paths):
        # Page 1 uses vote_numbers_p1, Page 2+ uses vote_numbers_cont
        region = template.vote_numbers_p1 if i == 0 else template.vote_numbers_cont
        try:
            vote_crop = crop_page_image(page_path, region)
            result["vote_numbers"].append(vote_crop)
        except Exception:
            pass  # Non-fatal: fall back to full-page extraction



def deskew_image(image_path: str, output_path: Optional[str] = None) -> str:
    """Detects table boundaries and deskews the image."""
    img = cv2.imread(image_path)
    if img is None:
        return image_path
        
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)
    
    # Detect lines
    lines = cv2.HoughLines(edges, 1, np.pi / 180, 200)
    
    angles = []
    if lines is not None:
        for line in lines:
            _, theta = line[0]
            angle = np.degrees(theta)
            # Only consider near-horizontal lines
            if 80 < angle < 100:
                angles.append(angle - 90)
                
    if not angles:
        return image_path
        
    median_angle = np.median(angles)
    
    if abs(median_angle) < 0.5:
        return image_path # Too small to matter
        
    (h, w) = img.shape[:2]
    center = (w // 2, h // 2)
    M = cv2.getRotationMatrix2D(center, median_angle, 1.0)
    rotated = cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    
    if output_path is None:
        fd, output_path = tempfile.mkstemp(suffix=".png", prefix="deskewed_")
        os.close(fd)
        
    cv2.imwrite(output_path, rotated)
    return output_path

def extract_vote_cells(cropped_image_path: str) -> list[list[str]]:
    """Extract individual cells from the deskewed cropped vote column.
    Returns a list of rows, where each row is a list of cell image paths (left to right).
    """
    img = cv2.imread(cropped_image_path)
    if img is None:
        return []
        
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 15, 5)
    
    # Detect horizontal lines
    h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (40, 1))
    horizontal_lines = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, h_kernel, iterations=2)
    
    # Detect vertical lines
    v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 40))
    vertical_lines = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, v_kernel, iterations=2)
    
    # Combine
    table_mask = cv2.addWeighted(horizontal_lines, 0.5, vertical_lines, 0.5, 0.0)
    _, table_mask = cv2.threshold(table_mask, 50, 255, cv2.THRESH_BINARY)
    
    # Find contours
    contours, _ = cv2.findContours(table_mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    
    cells = []
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        if 20 < h < 100 and 30 < w < 800: # Filter typical cell sizes
            cells.append((x, y, w, h))
            
    # Sort left-to-right, top-to-bottom
    if not cells:
        return []
        
    cells.sort(key=lambda b: b[1])
    rows = []
    current_row = [cells[0]]
    for cell in cells[1:]:
        if abs(cell[1] - current_row[-1][1]) < 15:
            current_row.append(cell)
        else:
            rows.append(current_row)
            current_row = [cell]
    rows.append(current_row)
    
    cell_paths_by_row = []
    for i, row in enumerate(rows):
        row.sort(key=lambda b: b[0]) # left to right
        row_paths = []
        for j, (x, y, w, h) in enumerate(row):
            cell_img = img[y:y+h, x:x+w]
            fd, p = tempfile.mkstemp(suffix=".png", prefix=f"cell_{i}_{j}_")
            os.close(fd)
            cv2.imwrite(p, cell_img)
            row_paths.append(p)
        if row_paths:
            cell_paths_by_row.append(row_paths)
            
    return cell_paths_by_row

def save_crop_persistently(temp_path: str, source_filename: str, region_name: str) -> str:
    """
    Copy a temporary crop to a persistent directory for visual provenance.
    
    Args:
        temp_path: Path to the temporary crop file
        source_filename: Name of the original source file (used to group crops)
        region_name: Descriptive name for the region (e.g., 'vote_column', 'summary')
        
    Returns:
        Path to the persistent crop file.
    """
    if not temp_path or not os.path.exists(temp_path):
        return ""
        
    # Group crops by source filename (without extension)
    group_id = Path(source_filename).stem
    target_dir = Path(config.crops_dir) / group_id
    target_dir.mkdir(parents=True, exist_ok=True)
    
    extension = Path(temp_path).suffix or ".png"
    target_path = target_dir / f"{region_name}{extension}"
    
    try:
        shutil.copy2(temp_path, target_path)
        return str(target_path)
    except Exception as e:
        print(f"Error saving persistent crop: {e}")
        return temp_path
