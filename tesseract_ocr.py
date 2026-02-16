#!/usr/bin/env python3
"""
Try Tesseract OCR for Thai ballot forms.
"""

import pytesseract
from PIL import Image
import re

def extract_text(image_path: str, lang: str = "tha+eng") -> str:
    """Extract text from image using Tesseract."""
    img = Image.open(image_path)
    text = pytesseract.image_to_string(img, lang=lang)
    return text

def extract_numbers(image_path: str) -> list[int]:
    """Extract all numbers from image."""
    text = extract_text(image_path)
    numbers = re.findall(r'\b\d+\b', text)
    return [int(n) for n in numbers]

def main():
    import sys
    image_path = sys.argv[1] if len(sys.argv) > 1 else "test_images/high_res_page-1.png"

    print(f"Processing: {image_path}")
    print("\n=== Full OCR Text ===")
    text = extract_text(image_path)
    print(text)

    print("\n=== Extracted Numbers ===")
    numbers = extract_numbers(image_path)
    print(numbers)

if __name__ == "__main__":
    main()
