#!/usr/bin/env python3
"""
Extract Garuda emblem from a ballot image to use as a template.
"""

import cv2
import os

IMAGE_PATH = "test_images/page-1.png"
OUTPUT_DIR = "assets"
OUTPUT_PATH = os.path.join(OUTPUT_DIR, "garuda_template.png")

def extract_garuda():
    if not os.path.exists(IMAGE_PATH):
        print(f"Image not found: {IMAGE_PATH}")
        return

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    img = cv2.imread(IMAGE_PATH)
    if img is None:
        print("Failed to load image")
        return
        
    h, w = img.shape[:2]
    
    # Garuda is typically in the top center
    # Estimates for page-1.png (approx 1240x1755)
    # Center X ~ 620
    # Top Y ~ 50-100
    # Size approx 150x150
    
    # Let's crop a generous region first to inspect, or just try to hit it
    # Center +/- 100px, Top 2% to 15%
    
    x1 = int(w * 0.42)
    x2 = int(w * 0.58)
    y1 = int(h * 0.02)
    y2 = int(h * 0.12)
    
    crop = img[y1:y2, x1:x2]
    
    cv2.imwrite(OUTPUT_PATH, crop)
    print(f"Saved candidate Garuda template to {OUTPUT_PATH}")
    print(f"Region: x={x1}-{x2}, y={y1}-{y2}")

if __name__ == "__main__":
    extract_garuda()
