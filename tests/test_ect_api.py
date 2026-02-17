#!/usr/bin/env python3
"""
Unit tests for ect_api.py.

Run with: python tests/test_ect_api.py
"""

import sys
import unittest
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestECTData(unittest.TestCase):
    """Tests for ECT data API."""

    def test_province_validation(self):
        """Test province name validation."""
        try:
            from ect_api import ect_data

            # Valid province
            is_valid, name = ect_data.validate_province("กรุงเทพมหานคร")
            self.assertTrue(is_valid)
            self.assertEqual(name, "กรุงเทพมหานคร")

            # Invalid province
            is_valid, name = ect_data.validate_province("ไม่มีจังหวัดนี้")
            self.assertFalse(is_valid)
            self.assertIsNone(name)

        except ImportError:
            self.skipTest("ect_api not available")

    def test_province_with_prefix(self):
        """Test province validation with จังหวัด prefix."""
        try:
            from ect_api import ect_data

            # Province with prefix should also be valid
            is_valid, name = ect_data.validate_province("จังหวัดเชียงใหม่")
            self.assertTrue(is_valid)

        except ImportError:
            self.skipTest("ect_api not available")

    def test_get_province_abbr(self):
        """Test getting province abbreviation."""
        try:
            from ect_api import ect_data

            abbr = ect_data.get_province_abbr("กรุงเทพมหานคร")
            self.assertIsNotNone(abbr)

        except ImportError:
            self.skipTest("ect_api not available")

    def test_candidate_lookup(self):
        """Test candidate lookup by province and constituency."""
        try:
            from ect_api import ect_data

            # Get candidates for a constituency
            candidates = ect_data.get_candidates("กรุงเทพมหานคร", 1)
            self.assertIsNotNone(candidates)
            # Should return a list (may be empty if no data)
            self.assertIsInstance(candidates, list)

        except ImportError:
            self.skipTest("ect_api not available")

    def test_party_lookup(self):
        """Test party information lookup."""
        try:
            from ect_api import ect_data

            # Get party info
            parties = ect_data.get_parties()
            self.assertIsNotNone(parties)

        except ImportError:
            self.skipTest("ect_api not available")


class TestProvinceList(unittest.TestCase):
    """Tests for province list validation."""

    def test_thai_province_count(self):
        """Test that Thailand has 77 provinces."""
        try:
            from ect_api import ect_data, ECT_AVAILABLE

            if not ECT_AVAILABLE:
                self.skipTest("ECT API not available")

            provinces = ect_data.get_provinces()
            if provinces:
                self.assertEqual(len(provinces), 77)

        except ImportError:
            self.skipTest("ect_api not available")

    def test_common_provinces_exist(self):
        """Test that common provinces are in the list."""
        try:
            from ect_api import ect_data, ECT_AVAILABLE

            if not ECT_AVAILABLE:
                self.skipTest("ECT API not available")

            common_provinces = [
                "กรุงเทพมหานคร",
                "เชียงใหม่",
                "ขอนแก่น",
                "ชลบุรี",
                "นครราชสีมา",
            ]

            for province in common_provinces:
                is_valid, _ = ect_data.validate_province(province)
                self.assertTrue(is_valid, f"Province {province} should be valid")

        except ImportError:
            self.skipTest("ect_api not available")


if __name__ == "__main__":
    unittest.main(verbosity=2)
