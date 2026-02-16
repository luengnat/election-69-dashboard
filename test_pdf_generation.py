#!/usr/bin/env python3
"""
Test PDF generation for Phase 4.1 implementation.
"""

import json
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from ballot_ocr import BallotData, generate_ballot_pdf, generate_batch_pdf, HAS_REPORTLAB


def test_pdf_generation():
    """Test PDF generation with mock data."""
    
    if not HAS_REPORTLAB:
        print("⚠ reportlab not installed. Install with: pip install reportlab")
        return False
    
    print("Testing PDF Generation (Phase 4.1)...")
    print("=" * 70)
    
    # Create sample ballot data
    ballot_data = BallotData(
        form_type="ส.ส. 5/16",
        form_category="constituency",
        province="แพร่",
        constituency_number=1,
        district="เมืองแพร่",
        polling_unit=2,
        polling_station_id="แพร่-เขต 1 เมืองแพร่-2",
        form_code="5/16",
        image_encoding="",
        ai_response="test",
        source_file="test.png",
        vote_counts={1: 100, 2: 50, 3: 30},
        valid_votes=180,
        invalid_votes=5,
        blank_votes=0,
        total_votes=185,
        confidence_score=0.98,
        confidence_details={
            "level": "EXCELLENT",
            "thai_text_validation": 1.0,
            "sum_validation": 1.0,
            "province_validation": 0.95,
            "details": []
        },
        candidate_info={
            "1": {
                "name": "นางสาวชนกนันท์ ศุภศิริ",
                "party_name": "ภูมิใจไทย",
                "party_abbr": "ภท.",
                "party_number": "1"
            },
            "2": {
                "name": "นางภูวษา สินธุวงศ์",
                "party_name": "ภูมิใจไทย",
                "party_abbr": "ภท.",
                "party_number": "1"
            },
            "3": {
                "name": "นายวิตติ แสงสุพรรณ",
                "party_name": "เพื่อไทย",
                "party_abbr": "เพท.",
                "party_number": "2"
            }
        },
        party_votes={},
        party_info={},
        page_parties=[],
        discrepancies={},
    )
    
    # Test single ballot PDF
    print("\n1. Testing Single Ballot PDF Generation...")
    output_path = "test_reports/test_ballot.pdf"
    Path("test_reports").mkdir(exist_ok=True)
    
    success = generate_ballot_pdf(ballot_data, output_path)
    
    if success:
        # Check file was created
        if Path(output_path).exists():
            file_size = Path(output_path).stat().st_size
            print(f"   ✓ Single ballot PDF created: {file_size} bytes")
        else:
            print("   ✗ PDF file not created")
            return False
    else:
        print("   ✗ Failed to generate single ballot PDF")
        return False
    
    # Test batch PDF
    print("\n2. Testing Batch PDF Generation...")
    ballot_data_list = [ballot_data for _ in range(3)]
    aggregated = {}
    batch_output = "test_reports/test_batch.pdf"
    
    success = generate_batch_pdf(aggregated, ballot_data_list, batch_output)
    
    if success:
        if Path(batch_output).exists():
            file_size = Path(batch_output).stat().st_size
            print(f"   ✓ Batch PDF created: {file_size} bytes")
        else:
            print("   ✗ Batch PDF file not created")
            return False
    else:
        print("   ✗ Failed to generate batch PDF")
        return False
    
    # Test party-list form PDF
    print("\n3. Testing Party-List Form PDF...")
    party_ballot = BallotData(
        form_type="ส.ส. 5/16 (บช)",
        form_category="party_list",
        province="นนทบุรี",
        constituency_number=0,
        district="",
        polling_unit=1,
        polling_station_id="นนทบุรี-ปทุมธานี",
        form_code="5/16",
        image_encoding="",
        ai_response="test",
        source_file="party_list.png",
        vote_counts={},
        valid_votes=150,
        invalid_votes=2,
        blank_votes=1,
        total_votes=153,
        confidence_score=0.95,
        confidence_details={
            "level": "EXCELLENT",
            "thai_text_validation": 1.0,
            "sum_validation": 0.95,
            "province_validation": 0.95,
            "details": []
        },
        candidate_info={},
        party_votes={"1": 45, "2": 30, "3": 25, "4": 20, "5": 30},
        party_info={
            "1": {"name": "ภูมิใจไทย", "abbr": "ภท.", "color": "#FF0000"},
            "2": {"name": "เพื่อไทย", "abbr": "เพท.", "color": "#FF6600"},
        },
        page_parties=[1, 2, 3, 4, 5],
        discrepancies={},
    )
    
    party_output = "test_reports/test_party_list.pdf"
    success = generate_ballot_pdf(party_ballot, party_output)
    
    if success:
        if Path(party_output).exists():
            file_size = Path(party_output).stat().st_size
            print(f"   ✓ Party-list PDF created: {file_size} bytes")
        else:
            print("   ✗ Party-list PDF file not created")
            return False
    else:
        print("   ✗ Failed to generate party-list PDF")
        return False
    
    print("\n" + "=" * 70)
    print("✓ ALL PDF GENERATION TESTS PASSED")
    print("\nGenerated files:")
    print(f"  - {output_path}")
    print(f"  - {batch_output}")
    print(f"  - {party_output}")
    print("\nUsage:")
    print("  python3 ballot_ocr.py images/ --batch --reports --pdf")
    
    return True


if __name__ == "__main__":
    try:
        success = test_pdf_generation()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
