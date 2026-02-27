#!/usr/bin/env python3
"""Unit tests for verify_with_ect_data ECT reference verification."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import ballot_ocr
from ballot_ocr import BallotData, verify_with_ect_data


class FakeEctData:
    """Deterministic fake ECT dataset for verification tests."""

    def validate_province_name(self, thai_name):
        if thai_name == "แพร่":
            return True, "แพร่"
        return False, None

    def get_province_abbr(self, thai_name):
        return "PHR" if thai_name == "แพร่" else None

    def get_constituency(self, cons_id):
        if cons_id == "PHR_1":
            return SimpleNamespace(total_vote_stations=3)
        return None

    def get_candidate_by_thai_province(self, thai_province, constituency_no, position):
        if thai_province == "แพร่" and constituency_no == 1 and position == 1:
            return SimpleNamespace(mp_app_name="นางสาวชนกนันท์ ศุภศิริ", mp_app_party_id=1)
        return None

    def get_party_for_candidate(self, candidate):
        return SimpleNamespace(abbr="ภท.")

    def get_party_by_number(self, party_no):
        if party_no == 1:
            return SimpleNamespace(name="ภูมิใจไทย", abbr="ภท.")
        return None

    def get_official_constituency_results(self, cons_id):
        if cons_id == "PHR_1":
            return {
                "vote_counts": {1: 153},
                "party_votes": {1: 80},
                "total": 155,
            }
        return None


class VerifyWithEctDataTests(unittest.TestCase):
    def setUp(self):
        self.fake_ect = FakeEctData()

    def test_constituency_reference_success(self):
        ballot = BallotData(
            form_type="ส.ส. 5/16",
            form_category="constituency",
            province="แพร่",
            constituency_number=1,
            polling_unit=2,
            polling_station_id="แพร่-1-2",
            vote_counts={1: 153},
            candidate_info={1: {"name": "นางสาวชนกนันท์ ศุภศิริ", "party_abbr": "ภท."}},
            total_votes=155,
            valid_votes=153,
            invalid_votes=2,
            blank_votes=0,
        )

        with patch.object(ballot_ocr, "ECT_AVAILABLE", True), patch.object(ballot_ocr, "ect_data", self.fake_ect):
            result = verify_with_ect_data(ballot, "")

        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["summary"]["high_severity"], 0)
        self.assertEqual(result["summary"]["medium_severity"], 0)
        self.assertEqual(result["summary"]["low_severity"], 0)
        self.assertGreater(result["summary"]["matches"], 0)
        self.assertIn("1", result["ect_data"]["candidate_info"])

    def test_party_list_detects_reference_issues(self):
        ballot = BallotData(
            form_type="ส.ส. 5/16 (บช)",
            form_category="party_list",
            province="แพร่",
            constituency_number=1,
            polling_unit=5,  # greater than known total_vote_stations=3
            polling_station_id="แพร่-1-5",
            party_votes={"999": 10},
            total_votes=12,
            valid_votes=10,
            invalid_votes=1,
            blank_votes=1,
        )

        with patch.object(ballot_ocr, "ECT_AVAILABLE", True), patch.object(ballot_ocr, "ect_data", self.fake_ect):
            result = verify_with_ect_data(ballot, "")

        self.assertEqual(result["status"], "discrepancies_found_high")
        discrepancy_types = {d["type"] for d in result["discrepancies"]}
        self.assertIn("polling_unit_range", discrepancy_types)
        self.assertIn("party_reference_missing", discrepancy_types)


if __name__ == "__main__":
    unittest.main()
