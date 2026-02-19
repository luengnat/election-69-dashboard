#!/usr/bin/env python3
"""
Vote extraction module for Thai election ballots.

Implements best practices learned from github.com/Klaijan/th-election-2026:
- Extract only the last column (vote counts)
- Remove grid lines before OCR
- Use digit-only Tesseract with character whitelist
- Detect dotted lines to validate cells
- Support multiple DPI settings

Usage:
    from vote_extractor import VoteExtractor

    extractor = VoteExtractor()
    votes = extractor.extract_votes("ballot.png")
"""

import os
import re
import tempfile
from pathlib import Path
from typing import Optional, List, Tuple
from dataclasses import dataclass

try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    import pytesseract
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False


# Thai numeral to Arabic conversion table
THAI_TO_ARABIC = str.maketrans({
    '๐': '0', '๑': '1', '๒': '2', '๓': '3', '๔': '4',
    '๕': '5', '๖': '6', '๗': '7', '๘': '8', '๙': '9'
})

# Tesseract config for digit-only extraction
DIGIT_CONFIG = "--oem 3 --psm 6 -c tessedit_char_whitelist=0123456789."


@dataclass
class VoteEntry:
    """A single vote count entry."""
    position: int  # Candidate/party position number
    votes: int     # Vote count
    raw_text: str  # Raw OCR text
    confidence: float = 0.0


@dataclass
class VoteExtractionResult:
    """Result from vote extraction."""
    votes: List[VoteEntry]
    total_votes: int
    column_detected: bool
    grid_removed: bool
    dpi_used: int
    error: Optional[str] = None


def thai_to_arabic(text: str) -> str:
    """Convert Thai numerals to Arabic numerals."""
    return text.translate(THAI_TO_ARABIC)


def remove_grid_lines(image: "np.ndarray") -> "np.ndarray":
    """
    Remove horizontal and vertical grid lines from image.

    Uses morphological operations to detect and remove lines.
    """
    if not CV2_AVAILABLE:
        return image

    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    else:
        gray = image.copy()

    # Threshold
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    h, w = thresh.shape[:2]

    # Dynamic kernel sizes based on image dimensions
    kx = max(18, int(w / 18))
    ky = max(18, int(h / 10))

    # Horizontal lines
    horiz_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kx, 1))
    horiz = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, horiz_kernel, iterations=1)

    # Vertical lines
    vert_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, ky))
    vert = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, vert_kernel, iterations=1)

    # Combine
    lines = cv2.bitwise_or(horiz, vert)

    # Remove lines from original
    result = gray.copy()
    result[lines > 0] = 255

    return result


def detect_dotted_lines(cell: "np.ndarray",
                        min_dots: int = 5,
                        min_diameter: int = 3,
                        max_diameter: int = 8) -> bool:
    """
    Check if a cell contains dotted lines (writing guide).

    Thai ballot forms use dotted lines as guides for handwriting.
    """
    if not CV2_AVAILABLE:
        return True  # Assume has dots if can't check

    if len(cell.shape) == 3:
        gray = cv2.cvtColor(cell, cv2.COLOR_RGB2GRAY)
    else:
        gray = cell

    # Threshold
    _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    # Find connected components
    n, labels, stats, centroids = cv2.connectedComponentsWithStats(bw, connectivity=8)

    if n <= 1:
        return False

    # Check for small circular blobs (dots)
    min_area = int(3.14159 * (min_diameter / 2.0) ** 2)
    max_area = int(3.14159 * (max_diameter / 2.0) ** 2) * 4

    dot_centers = []
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if area < min_area or area > max_area:
            continue
        if w > max_diameter * 2 or h > max_diameter * 2:
            continue
        cx, cy = centroids[i]
        dot_centers.append((int(cx), int(cy)))

    return len(dot_centers) >= min_dots


def extract_last_column(image: "np.ndarray",
                        table_zone: Tuple[float, float] = (0.50, 0.95),
                        column_frac: Tuple[float, float] = (0.85, 0.98)) -> "np.ndarray":
    """
    Extract the last column from a ballot image.

    Args:
        image: Input image (numpy array)
        table_zone: (top_frac, bottom_frac) of page containing the table
        column_frac: (left_frac, right_frac) for the vote column

    Returns:
        Cropped image of the last column
    """
    h, w = image.shape[:2]

    # Calculate pixel coordinates
    top = int(h * table_zone[0])
    bottom = int(h * table_zone[1])
    left = int(w * column_frac[0])
    right = int(w * column_frac[1])

    return image[top:bottom, left:right]


def preprocess_for_digits(image: "np.ndarray") -> "np.ndarray":
    """
    Preprocess image for digit extraction.

    Steps:
    1. Convert to grayscale
    2. Apply CLAHE contrast enhancement
    3. Remove grid lines
    4. Apply Otsu thresholding
    5. Denoise
    """
    if not CV2_AVAILABLE:
        return image

    # Convert to grayscale
    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    else:
        gray = image.copy()

    # CLAHE contrast enhancement
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)

    # Remove grid lines
    gray = remove_grid_lines(gray)

    # Otsu thresholding
    _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # Denoise
    try:
        bw = cv2.fastNlMeansDenoising(bw, None, h=10, templateWindowSize=7, searchWindowSize=21)
    except cv2.error:
        pass  # Skip denoising if it fails

    return bw


class VoteExtractor:
    """
    Extract vote counts from Thai election ballot forms.

    Uses techniques from the Klaijan/th-election-2026 project:
    - Column extraction
    - Grid line removal
    - Digit-only OCR
    """

    def __init__(self, dpi: int = 200):
        """
        Initialize the vote extractor.

        Args:
            dpi: DPI to use for PDF rendering (default 200, recommended range 150-400)
        """
        self.dpi = dpi
        self._check_dependencies()

    def _check_dependencies(self) -> None:
        """Check that required dependencies are available."""
        if not CV2_AVAILABLE:
            print("Warning: OpenCV not available. Some features disabled.")
        if not TESSERACT_AVAILABLE:
            print("Warning: Tesseract not available. OCR will not work.")

    def extract_votes_from_image(self, image_path: str) -> VoteExtractionResult:
        """
        Extract vote counts from an image file.

        Args:
            image_path: Path to the ballot image

        Returns:
            VoteExtractionResult with extracted votes
        """
        if not CV2_AVAILABLE or not TESSERACT_AVAILABLE:
            return VoteExtractionResult(
                votes=[],
                total_votes=0,
                column_detected=False,
                grid_removed=False,
                dpi_used=self.dpi,
                error="Missing dependencies"
            )

        try:
            # Load image
            img = cv2.imread(image_path)
            if img is None:
                return VoteExtractionResult(
                    votes=[], total_votes=0, column_detected=False,
                    grid_removed=False, dpi_used=self.dpi,
                    error=f"Could not load image: {image_path}"
                )

            # Extract last column
            column = extract_last_column(img)
            column_detected = column.size > 0

            # Preprocess
            processed = preprocess_for_digits(column)
            grid_removed = True

            # Save temp file for Tesseract
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                cv2.imwrite(tmp.name, processed)
                tmp_path = tmp.name

            # OCR with digit-only config
            text = pytesseract.image_to_string(
                tmp_path,
                lang="eng",
                config=DIGIT_CONFIG
            )

            os.unlink(tmp_path)

            # Parse results
            votes = self._parse_vote_text(text)

            return VoteExtractionResult(
                votes=votes,
                total_votes=sum(v.votes for v in votes),
                column_detected=column_detected,
                grid_removed=grid_removed,
                dpi_used=self.dpi
            )

        except Exception as e:
            return VoteExtractionResult(
                votes=[], total_votes=0, column_detected=False,
                grid_removed=False, dpi_used=self.dpi,
                error=str(e)
            )

    def _parse_vote_text(self, text: str) -> List[VoteEntry]:
        """
        Parse OCR text into vote entries.

        Handles both position:number format and standalone numbers.
        """
        votes = []
        lines = text.strip().split('\n')

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Convert Thai numerals
            line = thai_to_arabic(line)

            # Try position:number format
            match = re.match(r'^(\d{1,2})\s*[:\.\-]?\s*(\d+)$', line)
            if match:
                pos = int(match.group(1))
                count = int(match.group(2))
                if 1 <= pos <= 100 and 0 <= count <= 10000:
                    votes.append(VoteEntry(
                        position=pos,
                        votes=count,
                        raw_text=line
                    ))
                continue

            # Try standalone number
            if line.isdigit():
                count = int(line)
                if 0 <= count <= 10000:
                    # Assign to next position
                    pos = len(votes) + 1
                    votes.append(VoteEntry(
                        position=pos,
                        votes=count,
                        raw_text=line
                    ))

        return votes

    def extract_votes(self, image_path: str) -> dict[int, int]:
        """
        Simple interface: extract votes as a dictionary.

        Args:
            image_path: Path to the ballot image

        Returns:
            Dictionary mapping position to vote count
        """
        result = self.extract_votes_from_image(image_path)
        return {v.position: v.votes for v in result.votes}


def main():
    """Test the vote extractor."""
    import sys

    print("=== Vote Extractor Test ===")
    print()

    if len(sys.argv) < 2:
        print("Usage: python vote_extractor.py <image_path>")
        print()
        print("Testing with sample image...")

        # Try to find a test image
        test_paths = [
            "test_images/page-1.png",
            "ballots/Phrae/เขตเลือกตั้งที่ 1 จังหวัดแพร่/ล่วงหน้านอกเขตและนอกราชอาณาจักร/ชุดที่ 10/สส.5ทับ17ชุดที่10.pdf"
        ]

        for path in test_paths:
            if os.path.exists(path):
                print(f"Found: {path}")

                # If PDF, convert first
                if path.endswith('.pdf'):
                    print("(PDF conversion needed - use ballot_extraction.py)")
                    continue

                extractor = VoteExtractor()
                result = extractor.extract_votes_from_image(path)

                print(f"Column detected: {result.column_detected}")
                print(f"Grid removed: {result.grid_removed}")
                print(f"DPI: {result.dpi_used}")
                print(f"Votes found: {len(result.votes)}")

                if result.votes:
                    print("Vote entries:")
                    for v in result.votes[:10]:
                        print(f"  Position {v.position}: {v.votes} votes")
                break
        return

    # Process provided image
    image_path = sys.argv[1]

    extractor = VoteExtractor()
    result = extractor.extract_votes_from_image(image_path)

    print(f"Image: {image_path}")
    print(f"Column detected: {result.column_detected}")
    print(f"Grid removed: {result.grid_removed}")
    print(f"Votes found: {len(result.votes)}")
    print(f"Total votes: {result.total_votes}")

    if result.error:
        print(f"Error: {result.error}")

    if result.votes:
        print("\nVote entries:")
        for v in result.votes:
            print(f"  Position {v.position}: {v.votes} votes (raw: '{v.raw_text}')")


if __name__ == "__main__":
    main()
