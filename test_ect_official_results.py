#!/usr/bin/env python3
"""Unit tests for official ECT stats parsing."""

import unittest
from unittest.mock import patch

from ect_api import ECTData, ECT_ENDPOINTS


class OfficialResultsTests(unittest.TestCase):
    def test_parse_constituency_results(self):
        provinces_payload = {
            "province": [
                {
                    "province_id": "1",
                    "prov_id": "PHR",
                    "province": "แพร่",
                    "abbre_thai": "พร.",
                    "eng": "Phrae",
                    "total_vote_stations": 3,
                    "total_registered_vote": 1000,
                }
            ]
        }
        party_overview_payload = [
            {
                "id": "129",
                "party_no": "1",
                "name": "ภูมิใจไทย",
                "abbr": "ภท.",
                "color": "#ffffff",
                "logo_url": "",
            }
        ]
        constituencies_payload = [
            {"cons_id": "PHR_1", "cons_no": 1, "prov_id": "PHR", "total_vote_stations": 3}
        ]
        stats_cons_payload = {
            "result_province": [
                {
                    "prov_id": "PHR",
                    "constituencies": [
                        {
                            "cons_id": "PHR_1",
                            "turn_out": 155,
                            "valid_votes": 153,
                            "invalid_votes": 2,
                            "blank_votes": 0,
                            "counted_vote_stations": 3,
                            "percent_count": 100.0,
                            "candidates": [
                                {
                                    "mp_app_id": "PHR_1_1",
                                    "mp_app_vote": 153,
                                }
                            ],
                            "result_party": [
                                {
                                    "party_id": 129,
                                    "party_list_vote": 80,
                                }
                            ],
                        }
                    ],
                }
            ]
        }
        stats_party_payload = {
            "result_party": [
                {
                    "party_id": 129,
                    "party_vote": 999,
                    "party_vote_percent": 10.5,
                    "party_list_count": 1,
                    "mp_app_vote": 888,
                    "mp_app_vote_percent": 9.2,
                }
            ]
        }

        def fake_fetch(url):
            if url == ECT_ENDPOINTS["provinces"]:
                return provinces_payload
            if url == ECT_ENDPOINTS["party_overview"]:
                return party_overview_payload
            if url == ECT_ENDPOINTS["constituencies"]:
                return constituencies_payload
            if url == ECT_ENDPOINTS["stats_cons"]:
                return stats_cons_payload
            if url == ECT_ENDPOINTS["stats_party"]:
                return stats_party_payload
            raise AssertionError(f"Unexpected URL: {url}")

        ect = ECTData()
        with patch("ect_api.fetch_json", side_effect=fake_fetch):
            official = ect.get_official_constituency_results("PHR_1")
            self.assertIsNotNone(official)
            self.assertEqual(official["vote_counts"], {1: 153})
            self.assertEqual(official["party_votes"], {1: 80})
            self.assertEqual(official["total"], 155)

            party = ect.get_official_party_results(1)
            self.assertIsNotNone(party)
            self.assertEqual(party["party_id"], 129)
            self.assertEqual(party["party_vote"], 999)


if __name__ == "__main__":
    unittest.main()
