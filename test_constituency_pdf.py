#!/usr/bin/env python3
"""Test constituency PDF generation."""

import os
import sys
from dataclasses import dataclass, field

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ballot_ocr import AggregatedResults, generate_constituency_pdf


def test_constituency_pdf_constituency():
    """Test PDF generation for constituency (candidate) results."""
    agg = AggregatedResults(
        province="แพร่",
        constituency="เมืองแพร่",
        constituency_no=1,
        candidate_totals={1: 350, 2: 280, 3: 150},
        candidate_info={
            1: {"name": "นางสาวชนกนันท์ ศุภศิริ", "party_abbr": "PPP"},
            2: {"name": "นางภูวษา สินธุวงศ์", "party_abbr": "PWP"},
            3: {"name": "นายวิตติ แสงสุพรรณ", "party_abbr": "PTP"},
        },
        polling_units_reporting=3,
        total_polling_units=5,
        valid_votes_total=780,
        invalid_votes_total=15,
        blank_votes_total=5,
        overall_total=800,
        aggregated_confidence=0.95,
        ballots_processed=3,
        ballots_with_discrepancies=1,
        winners=[
            {"position": 1, "name": "นางสาวชนกนันท์ ศุภศิริ", "party": "PPP", "votes": 350, "percentage": 44.87},
            {"position": 2, "name": "นางภูวษา สินธุวงศ์", "party": "PWP", "votes": 280, "percentage": 35.90},
        ],
        turnout_rate=60.0,
        discrepancy_rate=0.05,
        source_ballots=["ballot_001.png", "ballot_002.png", "ballot_003.png"],
        form_types=["ส.ส. 5/16"],
    )

    output_path = "reports_test/test_constituency_constituency.pdf"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    success = generate_constituency_pdf(agg, output_path)

    if success and os.path.exists(output_path):
        file_size = os.path.getsize(output_path)
        print(f"✓ Constituency PDF generated: {output_path} ({file_size} bytes)")
        return True
    else:
        print("✗ Failed to generate constituency PDF")
        return False


def test_constituency_pdf_party_list():
    """Test PDF generation for party-list results."""
    agg = AggregatedResults(
        province="แพร่",
        constituency="แพร่ (Party List)",
        constituency_no=0,
        party_totals={"1": 250, "2": 180, "3": 120, "5": 80},
        party_info={
            "1": {"name": "Palang Pracharath Party", "abbr": "PPP"},
            "2": {"name": "Pheu Thai Party", "abbr": "PTP"},
            "3": {"name": "Move Forward Party", "abbr": "MFP"},
            "5": {"name": "Democrat Party", "abbr": "DP"},
        },
        polling_units_reporting=2,
        total_polling_units=5,
        valid_votes_total=630,
        invalid_votes_total=10,
        blank_votes_total=5,
        overall_total=645,
        aggregated_confidence=0.92,
        ballots_processed=2,
        ballots_with_discrepancies=0,
        winners=[
            {"name": "Palang Pracharath Party", "abbr": "PPP", "votes": 250, "percentage": 39.68},
            {"name": "Pheu Thai Party", "abbr": "PTP", "votes": 180, "percentage": 28.57},
        ],
        turnout_rate=55.0,
        discrepancy_rate=0.0,
        source_ballots=["bch_page-1.png", "bch_page-2.png"],
        form_types=["ส.ส. 5/16 (บช)"],
    )

    output_path = "reports_test/test_constituency_party_list.pdf"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    success = generate_constituency_pdf(agg, output_path)

    if success and os.path.exists(output_path):
        file_size = os.path.getsize(output_path)
        print(f"✓ Party-list PDF generated: {output_path} ({file_size} bytes)")
        return True
    else:
        print("✗ Failed to generate party-list PDF")
        return False


if __name__ == "__main__":
    print("Testing constituency PDF generation...")

    # Check if reportlab is available
    try:
        from reportlab.lib.pagesizes import letter
        print("✓ reportlab is installed")
    except ImportError:
        print("✗ reportlab not installed. Run: pip install reportlab")
        sys.exit(1)

    results = []
    results.append(test_constituency_pdf_constituency())
    results.append(test_constituency_pdf_party_list())

    if all(results):
        print("\n✓ All tests passed!")
        sys.exit(0)
    else:
        print("\n✗ Some tests failed")
        sys.exit(1)
