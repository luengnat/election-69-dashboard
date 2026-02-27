#!/usr/bin/env python3
"""
Advanced segmentation utilities using visual landmarks.
"""

import cv2
import numpy as np
import os
from typing import Optional, Tuple

GARUDA_TEMPLATE_PATH = "assets/garuda_template.png"

def detect_garuda(image_path: str, threshold: float = 0.6) -> Optional[Tuple[int, int]]:
    """
    Detect the center (x, y) of the Garuda emblem in the image.
    Used for form separation and coordinate realignment.
    """
    if not os.path.exists(GARUDA_TEMPLATE_PATH):
        # Fallback if template missing
        return None
        
    img = cv2.imread(image_path, 0) # Grayscale
    template = cv2.imread(GARUDA_TEMPLATE_PATH, 0)
    
    if img is None or template is None:
        return None
        
    w, h = template.shape[::-1]
    
    # Check if image is smaller than template
    if img.shape[0] < h or img.shape[1] < w:
        return None

    # Match template
    res = cv2.matchTemplate(img, template, cv2.TM_CCOEFF_NORMED)
    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
    
    if max_val >= threshold:
        center_x = max_loc[0] + w // 2
        center_y = max_loc[1] + h // 2
        return (center_x, center_y)
        
    return None

def detect_dotted_lines(image_path: str) -> list:
    """
    Detect horizontal dotted lines to locate input fields.
    Returns list of bounding boxes (x, y, w, h) for detected lines, sorted by Y.
    """
    img = cv2.imread(image_path, 0)
    if img is None:
        return []
        
    # 1. Preprocess: adaptive threshold to handle varying illumination
    thresh = cv2.adaptiveThreshold(img, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                   cv2.THRESH_BINARY_INV, 11, 2)
    
    # 2. Morphological opening to isolate horizontal components
    # Dotted lines are a series of small horizontal segments.
    # We use a kernel that is wide enough to capture dots but small enough to not be confused with text.
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 1))
    detected_lines = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel, iterations=1)
    
    # 3. Use HoughLinesP to connect the dots
    lines = cv2.HoughLinesP(detected_lines, 1, np.pi/180, threshold=30, 
                            minLineLength=40, maxLineGap=20)
    
    found_boxes = []
    if lines is not None:
        for line in lines:
            x1, y1, x2, y2 = line[0]
            # Check if nearly horizontal
            if abs(y2 - y1) < 5:
                w = abs(x2 - x1)
                # Filter by width: dotted lines for numbers are usually 100-300px wide
                if 50 < w < 500:
                    found_boxes.append((min(x1, x2), min(y1, y2), w, 2))
                    
    # 4. Group lines that are too close (same line detected multiple times)
    if not found_boxes:
        return []
        
    found_boxes.sort(key=lambda b: b[1]) # Sort by Y
    
    unique_lines = [found_boxes[0]]
    for i in range(1, len(found_boxes)):
        last_y = unique_lines[-1][1]
        curr_y = found_boxes[i][1]
        if abs(curr_y - last_y) > 15: # 15px threshold for distinct lines
            unique_lines.append(found_boxes[i])
            
    return unique_lines


def split_pages_by_landmark(image_paths: list[str]) -> list[list[str]]:
    """
    Group images into units based on the start-of-form landmark (Garuda).
    
    Returns:
        List of lists, where each sub-list is an ordered set of pages for one unit.
    """
    if not image_paths:
        return []
        
    units = []
    current_unit = [image_paths[0]]
    
    # Iterate from second page onwards
    for i in range(1, len(image_paths)):
        path = image_paths[i]
        # Check for Garuda on this page
        # If found, it's the start of a NEW unit
        if detect_garuda(path):
            units.append(current_unit)
            current_unit = [path]
        else:
            # continuation of current unit
            current_unit.append(path)
            
    units.append(current_unit)
    return units


def extract_zonal_snippets(image_path: str, output_dir: str = "snippets") -> list:
    """
    Find dotted lines and extract the region ABOVE them.
    Returns list of snippet file paths.
    """
    lines = detect_dotted_lines(image_path)
    if not lines:
        return []
        
    img = cv2.imread(image_path)
    if img is None:
        return []
        
    os.makedirs(output_dir, exist_ok=True)
    snippet_paths = []
    
    h_img, w_img = img.shape[:2]
    
    for i, (x, y, w, h) in enumerate(lines):
        # Crop region above the line (where handwriting is)
        # Height: ~60-80 pixels is usually enough for a number
        # Width: Use the line width or a bit wider
        
        crop_h = 70
        y1 = max(0, y - crop_h)
        y2 = y + 5 # Include the line slightly for context
        x1 = max(0, x - 10)
        x2 = min(w_img, x + w + 10)
        
        snippet = img[y1:y2, x1:x2]
        
        # Save snippet
        filename = f"snippet_{os.path.basename(image_path)}_{i:02d}.png"
        path = os.path.join(output_dir, filename)
        cv2.imwrite(path, snippet)
        snippet_paths.append(path)
        
    return snippet_paths
