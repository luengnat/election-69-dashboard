#!/usr/bin/env python3
"""
Integration tests for Thai Election Ballot OCR.

Tests the full pipeline from image processing to report generation.
Run with: python tests/test_integration.py
"""

import os
import sys
import json
import tempfile
import unittest
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestImageProcessing(unittest.TestCase):
    """Test image processing and encoding."""

    def test_encode_image(self):
        """Test base64 image encoding."""
        from ballot_extraction import encode_image

        # Use a test image if available
        test_image = "test_images/high_res_page-1.png"
        if os.path.exists(test_image):
            encoded = encode_image(test_image)
            self.assertIsInstance(encoded, str)
            self.assertTrue(len(encoded) > 0)
            # Verify it's valid base64
            import base64
            decoded = base64.b64decode(encoded)
            self.assertTrue(len(decoded) > 0)

    def test_encode_nonexistent_image(self):
        """Test encoding a non-existent image raises error."""
        from ballot_extraction import encode_image

        with self.assertRaises(FileNotFoundError):
            encode_image("nonexistent_image.png")


class TestPDFConversion(unittest.TestCase):
    """Test PDF to image conversion."""

    def test_pdftoppm_available(self):
        """Check if pdftoppm is available on the system."""
        import shutil
        # This is informational, not a hard requirement
        available = shutil.which("pdftoppm") is not None
        print(f"\n  pdftoppm available: {available}")

    def test_pdf_conversion_invalid_pdf(self):
        """Test PDF conversion with non-existent PDF."""
        from ballot_extraction import pdf_to_images

        # Non-existent PDF should raise FileNotFoundError
        with self.assertRaises(FileNotFoundError):
            pdf_to_images("nonexistent.pdf", "/tmp")

    def test_pdf_conversion_invalid_output_dir(self):
        """Test PDF conversion with non-existent output directory."""
        from ballot_extraction import pdf_to_images
        import tempfile

        # Create a temporary PDF file
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"%PDF-1.4\n")  # Minimal PDF header
            temp_pdf = f.name

        try:
            # Non-existent output directory should raise NotADirectoryError
            with self.assertRaises(NotADirectoryError):
                pdf_to_images(temp_pdf, "/nonexistent/directory")
        finally:
            os.unlink(temp_pdf)

    def test_pdf_conversion_invalid_dpi(self):
        """Test PDF conversion with invalid DPI value."""
        from ballot_extraction import pdf_to_images
        import tempfile

        # Create a temporary PDF file
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"%PDF-1.4\n")  # Minimal PDF header
            temp_pdf = f.name

        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                # DPI out of range should raise ValueError
                with self.assertRaises(ValueError):
                    pdf_to_images(temp_pdf, temp_dir, dpi=10)  # Too low

                with self.assertRaises(ValueError):
                    pdf_to_images(temp_pdf, temp_dir, dpi=1000)  # Too high
            finally:
                os.unlink(temp_pdf)


class TestFormDetection(unittest.TestCase):
    """Test form type detection."""

    def test_path_based_detection(self):
        """Test form type detection from file paths."""
        from crop_utils import detect_form_type_from_path
        from ballot_types import FormType

        # Test various path patterns
        test_cases = [
            ("/path/to/(บช)/5ทับ18/image.png", FormType.S5_18_BCH),
            ("/path/to/(บช)/5/16/ballot.png", FormType.S5_16_BCH),
            ("/path/to/ล่วงหน้าในเขต/form.png", FormType.S5_16),
            ("/path/to/หน่วยเลือกตั้ง/page.png", FormType.S5_18),
            ("/ambiguous/path/image.png", None),
        ]

        for path, expected in test_cases:
            result = detect_form_type_from_path(path)
            self.assertEqual(result, expected, f"Path: {path}")


class TestOCRExtraction(unittest.TestCase):
    """Test OCR extraction pipeline."""

    @classmethod
    def setUpClass(cls):
        """Set up test fixtures."""
        cls.test_image = "test_images/high_res_page-1.png"
        cls.has_test_image = os.path.exists(cls.test_image)

    def test_tesseract_available(self):
        """Check if Tesseract OCR is available."""
        from tesseract_ocr import is_available, check_tesseract_installed

        available = is_available()
        installed, version = check_tesseract_installed()
        print(f"\n  Tesseract available: {available}")
        print(f"  Tesseract version: {version}")

    def test_tesseract_extraction(self):
        """Test Tesseract OCR extraction."""
        if not self.has_test_image:
            self.skipTest("No test image available")

        from ballot_extraction import extract_with_tesseract

        result = extract_with_tesseract(self.test_image)

        # Tesseract may or may not succeed depending on installation
        if result is not None:
            self.assertIsInstance(result.vote_counts, dict)
            self.assertTrue(hasattr(result, 'form_type'))

    def test_extraction_fallback_chain(self):
        """Test that extraction fallback chain works."""
        if not self.has_test_image:
            self.skipTest("No test image available")

        # Temporarily remove API keys to force Tesseract fallback
        old_openrouter = os.environ.pop("OPENROUTER_API_KEY", None)
        old_anthropic = os.environ.pop("ANTHROPIC_API_KEY", None)

        try:
            from ballot_extraction import extract_ballot_data_with_ai

            result = extract_ballot_data_with_ai(self.test_image)

            # Should eventually succeed via Tesseract or return None
            if result is not None:
                self.assertIsInstance(result.vote_counts, dict)
        finally:
            # Restore environment
            if old_openrouter:
                os.environ["OPENROUTER_API_KEY"] = old_openrouter
            if old_anthropic:
                os.environ["ANTHROPIC_API_KEY"] = old_anthropic


class TestDataProcessing(unittest.TestCase):
    """Test data processing and validation."""

    def test_thai_numeral_conversion(self):
        """Test Thai numeral to Arabic conversion."""
        from ballot_types import convert_thai_numerals

        test_cases = [
            ("๑๒๓", "123"),
            ("๐๐๑", "001"),
            ("๑๐๐", "100"),
            ("abc", "abc"),  # Non-Thai passes through
            ("๑๒abc๓", "12abc3"),  # Mixed
        ]

        for thai, expected in test_cases:
            result = convert_thai_numerals(thai)
            self.assertEqual(result, expected)

    def test_vote_entry_validation(self):
        """Test vote entry validation."""
        from ballot_types import validate_vote_entry

        # Matching numeric and Thai text
        entry = validate_vote_entry(100, "หนึ่งร้อย")
        self.assertTrue(entry.is_validated)

        # Non-matching (should still create entry but marked as not validated)
        entry = validate_vote_entry(100, "ห้าสิบ")
        self.assertFalse(entry.is_validated)

    def test_ballot_data_creation(self):
        """Test BallotData creation and serialization."""
        from ballot_types import BallotData

        ballot = BallotData(
            form_type="ส.ส. 5/18",
            form_category="constituency",
            province="สุโขทัย",
            constituency_number=2,
            district="เมืองสุโขทัย",
            polling_unit=1,
            polling_station_id="สุโขทัย-เขต 2 เมืองสุโขทัย-1",
            vote_counts={1: 100, 2: 50},
            vote_details={},
            party_votes={},
            party_details={},
            total_votes=150,
            valid_votes=150,
            invalid_votes=0,
            blank_votes=0,
            source_file="test.png",
            confidence_score=0.95,
            confidence_details={"level": "HIGH"},
        )

        self.assertEqual(ballot.total_votes, 150)
        self.assertEqual(ballot.form_type, "ส.ส. 5/18")


class TestReportGeneration(unittest.TestCase):
    """Test report generation."""

    def test_markdown_report_generation(self):
        """Test markdown report generation."""
        from ballot_reporting import generate_single_ballot_report
        from ballot_types import BallotData

        ballot = BallotData(
            form_type="ส.ส. 5/18",
            form_category="constituency",
            province="สุโขทัย",
            constituency_number=2,
            district="เมืองสุโขทัย",
            polling_unit=1,
            polling_station_id="test-station",
            vote_counts={1: 100, 2: 50},
            vote_details={},
            party_votes={},
            party_details={},
            total_votes=150,
            valid_votes=150,
            invalid_votes=0,
            blank_votes=0,
            source_file="test.png",
            confidence_score=0.95,
            confidence_details={"level": "HIGH"},
        )

        report = generate_single_ballot_report(ballot)

        self.assertIn("สุโขทัย", report)
        self.assertIn("ส.ส. 5/18", report)
        self.assertIn("100", report)


class TestBatchProcessing(unittest.TestCase):
    """Test batch processing functionality."""

    def test_batch_processor_initialization(self):
        """Test BatchProcessor can be initialized."""
        from batch_processor import BatchProcessor

        processor = BatchProcessor(max_workers=2, rate_limit=1.0)
        self.assertEqual(processor.max_workers, 2)
        self.assertEqual(processor.rate_limit, 1.0)


class TestMetadataParser(unittest.TestCase):
    """Test path metadata parsing."""

    def test_province_extraction(self):
        """Test province extraction from paths."""
        from metadata_parser import PathMetadataParser

        parser = PathMetadataParser()

        test_cases = [
            ("จังหวัดสุโขทัย/ballot.png", "สุโขทัย"),
            ("จังหวัดเชียงใหม่/forms/page1.png", "เชียงใหม่"),
            ("bangkok/forms/ballot.png", None),  # No Thai prefix
        ]

        for path, expected_province in test_cases:
            metadata = parser.parse_path(path)
            if expected_province:
                self.assertEqual(metadata.province, expected_province, f"Path: {path}")
            else:
                self.assertIsNone(metadata.province)


def run_tests():
    """Run all integration tests."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestImageProcessing))
    suite.addTests(loader.loadTestsFromTestCase(TestPDFConversion))
    suite.addTests(loader.loadTestsFromTestCase(TestFormDetection))
    suite.addTests(loader.loadTestsFromTestCase(TestOCRExtraction))
    suite.addTests(loader.loadTestsFromTestCase(TestDataProcessing))
    suite.addTests(loader.loadTestsFromTestCase(TestReportGeneration))
    suite.addTests(loader.loadTestsFromTestCase(TestBatchProcessing))
    suite.addTests(loader.loadTestsFromTestCase(TestMetadataParser))

    # Run with verbosity
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(run_tests())
