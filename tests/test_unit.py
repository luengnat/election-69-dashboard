#!/usr/bin/env python3
"""
Unit tests for ballot_ocr.py core functions.

Run with: python tests/test_unit.py
"""

import sys
import unittest
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from ballot_ocr import (
    thai_text_to_number,
    validate_vote_entry,
    VoteEntry,
    FormType,
)


class TestThaiTextToNumber(unittest.TestCase):
    """Tests for Thai text to number conversion."""

    def test_single_digits(self):
        """Test single digit Thai numbers."""
        self.assertEqual(thai_text_to_number("ศูนย์"), 0)
        self.assertEqual(thai_text_to_number("หนึ่ง"), 1)
        self.assertEqual(thai_text_to_number("สอง"), 2)
        self.assertEqual(thai_text_to_number("สาม"), 3)
        self.assertEqual(thai_text_to_number("สี่"), 4)
        self.assertEqual(thai_text_to_number("ห้า"), 5)
        self.assertEqual(thai_text_to_number("หก"), 6)
        self.assertEqual(thai_text_to_number("เจ็ด"), 7)
        self.assertEqual(thai_text_to_number("แปด"), 8)
        self.assertEqual(thai_text_to_number("เก้า"), 9)
        self.assertEqual(thai_text_to_number("ศูนย์"), 0)

    def test_tens(self):
        """Test tens place Thai numbers."""
        self.assertEqual(thai_text_to_number("สิบ"), 10)
        self.assertEqual(thai_text_to_number("สิบเอ็ด"), 11)
        self.assertEqual(thai_text_to_number("สิบสอง"), 12)
        self.assertEqual(thai_text_to_number("ยี่สิบ"), 20)
        self.assertEqual(thai_text_to_number("ยี่สิบเอ็ด"), 21)
        self.assertEqual(thai_text_to_number("สามสิบ"), 30)
        self.assertEqual(thai_text_to_number("แปดสิบเก้า"), 89)

    def test_hundreds(self):
        """Test hundreds place Thai numbers."""
        self.assertEqual(thai_text_to_number("หนึ่งร้อย"), 100)
        self.assertEqual(thai_text_to_number("หนึ่งร้อยหนึ่ง"), 101)
        self.assertEqual(thai_text_to_number("สองร้อยห้าสิบ"), 250)
        self.assertEqual(thai_text_to_number("เก้าร้อยเก้าสิบเก้า"), 999)
        self.assertEqual(thai_text_to_number("หนึ่งพัน"), 1000)
        self.assertEqual(thai_text_to_number("สองพันห้าร้อย"), 2500)
        self.assertEqual(thai_text_to_number("สามพันสิบเอ็ด"), 3011)

    def test_invalid_input(self):
        """Test invalid input returns None."""
        self.assertIsNone(thai_text_to_number(""))
        self.assertIsNone(thai_text_to_number("   "))
        self.assertIsNone(thai_text_to_number("abc"))
        self.assertIsNone(thai_text_to_number(None))


class TestVoteEntry(unittest.TestCase):
    """Tests for VoteEntry dataclass and validate_vote_entry function."""

    def test_valid_entry(self):
        """Test creating a valid vote entry."""
        entry = validate_vote_entry(numeric=100, thai_text="หนึ่งร้อย")
        self.assertEqual(entry.numeric, 100)
        self.assertEqual(entry.thai_text, "หนึ่งร้อย")
        self.assertTrue(entry.is_validated)

    def test_mismatch_detection(self):
        """Test that mismatches between numeric and Thai are detected."""
        entry = validate_vote_entry(numeric=100, thai_text="สองร้อย")  # 200, not 100
        self.assertEqual(entry.numeric, 100)
        self.assertFalse(entry.is_validated)


class TestFormType(unittest.TestCase):
    """Tests for FormType enum."""

    def test_party_list_detection(self):
        """Test is_party_list property."""
        self.assertFalse(FormType.S5_16.is_party_list)
        self.assertTrue(FormType.S5_16_BCH.is_party_list)
        self.assertFalse(FormType.S5_17.is_party_list)
        self.assertTrue(FormType.S5_17_BCH.is_party_list)
        self.assertFalse(FormType.S5_18.is_party_list)
        self.assertTrue(FormType.S5_18_BCH.is_party_list)

    def test_expected_candidates(self):
        """Test expected_candidates property."""
        self.assertEqual(FormType.S5_16.expected_candidates, 6)
        self.assertEqual(FormType.S5_16_BCH.expected_candidates, 57)

    def test_form_type_values(self):
        """Test FormType string values."""
        self.assertEqual(FormType.S5_16.value, "ส.ส. 5/16")
        self.assertEqual(FormType.S5_16_BCH.value, "ส.ส. 5/16 (บช)")


class TestBallotData(unittest.TestCase):
    """Tests for BallotData dataclass."""

    def test_repr(self):
        """Test BallotData string representation."""
        from ballot_types import BallotData
        ballot = BallotData(
            form_type="ส.ส. 5/18",
            form_category="constituency",
            province="สุโขทัย",
            total_votes=150,
            confidence_score=0.9578,
            polling_station_id="station-123"
        )
        r = repr(ballot)
        self.assertIn("BallotData", r)
        self.assertIn("'ส.ส. 5/18'", r)
        self.assertIn("total=150", r)
        self.assertIn("confidence=0.96", r)  # Should be formatted to 2 decimals
        self.assertIn("'station-123'", r)

    def test_repr_fallback_to_file(self):
        """Test repr uses source_file if station ID is missing."""
        from ballot_types import BallotData
        ballot = BallotData(
            form_type="ส.ส. 5/16",
            form_category="constituency",
            province="Phrae",
            source_file="ballot.jpg"
        )
        r = repr(ballot)
        self.assertIn("'ballot.jpg'", r)


if __name__ == "__main__":
    unittest.main(verbosity=2)
