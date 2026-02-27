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
    import cv2
    import numpy as np
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


def deskew_image(img_arr: "np.ndarray") -> "np.ndarray":
    """
    Deskew image using projection profile.
    Simple method: rotate small angles and find max horizontal projection variance.
    """
    try:
        # Convert to grayscale if needed
        if len(img_arr.shape) == 3:
            gray = cv2.cvtColor(img_arr, cv2.COLOR_RGB2GRAY)
        else:
            gray = img_arr

        # Invert (text is white)
        thresh = cv2.bitwise_not(gray)
        
        # Check angles -5 to +5
        best_angle = 0
        max_variance = 0
        
        # Fast check: coarse steps
        for angle in range(-5, 6):
            # Rotate
            h, w = gray.shape[:2]
            center = (w // 2, h // 2)
            M = cv2.getRotationMatrix2D(center, angle, 1.0)
            rotated = cv2.warpAffine(thresh, M, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
            
            # Project
            projection = np.sum(rotated, axis=1)
            variance = np.var(projection)
            
            if variance > max_variance:
                max_variance = variance
                best_angle = angle
                
        if abs(best_angle) > 0:
            print(f"  Deskewing: detected angle {best_angle}")
            h, w = img_arr.shape[:2]
            center = (w // 2, h // 2)
            M = cv2.getRotationMatrix2D(center, best_angle, 1.0)
            return cv2.warpAffine(img_arr, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
            
        return img_arr
        
    except Exception as e:
        print(f"  Deskew error: {e}")
        return img_arr


def remove_lines(img_arr: "np.ndarray") -> "np.ndarray":
    """
    Remove horizontal and vertical lines from image using morphology.
    """
    try:
        if len(img_arr.shape) == 3:
            gray = cv2.cvtColor(img_arr, cv2.COLOR_RGB2GRAY)
        else:
            gray = img_arr
            
        # Threshold
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

        # Horizontal kernel
        h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (40, 1))
        detect_horizontal = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, h_kernel, iterations=2)
        
        # Vertical kernel
        v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 40))
        detect_vertical = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, v_kernel, iterations=2)
        
        # Combine lines
        lines = cv2.addWeighted(detect_horizontal, 0.5, detect_vertical, 0.5, 0.0)
        
        # Invert mask to get white lines on black background (since we work with inverted images usually)
        # But here we want to subtract lines from original image
        
        # Create a white image
        # mask = cv2.threshold(lines, 40, 255, cv2.THRESH_BINARY)[1]
        
        # Dilate lines slightly to ensure full removal
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        lines = cv2.dilate(lines, kernel, iterations=1)
        
        # Convert lines to mask: where lines are, we want white (255) in the output to "erase" them
        # (Assuming black text on white background)
        # Original is white bg, black text.
        # Lines are detected as 'foreground' (white in thresh).
        
        # Add the lines back to original (making them white)
        if len(img_arr.shape) == 3:
            lines_3ch = cv2.cvtColor(lines, cv2.COLOR_GRAY2RGB)
            result = cv2.add(img_arr, lines_3ch)
        else:
            result = cv2.add(img_arr, lines)
            
        return result

    except Exception as e:
        print(f"  Line removal error: {e}")
        return img_arr


def add_padding(img: "Image.Image", border: int = 20) -> "Image.Image":
    """
    Add white border padding to image.
    Tesseract often fails if text touches the edge.
    """
    if not PIL_AVAILABLE:
        return img
    try:
        # ImageOps.expand adds border. Fill with white (255)
        return ImageOps.expand(img, border=border, fill='white')
    except Exception as e:
        print(f"  Padding error: {e}")
        return img


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
    # Padding is always recommended for OCR safety
    recommended = ["padding"]
    
    # v2.0: Self-Correction hint
    force_aggressive = os.environ.get("ADAPTIVE_OCR_FORCE_AGGRESSIVE") == "1"
    if force_aggressive:
        recommended.extend(["contrast", "sharpen", "binarize", "dilate"])

    if resolution == "high":
        # High-res: can handle aggressive preprocessing
        recommended.extend(["contrast", "sharpen", "binarize"])
        # High res usually means we can see lines clearly, good candidate for line removal
        recommended.append("remove_lines")
    elif resolution == "low":
        # Low-res: preserve information, minimal processing
        pass
    else:
        # Medium: light preprocessing
        recommended.append("contrast")
        recommended.append("deskew") # Medium res often mobile scans

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
    
    # Advanced CV operations (convert to numpy)
    if "deskew" in methods or "remove_lines" in methods:
        img_np = np.array(processed)
        
        if "deskew" in methods:
            img_np = deskew_image(img_np)
            
        if "remove_lines" in methods:
            img_np = remove_lines(img_np)
            
        processed = Image.fromarray(img_np)
    
    # Standard PIL operations
    
    # Padding (do before other filters to avoid border artifacts)
    if "padding" in methods:
        processed = add_padding(processed)

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
