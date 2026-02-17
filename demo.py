#!/usr/bin/env python3
"""
Demo script for Thai Election Ballot OCR.

This script demonstrates the main features of the application without
requiring actual ballot images.

Usage:
    python demo.py
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))


def print_header(title: str):
    """Print a section header."""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def demo_thai_number_conversion():
    """Demonstrate Thai text to number conversion."""
    print_header("Thai Number Conversion")

    from ballot_ocr import thai_text_to_number

    test_cases = [
        ("ศูนย์", 0),
        ("หนึ่ง", 1),
        ("สิบ", 10),
        ("สิบห้า", 15),
        ("ยี่สิบเอ็ด", 21),
        ("หนึ่งร้อย", 100),
        ("สองร้อยห้าสิบ", 250),
        ("เก้าร้อยเก้าสิบเก้า", 999),
    ]

    print("\nConverting Thai text to numbers:")
    for thai, expected in test_cases:
        result = thai_text_to_number(thai)
        status = "✓" if result == expected else "✗"
        print(f"  {status} '{thai}' -> {result} (expected: {expected})")


def demo_vote_validation():
    """Demonstrate vote entry validation."""
    print_header("Vote Entry Validation")

    from ballot_ocr import validate_vote_entry

    print("\nValidating vote entries (numeric vs Thai text):")

    # Valid entry
    entry = validate_vote_entry(numeric=100, thai_text="หนึ่งร้อย")
    print(f"  ✓ 100 vs 'หนึ่งร้อย': validated={entry.is_validated}")

    # Invalid entry (mismatch)
    entry = validate_vote_entry(numeric=100, thai_text="สองร้อย")  # 200
    print(f"  ✗ 100 vs 'สองร้อย': validated={entry.is_validated} (mismatch detected!)")


def demo_form_types():
    """Demonstrate form type detection."""
    print_header("Form Type Detection")

    from ballot_ocr import FormType

    print("\nSupported form types:")
    for form in FormType:
        category = "Party-list" if form.is_party_list else "Constituency"
        candidates = form.expected_candidates
        print(f"  • {form.value}: {category}, {candidates} expected entries")


def demo_metadata_extraction():
    """Demonstrate metadata extraction from paths."""
    print_header("Metadata Extraction from Paths")

    from metadata_parser import PathMetadataParser

    parser = PathMetadataParser()

    test_paths = [
        "/ballots/จังหวัดเชียงใหม่/เขตเลือกตั้งที่ 1/หน่วยเลือกตั้งที่ 5.jpg",
        "/ballots/จังหวัดกรุงเทพมหานคร/เขตเลือกตั้งที่ 10/ballot.jpg",
        "/random/path/image.jpg",
    ]

    print("\nExtracting metadata from file paths:")
    for path in test_paths:
        result = parser.parse_path(path)
        print(f"\n  Path: {path}")
        print(f"    Province: {result.province or 'N/A'}")
        print(f"    Constituency: {result.constituency_number or 'N/A'}")
        print(f"    Polling Unit: {result.polling_unit or 'N/A'}")
        print(f"    Confidence: {result.confidence:.1f}")


def demo_ect_data():
    """Demonstrate ECT data validation."""
    print_header("ECT Data Validation")

    try:
        from ect_api import ect_data

        print("\nValidating provinces:")
        test_provinces = ["กรุงเทพมหานคร", "เชียงใหม่", "ไม่มีจังหวัดนี้"]
        for province in test_provinces:
            is_valid, canonical = ect_data.validate_province_name(province)
            status = "✓" if is_valid else "✗"
            result = canonical if is_valid else "Invalid"
            print(f"  {status} '{province}' -> {result}")

    except Exception as e:
        print(f"\n  ECT data demo failed: {e}")


def demo_pdf_generation():
    """Demonstrate PDF report generation."""
    print_header("PDF Report Generation")

    from ballot_ocr import BallotData

    # Create sample ballot data
    ballot = BallotData(
        form_type="ส.ส. 5/16",
        form_category="constituency",
        province="แพร่",
        constituency_number=1,
        district="เมืองแพร่",
        polling_unit=2,
        vote_counts={1: 100, 2: 50, 3: 30},
        valid_votes=180,
        invalid_votes=5,
        blank_votes=0,
        total_votes=185,
        confidence_score=0.95,
    )

    print("\nSample ballot data:")
    print(f"  Form: {ballot.form_type}")
    print(f"  Province: {ballot.province}")
    print(f"  Constituency: {ballot.constituency_number}")
    print(f"  Total votes: {ballot.total_votes}")
    print(f"  Confidence: {ballot.confidence_score:.0%}")

    # Note: PDF generation requires reportlab
    try:
        from ballot_ocr import generate_ballot_pdf
        import tempfile
        import os

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            temp_path = f.name

        print(f"\n  Generating PDF to: {temp_path}")
        success = generate_ballot_pdf(ballot, temp_path)

        if success and os.path.exists(temp_path):
            size = os.path.getsize(temp_path)
            print(f"  ✓ PDF generated successfully ({size} bytes)")
            os.unlink(temp_path)
        else:
            print("  ✗ PDF generation failed")

    except ImportError:
        print("\n  reportlab not installed. Install with: pip install reportlab")


def demo_configuration():
    """Demonstrate configuration management."""
    print_header("Configuration")

    from config import config

    print("\nCurrent configuration:")
    for key, value in config.to_dict().items():
        print(f"  {key}: {value}")

    issues = config.validate()
    if issues:
        print("\nConfiguration issues:")
        for issue in issues:
            print(f"  ⚠ {issue}")
    else:
        print("\n  ✓ Configuration is valid")


def main():
    """Run all demos."""
    print("\n" + "=" * 70)
    print("  Thai Election Ballot OCR - Feature Demo")
    print("=" * 70)

    demo_thai_number_conversion()
    demo_vote_validation()
    demo_form_types()
    demo_metadata_extraction()
    demo_ect_data()
    demo_pdf_generation()
    demo_configuration()

    print_header("Demo Complete")
    print("\n  For full usage, see:")
    print("    • README.md - Installation and usage guide")
    print("    • python cli.py --help - CLI commands")
    print("    • python web_ui.py - Web interface")
    print()


if __name__ == "__main__":
    main()
