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

# Optimal Tesseract configuration for Thai ballot forms
# PSM 3 = Fully automatic page segmentation (handles complex layouts best)
# OEM 1 = LSTM neural net engine only (best for Thai script)
DEFAULT_TESSERACT_CONFIG = "--psm 3 --oem 1"


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
    config: str = DEFAULT_TESSERACT_CONFIG
) -> Optional[str]:
    """
    Extract text from an image using Tesseract OCR.

    Args:
        image_path: Path to the image file
        lang: Language(s) to use (default: Thai + English)
        config: Tesseract configuration string
                --psm 3 --oem 1 = Fully automatic page segmentation with LSTM engine (recommended)
                --psm 6 = Assume a single uniform block of text
                --psm 4 = Assume a single column of text

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
    config: str = DEFAULT_TESSERACT_CONFIG
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


# Tesseract config for digit-only extraction (learned from Klaijan/th-election-2026)
# Uses character whitelist to only recognize digits and decimal points
DIGIT_ONLY_CONFIG = "--oem 3 --psm 6 -c tessedit_char_whitelist=0123456789."


def extract_digits_only(
    image_path: str,
    allow_decimal: bool = True
) -> list[str]:
    """
    Extract only digits from an image using Tesseract with character whitelist.

    This is more accurate for handwritten numbers because it forces Tesseract
    to only output digit characters, reducing misrecognition of similar-looking
    letters (e.g., O→0, I→1, S→5).

    Learned from: https://github.com/Klaijan/th-election-2026

    Args:
        image_path: Path to the image file
        allow_decimal: Whether to allow decimal points in output

    Returns:
        List of digit strings found
    """
    if not TESSERACT_AVAILABLE:
        return []

    if not os.path.exists(image_path):
        return []

    # Build config with appropriate whitelist
    if allow_decimal:
        config = DIGIT_ONLY_CONFIG
    else:
        config = "--oem 3 --psm 6 -c tessedit_char_whitelist=0123456789"

    try:
        img = Image.open(image_path)
        text = pytesseract.image_to_string(img, lang="eng", config=config)
        # Split and filter
        parts = text.strip().split()
        # Filter valid numbers
        results = []
        for part in parts:
            if allow_decimal:
                if re.match(r'^\d+\.?\d*$', part):
                    results.append(part)
            else:
                if part.isdigit():
                    results.append(part)
        return results
    except Exception as e:
        print(f"Digit extraction failed: {e}")
        return []


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

    Uses adaptive preprocessing to apply optimal filters based on image
    characteristics (resolution, contrast, noise).

    Args:
        image_path: Path to the input image
        output_path: Path to save preprocessed image (optional)

    Returns:
        Path to preprocessed image or None if failed
    """
    try:
        import adaptive_ocr
        processed_path, _ = adaptive_ocr.adaptive_preprocess(image_path, output_path=output_path)
        return processed_path
    except ImportError:
        # Fallback to static preprocessing if adaptive_ocr is missing
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
            print(f"Preprocessing fallback failed: {e}")
            return None
    except Exception as e:
        print(f"Adaptive preprocessing failed: {e}")
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

    @staticmethod
    def _is_continuation_page(image_path: str) -> bool:
        """Infer whether image is page 2+ from filename convention."""
        filename = os.path.basename(image_path).lower()
        match = re.search(r"page[\s_-]*0*(\d+)", filename, flags=re.IGNORECASE)
        return bool(match and int(match.group(1)) > 1)

    @staticmethod
    def _normalize_digits(token: str) -> str:
        """Normalize Thai/Arabic mixed digits to ASCII digits only."""
        trans = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")
        normalized = token.translate(trans)
        return re.sub(r"[^\d]", "", normalized)

    def _extract_vote_counts_from_column(
        self,
        image_path: str,
        form_type=None,
    ) -> dict[int, int]:
        """
        Extract vote counts from cropped vote-number column using OCR boxes.

        This path is robust on continuation pages where full-page OCR only sees
        headers and misses handwritten counts.
        """
        if not TESSERACT_AVAILABLE:
            return {}

        crop_path = None
        preprocessed_path = None
        try:
            from crop_utils import (
                crop_page_image,
                FORM_TEMPLATES,
                _DEFAULT_TEMPLATE,
                detect_form_type_from_path,
            )

            detected_form = form_type or detect_form_type_from_path(image_path)
            template = FORM_TEMPLATES.get(detected_form, _DEFAULT_TEMPLATE)

            is_continuation = self._is_continuation_page(image_path)
            crop_region = template.vote_numbers_cont if is_continuation else template.vote_numbers_p1

            # Trim a bit more top area on continuation pages to avoid header noise.
            if is_continuation:
                left, top, right, bottom = crop_region
                crop_region = (left, max(top, 0.12), right, bottom)

            crop_path = crop_page_image(image_path, crop_region)
            preprocessed_path = preprocess_for_numbers(crop_path)
            target = preprocessed_path or crop_path

            img = Image.open(target)
            w, h = img.size

            configs = [
                ("eng", "--oem 1 --psm 11 -c tessedit_char_whitelist=0123456789"),
                ("eng", "--oem 1 --psm 6 -c tessedit_char_whitelist=0123456789"),
                ("tha+eng", "--oem 1 --psm 11"),
            ]

            tokens = []
            for lang, config in configs:
                try:
                    data = pytesseract.image_to_data(
                        img,
                        lang=lang,
                        config=config,
                        output_type=pytesseract.Output.DICT,
                    )
                except Exception:
                    continue

                n = len(data.get("text", []))
                for i in range(n):
                    raw = (data["text"][i] or "").strip()
                    if not raw:
                        continue
                    conf_raw = data.get("conf", [0] * n)[i]
                    try:
                        conf = float(conf_raw)
                    except Exception:
                        conf = 0.0

                    normalized = self._normalize_digits(raw)
                    if not normalized:
                        continue
                    # Ignore tiny/noisy values that are likely row markers.
                    if len(normalized) > 5:
                        continue
                    value = int(normalized)
                    if value > 99999:
                        continue

                    left = int(data["left"][i])
                    top = int(data["top"][i])
                    width = int(data["width"][i])
                    height = int(data["height"][i])
                    y_center = top + height / 2.0
                    x_center = left + width / 2.0
                    # Skip the very top area where headers often leak into crop.
                    if y_center < (0.08 * h):
                        continue
                    tokens.append((y_center, x_center, value, conf, width, height))

            if not tokens:
                return {}

            # Cluster into rows by y-center; then keep the rightmost/largest token.
            tokens.sort(key=lambda t: t[0])
            row_threshold = max(10, int(h * 0.012))
            rows = []
            current = [tokens[0]]
            for tok in tokens[1:]:
                if abs(tok[0] - current[-1][0]) <= row_threshold:
                    current.append(tok)
                else:
                    rows.append(current)
                    current = [tok]
            rows.append(current)

            row_values = []
            for row in rows:
                # In vote-number crops, the vote count is usually rightmost.
                # If tied, prefer larger value over tiny row indices.
                row_sorted = sorted(row, key=lambda t: (t[1], t[2]))
                candidate = row_sorted[-1]
                value = candidate[2]
                if value < 0:
                    continue
                row_values.append(value)

            # De-duplicate near-identical repeated detections from multiple OCR passes.
            compact_values = []
            for value in row_values:
                if not compact_values or compact_values[-1] != value:
                    compact_values.append(value)

            # Keep realistic rows only.
            compact_values = compact_values[:60]
            return {idx + 1: val for idx, val in enumerate(compact_values)}
        except Exception:
            return {}
        finally:
            for p in (crop_path, preprocessed_path):
                if p and os.path.exists(p):
                    try:
                        os.unlink(p)
                    except OSError:
                        pass

    def extract_vote_counts(self, image_path: str, form_type=None) -> dict[int, int]:
        """
        Extract vote counts from a ballot image.

        This is a heuristic approach that looks for number patterns
        typical in Thai ballot forms.

        Args:
            image_path: Path to the ballot image

        Returns:
            Dictionary mapping position numbers to vote counts
        """
        column_votes = self._extract_vote_counts_from_column(image_path, form_type=form_type)
        if column_votes:
            return column_votes

        result = self.process_ballot(image_path)
        if not result:
            return {}

        vote_counts = {}
        lines = result.lines
        text = result.text

        # Pattern 1: Thai numeral position followed by number
        # Example: "๑ ... 153" or "๑. 153"
        thai_numeral_pattern = r'([๑๒๓๔๕๖๗๘๙๐]+)\s*[.\-:\s]*[^\d]*?(\d{1,5})'

        for line in lines:
            # Try Thai numerals first
            matches = re.findall(thai_numeral_pattern, line)
            for thai_pos, count in matches:
                position = thai_numeral_to_arabic(thai_pos)
                votes = int(count)
                if 1 <= position <= 57 and votes >= 0:
                    vote_counts[position] = votes

            # Pattern 2: Arabic position followed by vote count
            # Example: "1 153" or "1. 153"
            arabic_pattern = r'^\s*(\d{1,2})\s*[.\-:\s]+(\d{1,5})\s*$'
            match = re.match(arabic_pattern, line.strip())
            if match:
                position = int(match.group(1))
                votes = int(match.group(2))
                if 1 <= position <= 57 and position not in vote_counts:
                    vote_counts[position] = votes

        # Pattern 3: Look for consecutive numbers in vote column format
        # Find all multi-digit numbers that could be vote counts
        if not vote_counts:
            normalized_text = text.translate(str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789"))
            all_numbers = re.findall(r'\b(\d{1,5})\b', normalized_text)
            # Filter likely vote counts (2+ digits, reasonable range)
            likely_votes = [int(n) for n in all_numbers if 0 <= int(n) <= 99999]
            # Assign to positions 1, 2, 3... based on order found
            for i, votes in enumerate(likely_votes[:60], 1):
                vote_counts[i] = votes

        return vote_counts

    def detect_form_category(self, image_path: str) -> dict:
        """
        Detect form category and type from a ballot image.

        Uses fuzzy pattern matching to handle OCR character confusions
        (e.g., ช <-> ซ in Thai text).

        Args:
            image_path: Path to the ballot image

        Returns:
            Dictionary with 'is_party_list', 'form_category', and confidence
        """
        result = self.process_ballot(image_path)
        if not result:
            return {'is_party_list': None, 'form_category': 'unknown', 'confidence': 0}

        text = result.text

        # Fuzzy patterns for party list detection
        # Handle OCR misreads: ช <-> ซ, ื่ <-> ื
        party_list_patterns = [
            r'บัญชีราย[ชซ]ื่อ',  # บัญชีรายชื่อ or บัญชีรายซื่อ
            r'แบบบัญชี',         # แบบบัญชี
            r'\(บช\)',           # (บช)
            r'บช\)',             # บช) without opening paren
        ]

        is_party_list = False
        for pattern in party_list_patterns:
            if re.search(pattern, text):
                is_party_list = True
                break

        # Determine form category
        if is_party_list:
            form_category = 'party_list'
        elif 'แบ่งเขตเลือกตั้ง' in text:
            form_category = 'constituency'
        else:
            form_category = 'unknown'

        return {
            'is_party_list': is_party_list,
            'form_category': form_category,
            'confidence': result.confidence
        }


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
