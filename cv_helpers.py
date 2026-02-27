import cv2
import numpy as np
import os
import tempfile
from pathlib import Path

def deskew_image(image_path: str, output_path: str = None) -> str:
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
            rho, theta = line[0]
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

def extract_vote_cells(cropped_image_path: str) -> list[str]:
    """Extract individual cells from the cropped vote column."""
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
    # We really just need the cells sorted by Y (row) and then X (column)
    if not cells:
        return []
        
    # Group into rows (y-tolerance)
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
    
    cell_paths = []
    for i, row in enumerate(rows):
        row.sort(key=lambda b: b[0]) # left to right
        for j, (x, y, w, h) in enumerate(row):
            cell_img = img[y:y+h, x:x+w]
            fd, p = tempfile.mkstemp(suffix=".png", prefix=f"cell_{i}_{j}_")
            os.close(fd)
            cv2.imwrite(p, cell_img)
            cell_paths.append(p)
            
    return cell_paths
