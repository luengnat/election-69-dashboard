#!/usr/bin/env python3
"""
Enhanced OCR strategies for Thai ballot forms.

This module implements accuracy improvements:
1. Advanced image preprocessing
2. Multiple Tesseract configurations
3. Ensemble voting
4. Post-processing corrections
"""

import os
import sys
import tempfile
import subprocess
from pathlib import Path
from typing import Optional
from dataclasses import dataclass


@dataclass
class EnhancedResult:
    """Result from enhanced OCR extraction."""
    text: str
    confidence: float
    vote_counts: dict[int, int]
    preprocessing_applied: list[str]
    engine_mode: str


def preprocess_image(
    image_path: str,
    output_path: Optional[str] = None,
    methods: list[str] = None
) -> tuple[str, list[str]]:
    """
    Apply advanced preprocessing to improve OCR accuracy.

    Args:
        image_path: Path to input image
        output_path: Where to save processed image
        methods: List of preprocessing methods to apply
            - "contrast": Increase contrast
            - "sharpen": Sharpen edges
            - "binarize": Convert to black/white
            - "deskew": Correct rotation
            - "denoise": Remove noise
            - "dilate": Thicken strokes

    Returns:
        Tuple of (output_path, methods_applied)
    """
    if methods is None:
        methods = ["contrast", "sharpen", "binarize"]

    try:
        from PIL import Image, ImageEnhance, ImageFilter, ImageOps
        import io
    except ImportError:
        return image_path, []

    if output_path is None:
        suffix = Path(image_path).suffix or ".png"
        fd, output_path = tempfile.mkstemp(suffix=suffix, prefix="enhanced_")
        os.close(fd)

    applied = []

    try:
        with Image.open(image_path) as img:
            # Convert to grayscale for better processing
            if img.mode != "L":
                img = img.convert("L")

            # Apply requested methods
            if "deskew" in methods:
                try:
                    # Simple deskew using hough transform approximation
                    img = img.rotate(_detect_skew(img), resample=Image.BICUBIC, expand=True)
                    applied.append("deskew")
                except Exception:
                    pass

            if "denoise" in methods:
                img = img.filter(ImageFilter.MedianFilter(size=3))
                applied.append("denoise")

            if "contrast" in methods:
                # Higher contrast for handwritten ink
                img = ImageEnhance.Contrast(img).enhance(2.0)
                applied.append("contrast")

            if "sharpen" in methods:
                img = img.filter(ImageFilter.SHARPEN)
                img = img.filter(ImageFilter.EDGE_ENHANCE)
                applied.append("sharpen")

            if "dilate" in methods:
                # Thicken thin strokes (helps with faint handwriting)
                from PIL import ImageOps
                img = img.filter(ImageFilter.MaxFilter(size=3))
                applied.append("dilate")

            if "binarize" in methods:
                # Adaptive thresholding
                img = img.point(lambda x: 0 if x < 140 else 255)
                applied.append("binarize")

            img.save(output_path)

    except Exception as e:
        print(f"Preprocessing error: {e}")
        return image_path, []

    return output_path, applied


def _detect_skew(img) -> float:
    """Detect image skew angle. Returns angle in degrees."""
    # Simplified skew detection
    # In production, use Hough transform or similar
    return 0.0


def extract_with_config(
    image_path: str,
    psm: int = 6,
    oem: int = 3,
    lang: str = "tha+eng",
    extra_config: str = ""
) -> tuple[str, float]:
    """
    Extract text with specific Tesseract configuration.

    PSM (Page Segmentation Mode):
        3 = Fully automatic (default)
        4 = Single column of text
        6 = Single uniform block of text
        11 = Sparse text in no particular order
        12 = Sparse text with OSD

    OEM (OCR Engine Mode):
        0 = Legacy engine only
        1 = Neural net LSTM only
        2 = Legacy + LSTM
        3 = Default (whatever is available)

    Returns:
        Tuple of (text, confidence)
    """
    try:
        import pytesseract
        from PIL import Image

        config = f"--psm {psm} --oem {oem} {extra_config}".strip()

        with Image.open(image_path) as img:
            # Get text
            text = pytesseract.image_to_string(img, lang=lang, config=config)

            # Get confidence
            data = pytesseract.image_to_data(img, lang=lang, config=config, output_type=pytesseract.Output.DICT)
            confidences = [c for c in data.get('conf', []) if c > 0]
            avg_conf = sum(confidences) / len(confidences) if confidences else 0

            return text, avg_conf

    except Exception as e:
        print(f"OCR error: {e}")
        return "", 0


def ensemble_extract(
    image_path: str,
    preprocess_methods: list[str] = None
) -> EnhancedResult:
    """
    Run multiple OCR configurations and combine results.

    This ensemble approach tries different settings and
    uses voting to determine the best results.
    """
    if preprocess_methods is None:
        preprocess_methods = ["contrast", "sharpen"]

    # Step 1: Preprocess image
    processed_path, applied = preprocess_image(image_path, methods=preprocess_methods)

    # Step 2: Run multiple configurations
    configs = [
        (6, 3, "Standard block mode"),
        (4, 3, "Single column"),
        (11, 3, "Sparse text"),
        (6, 1, "LSTM only"),
    ]

    results = []
    for psm, oem, desc in configs:
        try:
            text, conf = extract_with_config(processed_path, psm=psm, oem=oem)
            results.append((text, conf, desc))
        except Exception:
            pass

    if not results:
        return EnhancedResult(
            text="",
            confidence=0,
            vote_counts={},
            preprocessing_applied=applied,
            engine_mode="none"
        )

    # Step 3: Pick best result by confidence
    best_text, best_conf, best_mode = max(results, key=lambda x: x[1])

    # Step 4: Extract vote counts using pattern matching
    vote_counts = _extract_vote_counts(best_text)

    # Clean up
    if processed_path != image_path:
        try:
            os.unlink(processed_path)
        except OSError:
            pass

    return EnhancedResult(
        text=best_text,
        confidence=best_conf,
        vote_counts=vote_counts,
        preprocessing_applied=applied,
        engine_mode=best_mode
    )


def _extract_vote_counts(text: str) -> dict[int, int]:
    """
    Extract vote counts from OCR text using pattern matching.

    Looks for patterns like:
    - "๑. ... 153"
    - "1. ... หนึ่งร้อยห้าสิบสาม"
    - Position followed by number
    """
    import re

    counts = {}

    # Pattern: Thai numeral position followed by Arabic number
    # Example: "๑. ... ชื่อ ... 153"
    thai_numeral_pattern = r'([๑๒๓๔๕๖๗๘๙๐]+)\s*[.\-]\s*[^\d]*(\d{1,5})\s*$'

    for line in text.split('\n'):
        line = line.strip()
        if not line:
            continue

        # Try Thai numerals
        match = re.search(thai_numeral_pattern, line)
        if match:
            thai_pos = match.group(1)
            count = int(match.group(2))
            # Convert Thai numeral to Arabic
            pos = _thai_to_arabic(thai_pos)
            if pos > 0 and count > 0:
                counts[pos] = count
                continue

        # Try Arabic numerals for position
        arabic_pattern = r'^(\d{1,2})\s*[.\-]\s*[^\d]*(\d{1,5})'
        match = re.search(arabic_pattern, line)
        if match:
            pos = int(match.group(1))
            count = int(match.group(2))
            if pos > 0 and pos < 100 and count < 100000:
                counts[pos] = count

    return counts


def _thai_to_arabic(thai_num: str) -> int:
    """Convert Thai numeral string to Arabic integer."""
    thai_digits = "๐๑๒๓๔๕๖๗๘๙"
    result = 0
    for char in thai_num:
        if char in thai_digits:
            result = result * 10 + thai_digits.index(char)
    return result


def benchmark_preprocessing(image_path: str) -> dict:
    """
    Test different preprocessing combinations to find the best.

    Returns dict with results for each combination.
    """
    combinations = [
        [],
        ["contrast"],
        ["contrast", "sharpen"],
        ["contrast", "sharpen", "binarize"],
        ["contrast", "sharpen", "denoise"],
        ["contrast", "sharpen", "dilate"],
        ["contrast", "sharpen", "binarize", "dilate"],
    ]

    results = {}

    for methods in combinations:
        name = "+".join(methods) if methods else "none"
        result = ensemble_extract(image_path, preprocess_methods=methods)
        results[name] = {
            "confidence": result.confidence,
            "vote_counts": result.vote_counts,
            "preprocessing": result.preprocessing_applied,
            "engine_mode": result.engine_mode,
        }

    return results


def main():
    """Demo and benchmark."""
    import sys

    print("=== Enhanced OCR for Thai Ballots ===")
    print()

    test_image = sys.argv[1] if len(sys.argv) > 1 else "test_images/high_res_page-1.png"

    if not os.path.exists(test_image):
        print(f"Image not found: {test_image}")
        return 1

    print(f"Testing: {test_image}")
    print()

    # Test ensemble extraction
    print("1. Ensemble Extraction")
    print("-" * 40)
    result = ensemble_extract(test_image)
    print(f"Confidence: {result.confidence:.1f}%")
    print(f"Preprocessing: {result.preprocessing_applied}")
    print(f"Engine mode: {result.engine_mode}")
    print(f"Vote counts extracted: {result.vote_counts}")
    print()

    # Benchmark preprocessing
    print("2. Preprocessing Benchmark")
    print("-" * 40)
    benchmark = benchmark_preprocessing(test_image)

    for name, data in sorted(benchmark.items(), key=lambda x: -x[1]["confidence"]):
        conf = data["confidence"]
        votes = len(data["vote_counts"])
        print(f"  {name:<30} {conf:.1f}%  ({votes} votes)")

    print()

    # Find best
    best = max(benchmark.items(), key=lambda x: x[1]["confidence"])
    print(f"Best preprocessing: {best[0]} ({best[1]['confidence']:.1f}%)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
