#!/usr/bin/env python3
"""
Tesseract OCR module for Thai Election Ballot OCR.

Provides local OCR capabilities using Tesseract as an alternative to
cloud-based AI vision APIs. Useful for:
- Offline operation
- Cost reduction
- Privacy-sensitive deployments
- Fallback when cloud APIs are unavailable

Requirements:
- tesseract-ocr (install via brew/apt)
- tesseract-ocr-tha (Thai language pack)
- pytesseract (Python wrapper)

Usage:
    from tesseract_ocr import TesseractOCR, extract_text, extract_numbers

    # Simple text extraction
    text = extract_text("ballot.jpg", lang="tha+eng")

    # Number extraction with Thai numeral support
    numbers = extract_numbers("ballot.jpg")

    # Full OCR with structured output
    ocr = TesseractOCR()
    result = ocr.process_ballot("ballot.jpg")
"""

import os
import re
import subprocess
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field

# Try to import pytesseract
try:
    import pytesseract
    from PIL import Image
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False
    pytesseract = None
    Image = None


@dataclass
class TesseractResult:
    """Result from Tesseract OCR processing."""
    text: str
    confidence: float  # Average confidence (0-100)
    numbers: list[int] = field(default_factory=list)
    thai_numbers: list[str] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)
    words: list[tuple[str, float]] = field(default_factory=list)  # (word, confidence)


def check_tesseract_installed() -> tuple[bool, str]:
    """
    Check if Tesseract OCR is installed and available.

    Returns:
        Tuple of (is_installed, version_or_error_message)
    """
    try:
        result = subprocess.run(
            ["tesseract", "--version"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            version = result.stdout.split('\n')[0]
            return True, version
        return False, f"Tesseract error: {result.stderr}"
    except FileNotFoundError:
        return False, "Tesseract not found. Install with: brew install tesseract tesseract-lang"
    except Exception as e:
        return False, f"Error checking Tesseract: {e}"


def check_thai_language_pack() -> bool:
    """
    Check if Thai language pack is installed.

    Returns:
        True if Thai language pack is available
    """
    try:
        result = subprocess.run(
            ["tesseract", "--list-langs"],
            capture_output=True,
            text=True,
            timeout=10
        )
        return "tha" in result.stdout
    except Exception:
        return False


def extract_text(
    image_path: str,
    lang: str = "tha+eng",
    config: str = "--psm 6"
) -> Optional[str]:
    """
    Extract text from an image using Tesseract OCR.

    Args:
        image_path: Path to the image file
        lang: Language(s) to use (default: Thai + English)
        config: Tesseract configuration string
                --psm 6 = Assume a single uniform block of text
                --psm 4 = Assume a single column of text
                --psm 3 = Fully automatic page segmentation

    Returns:
        Extracted text or None if extraction failed
    """
    if not TESSERACT_AVAILABLE:
        print("pytesseract not installed. Install with: pip install pytesseract")
        return None

    if not os.path.exists(image_path):
        print(f"Image not found: {image_path}")
        return None

    try:
        img = Image.open(image_path)
        text = pytesseract.image_to_string(img, lang=lang, config=config)
        return text.strip()
    except Exception as e:
        print(f"Tesseract extraction failed: {e}")
        return None


def extract_with_confidence(
    image_path: str,
    lang: str = "tha+eng",
    config: str = "--psm 6"
) -> Optional[TesseractResult]:
    """
    Extract text with confidence scores.

    Args:
        image_path: Path to the image file
        lang: Language(s) to use
        config: Tesseract configuration string

    Returns:
        TesseractResult with text, confidence, and word-level details
    """
    if not TESSERACT_AVAILABLE:
        return None

    try:
        img = Image.open(image_path)

        # Get text
        text = pytesseract.image_to_string(img, lang=lang, config=config)

        # Get data with confidence
        data = pytesseract.image_to_data(img, lang=lang, config=config, output_type=pytesseract.Output.DICT)

        # Calculate average confidence
        confidences = [c for c in data.get('conf', []) if c > 0]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0

        # Extract words with confidence
        words = []
        for i, word in enumerate(data.get('text', [])):
            if word.strip():
                conf = data.get('conf', [0])[i] if i < len(data.get('conf', [])) else 0
                words.append((word, conf))

        # Extract lines
        lines = [line.strip() for line in text.split('\n') if line.strip()]

        return TesseractResult(
            text=text.strip(),
            confidence=avg_confidence,
            lines=lines,
            words=words
        )
    except Exception as e:
        print(f"Tesseract extraction failed: {e}")
        return None


def extract_numbers(
    image_path: str,
    lang: str = "tha+eng"
) -> list[int]:
    """
    Extract Arabic numerals from an image.

    Args:
        image_path: Path to the image file
        lang: Language(s) to use

    Returns:
        List of extracted numbers
    """
    text = extract_text(image_path, lang=lang)
    if not text:
        return []

    # Find all Arabic numerals
    numbers = re.findall(r'\b\d+\b', text)
    return [int(n) for n in numbers]


def extract_thai_numbers(
    image_path: str,
    lang: str = "tha"
) -> list[str]:
    """
    Extract Thai numerals (๐๑๒๓๔๕๖๗๘๙) from an image.

    Args:
        image_path: Path to the image file
        lang: Language(s) to use

    Returns:
        List of Thai number strings
    """
    text = extract_text(image_path, lang=lang)
    if not text:
        return []

    # Thai numerals pattern
    thai_numerals = "๐๑๒๓๔๕๖๗๘๙"
    pattern = f"[{thai_numerals}]+"

    return re.findall(pattern, text)


def thai_numeral_to_arabic(thai_num: str) -> int:
    """
    Convert Thai numerals to Arabic numerals.

    Args:
        thai_num: String of Thai numerals (e.g., "๑๒๓")

    Returns:
        Integer value (e.g., 123)
    """
    thai_to_arabic = {
        '๐': '0', '๑': '1', '๒': '2', '๓': '3', '๔': '4',
        '๕': '5', '๖': '6', '๗': '7', '๘': '8', '๙': '9'
    }

    arabic_str = ''.join(thai_to_arabic.get(c, c) for c in thai_num)
    try:
        return int(arabic_str)
    except ValueError:
        return 0


def preprocess_for_numbers(image_path: str, output_path: Optional[str] = None) -> Optional[str]:
    """
    Preprocess an image to improve number extraction.

    Applies:
    - Grayscale conversion
    - Thresholding
    - Noise reduction

    Args:
        image_path: Path to the input image
        output_path: Path to save preprocessed image (optional)

    Returns:
        Path to preprocessed image or None if failed
    """
    try:
        from PIL import Image, ImageFilter, ImageOps

        img = Image.open(image_path)

        # Convert to grayscale
        img = img.convert('L')

        # Increase contrast
        img = ImageOps.autocontrast(img)

        # Apply threshold (binary image)
        threshold = 128
        img = img.point(lambda x: 255 if x > threshold else 0, '1')

        # Convert back to grayscale for Tesseract
        img = img.convert('L')

        # Save preprocessed image
        if output_path is None:
            output_path = str(image_path) + ".preprocessed.png"

        img.save(output_path)
        return output_path

    except Exception as e:
        print(f"Preprocessing failed: {e}")
        return None


class TesseractOCR:
    """
    High-level Tesseract OCR interface for Thai ballots.

    Provides methods optimized for extracting vote counts and
    ballot information from Thai election forms.
    """

    def __init__(self, lang: str = "tha+eng"):
        """
        Initialize Tesseract OCR.

        Args:
            lang: Default language(s) to use
        """
        self.lang = lang
        self._check_availability()

    def _check_availability(self) -> None:
        """Check if Tesseract and language packs are available."""
        installed, version = check_tesseract_installed()
        if not installed:
            raise RuntimeError(f"Tesseract not available: {version}")

        if not check_thai_language_pack():
            print("Warning: Thai language pack not installed.")
            print("Install with: brew install tesseract-lang")

    def process_ballot(self, image_path: str) -> Optional[TesseractResult]:
        """
        Process a ballot image and extract all relevant information.

        Args:
            image_path: Path to the ballot image

        Returns:
            TesseractResult with extracted data
        """
        # Try with default settings first
        result = extract_with_confidence(image_path, lang=self.lang)

        if result and result.confidence < 50:
            # Low confidence - try preprocessing
            preprocessed = preprocess_for_numbers(image_path)
            if preprocessed:
                result = extract_with_confidence(preprocessed, lang=self.lang)
                try:
                    os.unlink(preprocessed)
                except OSError:
                    pass

        if result:
            # Extract numbers
            result.numbers = extract_numbers(image_path, lang=self.lang)
            result.thai_numbers = extract_thai_numbers(image_path, lang=self.lang)

        return result

    def extract_vote_counts(self, image_path: str) -> dict[int, int]:
        """
        Extract vote counts from a ballot image.

        This is a heuristic approach that looks for number patterns
        typical in Thai ballot forms.

        Args:
            image_path: Path to the ballot image

        Returns:
            Dictionary mapping position numbers to vote counts
        """
        result = self.process_ballot(image_path)
        if not result:
            return {}

        vote_counts = {}
        lines = result.lines

        # Look for patterns like "1. 100" or "1 100" or "หมายเลข 1: 100"
        for line in lines:
            # Try to match position and vote count
            match = re.match(r'(\d+)\s*[:\.]?\s*(\d+)', line.strip())
            if match:
                position = int(match.group(1))
                votes = int(match.group(2))
                if 1 <= position <= 57:  # Valid position range
                    vote_counts[position] = votes

        return vote_counts


# Module-level convenience functions
def is_available() -> bool:
    """Check if Tesseract OCR is available."""
    return TESSERACT_AVAILABLE and check_tesseract_installed()[0]


def get_version() -> Optional[str]:
    """Get Tesseract version string."""
    installed, version = check_tesseract_installed()
    return version if installed else None


def main():
    """Demo/test function."""
    import sys

    print("Tesseract OCR Module")
    print("=" * 50)

    installed, version = check_tesseract_installed()
    print(f"Installed: {installed}")
    print(f"Version: {version}")

    thai_available = check_thai_language_pack()
    print(f"Thai language pack: {thai_available}")

    if TESSERACT_AVAILABLE:
        print("\npytesseract is available")

        if thai_available:
            try:
                ocr = TesseractOCR()
                print("TesseractOCR initialized successfully")

                # Process a test image if provided
                if len(sys.argv) > 1:
                    image_path = sys.argv[1]
                    print(f"\nProcessing: {image_path}")

                    result = ocr.process_ballot(image_path)
                    if result:
                        print(f"\nConfidence: {result.confidence:.1f}%")
                        print(f"Lines found: {len(result.lines)}")
                        print(f"Numbers found: {result.numbers}")
                        print(f"Thai numbers: {result.thai_numbers}")

                        print("\n=== OCR Text ===")
                        print(result.text[:1000] if len(result.text) > 1000 else result.text)

            except Exception as e:
                print(f"Failed to initialize: {e}")
        else:
            print("Install Thai language pack for full functionality")
    else:
        print("\nInstall pytesseract: pip install pytesseract")


if __name__ == "__main__":
    main()
