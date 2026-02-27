#!/usr/bin/env python3
"""
Election Data Integrity Verification Script.

Verifies the consistency and accuracy of election data snapshots.
"""

import argparse
import sys
import os
from ect_api import ECTData, Candidate, Party, Province

def verify_candidate_linkage(ect_data: ECTData):
    """Verify that all candidates have results and vice versa."""
    print("\n--- Verifying Candidate Linkage ---")
    ect_data.load_candidates()
    ect_data.load_official_results()
    
    candidates = ect_data._candidates
    stats_cons = ect_data._stats_cons_by_id
    
    # 1. Check if every candidate has a result entry
    # Note: stats_cons.json stores candidates per constituency
    found_candidates = set()
    for cons_id, cons_stats in stats_cons.items():
        candidates_in_cons = cons_stats.get("candidates", [])
        for cand_stat in candidates_in_cons:
            mp_app_id = cand_stat.get("mp_app_id")
            if mp_app_id:
                found_candidates.add(mp_app_id)
                if mp_app_id not in candidates:
                    print(f"ERROR: Candidate {mp_app_id} found in results but not in info_mp_candidate.json")

    missing_results = []
    for mp_app_id in candidates:
        if mp_app_id not in found_candidates:
            missing_results.append(mp_app_id)
            
    if missing_results:
        print(f"WARNING: {len(missing_results)} candidates have no result entries in stats_cons.json")
        # Optional: print first few
        for mid in missing_results[:5]:
            print(f"  - {mid}")
    else:
        print("SUCCESS: All candidates in info_mp_candidate.json have result entries.")

def verify_vote_totals(ect_data: ECTData):
    """Verify that sum of candidate votes matches valid_vote count."""
    print("\n--- Verifying Vote Totals ---")
    ect_data.load()
    ect_data.load_official_results()
    
    stats_cons = ect_data._stats_cons_by_id
    mismatches = 0
    
    for cons_id, cons_stats in stats_cons.items():
        valid_votes = int(cons_stats.get("valid_votes", 0) or 0)
        cand_votes_sum = sum(int(c.get("mp_app_vote", 0) or 0) for c in cons_stats.get("candidates", []))
        
        if valid_votes != cand_votes_sum:
            mismatches += 1
            print(f"ERROR: Vote mismatch in constituency {cons_id}!")
            print(f"  Reported Valid Votes: {valid_votes}")
            print(f"  Sum of Candidate Votes: {cand_votes_sum}")
            print(f"  Difference: {valid_votes - cand_votes_sum}")

    if mismatches == 0:
        print("SUCCESS: All constituency vote totals match sum of candidate votes.")
    else:
        print(f"FAILURE: {mismatches} constituencies have vote total mismatches.")

def verify_party_consistency(ect_data: ECTData):
    """Verify that candidate party IDs match result party IDs."""
    print("\n--- Verifying Party Consistency ---")
    ect_data.load()
    ect_data.load_candidates()
    ect_data.load_official_results()
    
    stats_cons = ect_data._stats_cons_by_id
    candidates = ect_data._candidates
    
    mismatches = 0
    for cons_id, cons_stats in stats_cons.items():
        for cand_stat in cons_stats.get("candidates", []):
            mp_app_id = cand_stat.get("mp_app_id")
            if not mp_app_id or mp_app_id not in candidates:
                continue
                
            candidate = candidates[mp_app_id]
            stat_party_id = cand_stat.get("party_id")
            
            # Note: in info_mp_candidate, mp_app_party_id is int
            # In stats_cons, party_id is string
            if str(candidate.mp_app_party_id) != str(stat_party_id):
                mismatches += 1
                if mismatches <= 10:
                    print(f"ERROR: Party mismatch for candidate {mp_app_id}")
                    print(f"  Candidate Info Party ID: {candidate.mp_app_party_id}")
                    print(f"  Result Stat Party ID: {stat_party_id}")

    if mismatches == 0:
        print("SUCCESS: All candidate party IDs match result party IDs.")
    else:
        print(f"FAILURE: {mismatches} candidate party ID mismatches found.")

def main():
    parser = argparse.ArgumentParser(description="Verify ECT data integrity.")
    parser.add_argument("--snapshot", type=str, required=True, help="Path to the snapshot directory.")
    args = parser.parse_args()
    
    if not os.path.isdir(args.snapshot):
        print(f"Error: {args.snapshot} is not a directory.")
        sys.exit(1)

    print(f"Initializing ECTData with snapshot: {args.snapshot}")
    ect_data = ECTData(base_dir=args.snapshot)
    
    try:
        verify_candidate_linkage(ect_data)
        verify_vote_totals(ect_data)
        verify_party_consistency(ect_data)
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
