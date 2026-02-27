#!/usr/bin/env python3
"""
Batch generate side-by-side OCR visualizations for all test images.
"""

import os
import subprocess
from pathlib import Path

# Directory to save previews
OUTPUT_DIR = "verification_previews"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Test images to process
TEST_IMAGES = [
    "test_images/page-1.png",
    "test_images/page-2.png",
    "test_images/high_res_page-1.png",
    "test_images/bch_page-1.png",
    "test_images/bch_page-2.png",
    "test_images/bch_page-3.png",
    "test_images/bch_page-4.png",
]

def generate_previews():
    print(f"Generating previews in {OUTPUT_DIR}...")
    
    for img_path in TEST_IMAGES:
        if not os.path.exists(img_path):
            print(f"Skipping {img_path} (not found)")
            continue
            
        filename = Path(img_path).stem
        output_path = os.path.join(OUTPUT_DIR, f"{filename}_preview.jpg")
        
        print(f"Generating preview for {img_path}...")
        try:
            # Call visualize_ocr.py
            cmd = ["python3", "visualize_ocr.py", img_path, output_path]
            subprocess.run(cmd, check=True)
        except Exception as e:
            print(f"Failed to generate preview for {img_path}: {e}")

    print("\nBatch generation complete.")
    print(f"Files available in ./{OUTPUT_DIR}/")

if __name__ == "__main__":
    generate_previews()
