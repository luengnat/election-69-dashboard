#!/usr/bin/env python3
"""Test executive summary PDF generation."""

import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ballot_ocr import AggregatedResults, generate_executive_summary_pdf, detect_anomalous_constituencies


def create_sample_aggregated_results():
    """Create sample aggregated results for testing."""
    results = []

    # Sample constituency results
    sample_data = [
        {"province": "แพร่", "cons_no": 1, "valid": 780, "invalid": 15, "blank": 5, "confidence": 0.95,
         "candidates": {1: 350, 2: 280, 3: 150}, "winners": [{"name": "Candidate A", "votes": 350, "percentage": 44.87}]},
        {"province": "แพร่", "cons_no": 2, "valid": 650, "invalid": 10, "blank": 3, "confidence": 0.92,
         "candidates": {1: 300, 2: 250, 3: 100}, "winners": [{"name": "Candidate B", "votes": 300, "percentage": 46.15}]},
        {"province": "เชียงใหม่", "cons_no": 1, "valid": 890, "invalid": 20, "blank": 8, "confidence": 0.88,
         "candidates": {1: 450, 2: 300, 3: 140}, "winners": [{"name": "Candidate C", "votes": 450, "percentage": 50.56}]},
        {"province": "เชียงราย", "cons_no": 3, "valid": 520, "invalid": 8, "blank": 2, "confidence": 0.75,
         "candidates": {1: 280, 2: 160, 3: 80}, "winners": [{"name": "Candidate D", "votes": 280, "percentage": 53.85}]},
        {"province": "นครราชสีมา", "cons_no": 6, "valid": 1100, "invalid": 25, "blank": 10, "confidence": 0.82,
         "candidates": {1: 550, 2: 400, 3: 150}, "winners": [{"name": "Candidate E", "votes": 550, "percentage": 50.00}]},
    ]

    for data in sample_data:
        agg = AggregatedResults(
            province=data["province"],
            constituency=f"{data['province']} District {data['cons_no']}",
            constituency_no=data["cons_no"],
            candidate_totals=data["candidates"],
            candidate_info={pos: {"name": f"Candidate {pos}", "party_abbr": "XYZ"} for pos in data["candidates"]},
            valid_votes_total=data["valid"],
            invalid_votes_total=data["invalid"],
            blank_votes_total=data["blank"],
            overall_total=data["valid"] + data["invalid"] + data["blank"],
            aggregated_confidence=data["confidence"],
            ballots_processed=1,
            winners=data["winners"],
            turnout_rate=65.0,
            discrepancy_rate=0.0,
            source_ballots=[f"ballot_{data['province']}_{data['cons_no']}.png"],
            form_types=["ส.ส. 5/16"],
        )
        results.append(agg)

    return results


def test_executive_summary_pdf():
    """Test executive summary PDF generation."""
    print("Testing executive summary PDF...")

    # Check if reportlab is available
    try:
        from reportlab.graphics.charts.barcharts import VerticalBarChart
        print("✓ reportlab available")
    except ImportError:
        print("✗ reportlab not installed")
        return False

    # Create sample data
    results = create_sample_aggregated_results()
    print(f"✓ Created {len(results)} sample aggregated results")

    # Detect anomalies
    results_dict = {(r.province, r.constituency_no): r for r in results}
    anomalies = detect_anomalous_constituencies(results_dict)
    print(f"✓ Detected {len(anomalies)} anomalies")

    # Generate PDF
    output_path = "reports_test/test_executive_summary.pdf"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    success = generate_executive_summary_pdf(results, anomalies, output_path)

    if success and os.path.exists(output_path):
        file_size = os.path.getsize(output_path)
        print(f"✓ Executive Summary PDF generated: {output_path} ({file_size} bytes)")
        return True
    else:
        print("✗ Failed to generate executive summary PDF")
        return False


if __name__ == "__main__":
    if test_executive_summary_pdf():
        print("\n✓ Test passed!")
        sys.exit(0)
    else:
        print("\n✗ Test failed")
        sys.exit(1)
