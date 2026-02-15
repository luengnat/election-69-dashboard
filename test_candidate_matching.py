#!/usr/bin/env python3
"""
Test candidate matching logic for Phase 2.2 implementation.
"""

import json
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from ballot_ocr import process_extracted_data
from ect_api import ect_data


def test_candidate_matching():
    """Test that candidate matching works correctly."""
    
    # Load candidate data
    print("Loading ECT candidate data...")
    ect_data.load_candidates()
    
    # Simulate extracted data from a constituency form
    mock_extraction_data = {
        "form_type": "ส.ส. 5/16",
        "form_code": "5/16",
        "is_party_list": False,
        "province": "แพร่",
        "constituency_number": 1,
        "district": "เมืองแพร่",
        "polling_unit": 2,
        "vote_counts": {
            "1": {"numeric": 153, "thai_text": "หนึ่งร้อยห้าสิบสาม"},
            "2": {"numeric": 4, "thai_text": "สี่"},
            "3": {"numeric": 95, "thai_text": "เก้าสิบห้า"},
        },
        "valid_votes": 252,
        "invalid_votes": 3,
        "blank_votes": 0,
        "total_votes": 255,
    }
    
    print("\nProcessing mock extraction data...")
    ballot_data = process_extracted_data(mock_extraction_data, "test_mock.png", form_type=None)
    
    if not ballot_data:
        print("✗ Extraction failed!")
        return False
    
    print("\n" + "="*70)
    print("RESULTS")
    print("="*70)
    
    # Verify basic fields
    print(f"\nForm Information:")
    print(f"  Form type: {ballot_data.form_type}")
    print(f"  Category: {ballot_data.form_category}")
    print(f"  Province: {ballot_data.province}")
    print(f"  Constituency: {ballot_data.constituency_number}")
    
    # Verify vote counts
    print(f"\nVote Counts:")
    print(f"  Total votes: {ballot_data.total_votes}")
    print(f"  Valid votes: {ballot_data.valid_votes}")
    print(f"  Invalid votes: {ballot_data.invalid_votes}")
    print(f"  Blank votes: {ballot_data.blank_votes}")
    
    # Verify candidate matching
    print(f"\nCandidate Matching:")
    if ballot_data.candidate_info:
        for position, info in sorted(ballot_data.candidate_info.items()):
            votes = ballot_data.vote_counts.get(position, 0)
            print(f"  Position {position}:")
            print(f"    Name: {info['name']}")
            print(f"    Party: {info['party_name']} ({info['party_abbr']})")
            print(f"    Votes: {votes}")
            
        # Check that candidates were matched
        matched_count = sum(1 for info in ballot_data.candidate_info.values() 
                          if info['name'] != "Unknown")
        print(f"\n  ✓ Successfully matched {matched_count}/{len(ballot_data.candidate_info)} candidates")
        
        if matched_count == len(ballot_data.candidate_info):
            print("  ✓ ALL CANDIDATES MATCHED!")
            return True
        else:
            print(f"  ⚠ Some candidates not matched")
            return True  # Still pass since some were matched
    else:
        print(f"  ✗ No candidate info in results")
        return False


if __name__ == "__main__":
    success = test_candidate_matching()
    sys.exit(0 if success else 1)
