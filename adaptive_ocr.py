#!/usr/bin/env python3
"""
Adaptive OCR preprocessing based on image characteristics.

Key insight: Different images need different preprocessing.
High-res images benefit from aggressive preprocessing.
Low-res images are hurt by binarization.

Solution: Analyze image characteristics and select optimal preprocessing.
"""

import os
import sys
import io
import tempfile
from dataclasses import dataclass
from typing import Optional, Union, List
from pathlib import Path

try:
    from PIL import Image, ImageStat, ImageEnhance, ImageFilter, ImageOps
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


@dataclass
class ImageCharacteristics:
    """Analyzed characteristics of an image."""
    width: int
    height: int
    resolution_category: str  # "low", "medium", "high"
    contrast_ratio: float
    has_noise: bool
    recommended_preprocessing: List[str]


def analyze_image_obj(img: "Image.Image") -> ImageCharacteristics:
    """
    Analyze a PIL Image object to determine optimal preprocessing.
    """
    if not PIL_AVAILABLE:
        return ImageCharacteristics(0, 0, "medium", 0, False, ["contrast"])

    width, height = img.size

    # Convert to grayscale for analysis
    if img.mode != "L":
        gray = img.convert("L")
    else:
        gray = img

    # Calculate contrast (standard deviation of pixel values)
    stat = ImageStat.Stat(gray)
    contrast = stat.stddev[0]  # Higher = more contrast

    # Determine resolution category
    total_pixels = width * height
    if total_pixels > 4_000_000:  # > 4MP
        resolution = "high"
    elif total_pixels > 1_000_000:  # > 1MP
        resolution = "medium"
    else:
        resolution = "low"

    # Detect noise by looking at high-frequency variations
    # (simplified - in production use proper noise detection)
    has_noise = contrast > 70 and resolution == "low"

    # Determine recommended preprocessing based on characteristics
    if resolution == "high":
        # High-res: can handle aggressive preprocessing
        recommended = ["contrast", "sharpen", "binarize"]
    elif resolution == "low":
        # Low-res: preserve information, minimal processing
        recommended = []  # No preprocessing!
    else:
        # Medium: light preprocessing
        recommended = ["contrast"]

    # Adjust based on contrast
    if contrast < 40:
        # Low contrast image - needs boost
        if "contrast" not in recommended:
            recommended.append("contrast")
    elif contrast > 80:
        # High contrast - might be over-processed
        if "binarize" in recommended:
            recommended.remove("binarize")

    return ImageCharacteristics(
        width=width,
        height=height,
        resolution_category=resolution,
        contrast_ratio=contrast,
        has_noise=has_noise,
        recommended_preprocessing=recommended,
    )


def analyze_image(image_input: Union[str, "Image.Image"]) -> ImageCharacteristics:
    """
    Analyze image (path or object) to determine optimal preprocessing.
    """
    if isinstance(image_input, str):
        if not PIL_AVAILABLE:
            return ImageCharacteristics(0, 0, "medium", 0, False, [])
        with Image.open(image_input) as img:
            return analyze_image_obj(img)
    else:
        return analyze_image_obj(image_input)


def apply_preprocessing(img: "Image.Image", methods: List[str]) -> "Image.Image":
    """Apply list of preprocessing methods to a PIL Image."""
    if not PIL_AVAILABLE:
        return img

    processed = img.copy()
    
    # Convert to grayscale if needed
    if processed.mode != "L" and ("binarize" in methods or "threshold" in methods):
        processed = processed.convert("L")
    elif processed.mode != "RGB" and "contrast" in methods:
        # Contrast works best in RGB or L
        pass

    if "denoise" in methods:
        processed = processed.filter(ImageFilter.MedianFilter(size=3))

    if "contrast" in methods:
        # Higher contrast for handwritten ink
        # Ensure compatible mode for Contrast
        if processed.mode not in ["RGB", "L"]:
            processed = processed.convert("RGB")
        processed = ImageEnhance.Contrast(processed).enhance(2.0)

    if "sharpen" in methods:
        processed = processed.filter(ImageFilter.SHARPEN)
        processed = processed.filter(ImageFilter.EDGE_ENHANCE)

    if "dilate" in methods:
        # Thicken thin strokes
        processed = processed.filter(ImageFilter.MaxFilter(size=3))

    if "binarize" in methods:
        # Adaptive thresholding
        if processed.mode != "L":
            processed = processed.convert("L")
        processed = processed.point(lambda x: 0 if x < 140 else 255)

    return processed


def adaptive_preprocess_image(img: "Image.Image") -> "Image.Image":
    """
    Analyze and preprocess a PIL Image.
    Returns the processed PIL Image.
    """
    chars = analyze_image_obj(img)
    print(f"  Adaptive OCR: {chars.resolution_category} res, contrast={chars.contrast_ratio:.1f}, methods={chars.recommended_preprocessing}")
    return apply_preprocessing(img, chars.recommended_preprocessing)


def adaptive_preprocess(image_path: str, output_path: Optional[str] = None) -> tuple[str, list[str]]:
    """
    Apply preprocessing adapted to image characteristics (File API).

    Returns (output_path, methods_applied).
    """
    if not PIL_AVAILABLE:
        return image_path, []

    with Image.open(image_path) as img:
        chars = analyze_image_obj(img)
        print(f"  Adaptive OCR (File): {chars.resolution_category} res, contrast={chars.contrast_ratio:.1f}, methods={chars.recommended_preprocessing}")
        processed = apply_preprocessing(img, chars.recommended_preprocessing)
        
        if output_path is None:
            suffix = Path(image_path).suffix or ".png"
            fd, output_path = tempfile.mkstemp(suffix=suffix, prefix="adaptive_")
            os.close(fd)
            
        processed.save(output_path)
        
    return output_path, chars.recommended_preprocessing


def adaptive_extract(image_path: str) -> tuple[str, float, dict]:
    """
    Extract text with adaptive preprocessing.

    Returns (text, confidence, metadata).
    """
    # Analyze first
    chars = analyze_image(image_path)

    # Preprocess with recommended settings
    processed_path, methods = adaptive_preprocess(image_path)

    # Extract with optimal config based on resolution
    from enhanced_ocr import extract_with_config

    if chars.resolution_category == "high":
        # High-res: try sparse text mode
        text, conf = extract_with_config(processed_path, psm=11, oem=3)
    else:
        # Lower-res: use standard block mode
        text, conf = extract_with_config(processed_path, psm=6, oem=3)

    # Clean up
    if processed_path != image_path:
        try:
            os.unlink(processed_path)
        except OSError:
            pass

    metadata = {
        "resolution": chars.resolution_category,
        "dimensions": f"{chars.width}x{chars.height}",
        "contrast": chars.contrast_ratio,
        "preprocessing": methods,
    }

    return text, conf, metadata


def compare_strategies(image_path: str) -> dict:
    """
    Compare all strategies on an image.

    Returns dict with results for each approach.
    """
    from enhanced_ocr import extract_with_config, preprocess_image

    results = {}

    # Strategy 1: No preprocessing
    text, conf = extract_with_config(image_path, psm=6, oem=3)
    results["none"] = {"confidence": conf, "preprocessing": []}

    # Strategy 2: Adaptive (our new approach)
    chars = analyze_image(image_path)
    processed_path, methods = preprocess_image(
        image_path,
        methods=chars.recommended_preprocessing
    )
    text, conf = extract_with_config(processed_path, psm=6, oem=3)
    results["adaptive"] = {
        "confidence": conf,
        "preprocessing": methods,
        "resolution": chars.resolution_category,
    }
    if processed_path != image_path:
        os.unlink(processed_path)

    # Strategy 3: Light preprocessing (contrast only)
    processed_path, methods = preprocess_image(image_path, methods=["contrast"])
    text, conf = extract_with_config(processed_path, psm=6, oem=3)
    results["light"] = {"confidence": conf, "preprocessing": methods}
    if processed_path != image_path:
        os.unlink(processed_path)

    # Strategy 4: Aggressive (for comparison)
    processed_path, methods = preprocess_image(
        image_path,
        methods=["contrast", "sharpen", "binarize", "dilate"]
    )
    text, conf = extract_with_config(processed_path, psm=6, oem=3)
    results["aggressive"] = {"confidence": conf, "preprocessing": methods}
    if processed_path != image_path:
        os.unlink(processed_path)

    return results


def main():
    """Test adaptive preprocessing."""
    print("=== Adaptive OCR Preprocessing Test ===")
    print()

    test_images = [
        "test_images/high_res_page-1.png",
        "test_images/page-1.png",
        "test_images/bch_page-1.png",
    ]

    for img_path in test_images:
        if not os.path.exists(img_path):
            continue

        print(f"Image: {img_path}")

        # Analyze
        chars = analyze_image(img_path)
        print(f"  Resolution: {chars.resolution_category} ({chars.width}x{chars.height})")
        print(f"  Contrast: {chars.contrast_ratio:.1f}")
        print(f"  Recommended: {chars.recommended_preprocessing}")

        # Compare strategies
        results = compare_strategies(img_path)

        print("  Strategy results:")
        for name, data in sorted(results.items(), key=lambda x: -x[1]["confidence"]):
            conf = data["confidence"]
            prep = "+".join(data["preprocessing"]) if data["preprocessing"] else "none"
            print(f"    {name:<12} {conf:.1f}%  ({prep})")

        # Find best
        best = max(results.items(), key=lambda x: x[1]["confidence"])
        print(f"  BEST: {best[0]} at {best[1]['confidence']:.1f}%")
        print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
