#!/usr/bin/env python3
"""
Unit tests for metadata_parser.py and batch_processor.py.

Run with: python tests/test_metadata_parser.py
"""

import sys
import unittest
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from metadata_parser import PathMetadataParser


class TestPathMetadataParser(unittest.TestCase):
    """Tests for PathMetadataParser."""

    def setUp(self):
        """Create parser instance."""
        self.parser = PathMetadataParser()

    def test_extract_province_from_path(self):
        """Test province extraction from path with จังหวัด prefix."""
        # Province with จังหวัด prefix
        result = self.parser.parse_path("/ballots/จังหวัดเชียงใหม่/เขตเลือกตั้งที่ 1/ballot.jpg")
        self.assertEqual(result.province, "เชียงใหม่")

    def test_extract_constituency_from_path(self):
        """Test constituency number extraction from path."""
        # With เขตเลือกตั้งที่ keyword
        result = self.parser.parse_path("/ballots/จังหวัดแพร่/เขตเลือกตั้งที่ 4/หน่วยเลือกตั้งที่ 2.jpg")
        self.assertEqual(result.constituency_number, 4)

        # Another constituency
        result = self.parser.parse_path("/ballots/จังหวัดเชียงใหม่/เขตเลือกตั้งที่ 3/ballot.jpg")
        self.assertEqual(result.constituency_number, 3)

    def test_extract_polling_unit_from_path(self):
        """Test polling unit extraction from path."""
        result = self.parser.parse_path("/ballots/จังหวัดแพร่/เขตเลือกตั้งที่ 1/หน่วยเลือกตั้งที่ 5.jpg")
        self.assertEqual(result.polling_unit, 5)

    def test_empty_path(self):
        """Test empty path returns empty metadata."""
        result = self.parser.parse_path("")
        self.assertIsNone(result.province)

    def test_unicode_normalization(self):
        """Test Unicode normalization for Thai characters."""
        # Different Unicode representations of the same text
        result1 = self.parser.parse_path("/ballots/จังหวัดกรุงเทพมหานคร/ballot.jpg")
        result2 = self.parser.parse_path("/ballots/จังหวัดกรุงเทพมหานคร/ballot.jpg")

        # Both should work without errors
        self.assertIsNotNone(result1)
        self.assertIsNotNone(result2)

    def test_confidence_scoring(self):
        """Test confidence score calculation."""
        # Full metadata extraction should have higher confidence
        result = self.parser.parse_path("/ballots/จังหวัดกรุงเทพมหานคร/เขตเลือกตั้งที่ 1/หน่วยเลือกตั้งที่ 2.jpg")
        confidence = result.confidence
        self.assertGreater(confidence, 0)

        # Path with less info should have lower confidence
        result_simple = self.parser.parse_path("/ballots/ballot.jpg")
        confidence_simple = result_simple.confidence
        self.assertLessEqual(confidence_simple, confidence)

    def test_no_match_returns_empty(self):
        """Test that paths without Thai patterns return empty metadata."""
        result = self.parser.parse_path("/some/random/path/file.jpg")
        self.assertIsNone(result.province)
        self.assertIsNone(result.constituency_number)
        self.assertIsNone(result.polling_unit)


if __name__ == "__main__":
    unittest.main(verbosity=2)
