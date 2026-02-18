#!/usr/bin/env python3
"""
EasyOCR wrapper module for Thai Election Ballot OCR.

EasyOCR is a Python module for extracting text from images.
It supports 80+ languages including Thai and runs locally.

Advantages over Tesseract:
- Better accuracy for handwritten text
- Built-in text detection (no need to preprocess)
- GPU acceleration support

Requirements:
- easyocr (pip install easyocr)
- PyTorch (pip install torch)

Usage:
    from easyocr_wrapper import EasyOCRExtractor, extract_text_easyocr

    # Simple text extraction
    text = extract_text_easyocr("ballot.jpg")

    # With confidence scores
    extractor = EasyOCRExtractor()
    results = extractor.extract("ballot.jpg")
"""

import os
from typing import Optional
from dataclasses import dataclass, field

# Try to import EasyOCR
try:
    import easyocr
    EASYOCR_AVAILABLE = True
except ImportError:
    EASYOCR_AVAILABLE = False
    easyocr = None


@dataclass
class EasyOCRResult:
    """Result from EasyOCR extraction."""
    text: str
    confidence: float  # Average confidence (0-1)
    lines: list[tuple[str, float]] = field(default_factory=list)  # (text, confidence)
    raw_results: list = field(default_factory=list)  # Original EasyOCR output


def check_easyocr_available() -> tuple[bool, str]:
    """
    Check if EasyOCR is installed and available.

    Returns:
        Tuple of (is_available, status_message)
    """
    if not EASYOCR_AVAILABLE:
        return False, "EasyOCR not installed. Install with: pip install easyocr"

    try:
        import torch
        has_gpu = torch.cuda.is_available()
        device = "GPU" if has_gpu else "CPU"
        return True, f"EasyOCR available (using {device})"
    except ImportError:
        return True, "EasyOCR available (CPU only, PyTorch not installed)"


def extract_text_easyocr(
    image_path: str,
    languages: list[str] = None,
    gpu: bool = False
) -> Optional[str]:
    """
    Extract text from an image using EasyOCR.

    Args:
        image_path: Path to the image file
        languages: List of language codes (default: ["th", "en"])
        gpu: Whether to use GPU acceleration

    Returns:
        Extracted text or None if extraction failed
    """
    if not EASYOCR_AVAILABLE:
        print("EasyOCR not installed. Install with: pip install easyocr")
        return None

    if not os.path.exists(image_path):
        print(f"Image not found: {image_path}")
        return None

    if languages is None:
        languages = ["th", "en"]  # Thai + English

    try:
        reader = easyocr.Reader(languages, gpu=gpu)
        results = reader.readtext(image_path)

        # Combine all text
        text_lines = [result[1] for result in results]
        return "\n".join(text_lines)

    except Exception as e:
        print(f"EasyOCR extraction failed: {e}")
        return None


class EasyOCRExtractor:
    """
    High-level EasyOCR interface for Thai ballots.

    Provides methods optimized for extracting text and numbers
    from Thai election forms.
    """

    def __init__(self, languages: list[str] = None, gpu: bool = False):
        """
        Initialize EasyOCR extractor.

        Args:
            languages: List of language codes (default: ["th", "en"])
            gpu: Whether to use GPU acceleration
        """
        self.languages = languages or ["th", "en"]
        self.gpu = gpu
        self._reader = None

    def _get_reader(self):
        """Lazy-load the EasyOCR reader."""
        if not EASYOCR_AVAILABLE:
            raise RuntimeError("EasyOCR not installed")

        if self._reader is None:
            self._reader = easyocr.Reader(self.languages, gpu=self.gpu)
        return self._reader

    def extract(self, image_path: str) -> Optional[EasyOCRResult]:
        """
        Extract text with confidence scores.

        Args:
            image_path: Path to the image file

        Returns:
            EasyOCRResult with text and confidence scores
        """
        if not os.path.exists(image_path):
            print(f"Image not found: {image_path}")
            return None

        try:
            reader = self._get_reader()
            results = reader.readtext(image_path)

            if not results:
                return EasyOCRResult(text="", confidence=0.0)

            # Extract text and confidence
            lines = [(result[1], result[2]) for result in results]
            text = "\n".join(result[1] for result in results)

            # Calculate average confidence
            confidences = [result[2] for result in results]
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0

            return EasyOCRResult(
                text=text,
                confidence=avg_confidence,
                lines=lines,
                raw_results=results
            )

        except Exception as e:
            print(f"EasyOCR extraction failed: {e}")
            return None

    def extract_numbers(self, image_path: str) -> list[int]:
        """
        Extract Arabic numerals from an image.

        Args:
            image_path: Path to the image file

        Returns:
            List of extracted numbers
        """
        import re

        result = self.extract(image_path)
        if not result:
            return []

        # Find all Arabic numerals
        numbers = re.findall(r'\b\d+\b', result.text)
        return [int(n) for n in numbers]


def is_available() -> bool:
    """Check if EasyOCR is available."""
    return EASYOCR_AVAILABLE


def main():
    """Demo/test function."""
    import sys

    print("EasyOCR Wrapper Module")
    print("=" * 50)

    available, status = check_easyocr_available()
    print(f"Available: {available}")
    print(f"Status: {status}")

    if available:
        if len(sys.argv) > 1:
            image_path = sys.argv[1]
            print(f"\nProcessing: {image_path}")

            extractor = EasyOCRExtractor()
            result = extractor.extract(image_path)

            if result:
                print(f"\nConfidence: {result.confidence:.1%}")
                print(f"Lines found: {len(result.lines)}")

                print("\n=== Extracted Text ===")
                print(result.text[:1000] if len(result.text) > 1000 else result.text)
            else:
                print("Extraction failed")
    else:
        print("\nInstall EasyOCR: pip install easyocr")


if __name__ == "__main__":
    main()
