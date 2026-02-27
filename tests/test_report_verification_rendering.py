#!/usr/bin/env python3
"""Regression tests for report rendering with verification discrepancies."""

import unittest

from ballot_ocr import BallotData, generate_batch_report, generate_single_ballot_report


class ReportVerificationRenderingTests(unittest.TestCase):
    def setUp(self):
        self.ballot = BallotData(
            form_type="ส.ส. 5/16",
            form_category="constituency",
            province="แพร่",
            constituency_number=1,
            district="เมืองแพร่",
            polling_unit=2,
            polling_station_id="แพร่-1-2",
            vote_counts={1: 153},
            valid_votes=153,
            invalid_votes=2,
            blank_votes=0,
            total_votes=155,
            source_file="test.png",
            confidence_score=0.95,
            confidence_details={"level": "HIGH"},
        )

    def test_single_report_renders_generic_discrepancy(self):
        discrepancy_report = {
            "status": "discrepancies_found_high",
            "summary": {"matches": 2, "low_severity": 0, "medium_severity": 0, "high_severity": 1},
            "discrepancies": [
                {
                    "type": "polling_unit_range",
                    "severity": "HIGH",
                    "extracted": 5,
                    "expected": "1-3",
                }
            ],
        }
        report = generate_single_ballot_report(self.ballot, discrepancy_report=discrepancy_report)
        self.assertIn("polling_unit_range", report)
        self.assertIn("1-3", report)

    def test_batch_report_renders_generic_discrepancy(self):
        results = [
            {
                "status": "discrepancies_found_high",
                "polling_station": "แพร่-1-2",
                "discrepancies": [
                    {
                        "type": "province_reference",
                        "severity": "HIGH",
                        "extracted": "แพร๋",
                        "expected": "valid ECT province",
                    }
                ],
            }
        ]
        report = generate_batch_report(results, [self.ballot])
        self.assertIn("province_reference", report)
        self.assertIn("valid ECT province", report)


if __name__ == "__main__":
    unittest.main()
