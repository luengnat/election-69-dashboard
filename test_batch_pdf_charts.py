#!/usr/bin/env python3
"""Test batch PDF generation with charts."""

import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ballot_ocr import BallotData, generate_batch_pdf, aggregate_ballot_results


def create_sample_ballot_data():
    """Create sample ballot data for testing."""
    ballots = []

    # Create multiple ballots with varying confidence levels
    test_data = [
        {"province": "แพร่", "cons_no": 1, "confidence": 0.95, "level": "EXCELLENT", "valid": 296},
        {"province": "แพร่", "cons_no": 2, "confidence": 0.92, "level": "GOOD", "valid": 307},
        {"province": "เชียงใหม่", "cons_no": 1, "confidence": 0.88, "level": "GOOD", "valid": 250},
        {"province": "เชียงราย", "cons_no": 3, "confidence": 0.75, "level": "ACCEPTABLE", "valid": 180},
        {"province": "เชียงราย", "cons_no": 4, "confidence": 0.65, "level": "ACCEPTABLE", "valid": 195},
        {"province": "นครราชสีมา", "cons_no": 6, "confidence": 0.50, "level": "POOR", "valid": 107},
        {"province": "สุโขทัย", "cons_no": 2, "confidence": 0.35, "level": "POOR", "valid": 202},
        {"province": "พัทลุง", "cons_no": 2, "confidence": 0.25, "level": "VERY_LOW", "valid": 150},
    ]

    for i, data in enumerate(test_data, 1):
        ballot = BallotData(
            form_type="ส.ส. 5/16",
            form_category="constituency",
            province=data["province"],
            constituency_number=data["cons_no"],
            polling_unit=i,
            polling_station_id=f"{data['province']}-{data['cons_no']}-{i}",
            valid_votes=data["valid"],
            invalid_votes=5,
            blank_votes=2,
            total_votes=data["valid"] + 7,
            vote_counts={1: data["valid"] // 2, 2: data["valid"] // 3, 3: data["valid"] // 6},
            source_file=f"test_{i}.png",
            confidence_score=data["confidence"],
            confidence_details={"level": data["level"], "score": data["confidence"]},
        )
        ballots.append(ballot)

    return ballots


def test_batch_pdf_with_charts():
    """Test batch PDF generation with charts."""
    print("Testing batch PDF with charts...")

    # Check if reportlab is available
    try:
        from reportlab.graphics.charts.barcharts import VerticalBarChart
        print("✓ reportlab with charts support available")
    except ImportError:
        print("✗ reportlab chart support not available")
        return False

    # Create sample data
    ballots = create_sample_ballot_data()
    print(f"✓ Created {len(ballots)} sample ballots")

    # Aggregate results
    aggregated = aggregate_ballot_results(ballots)
    print(f"✓ Aggregated into {len(aggregated)} constituencies")

    # Generate PDF
    output_path = "reports_test/test_batch_with_charts.pdf"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    success = generate_batch_pdf(aggregated, ballots, output_path)

    if success and os.path.exists(output_path):
        file_size = os.path.getsize(output_path)
        print(f"✓ Batch PDF with charts generated: {output_path} ({file_size} bytes)")
        return True
    else:
        print("✗ Failed to generate batch PDF with charts")
        return False


if __name__ == "__main__":
    if test_batch_pdf_with_charts():
        print("\n✓ Test passed!")
        sys.exit(0)
    else:
        print("\n✗ Test failed")
        sys.exit(1)
