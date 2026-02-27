#!/usr/bin/env python3
import json
import argparse
from collections import defaultdict
from pathlib import Path

def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def investigate_district(province, district_number):
    print(f"Investigating {province} District {district_number}...")
    
    # Load structured scores
    scores_path = Path("drive2_scores_structured_per_file.json")
    if not scores_path.exists():
        print(f"Error: {scores_path} not found.")
        return

    data = load_json(scores_path)
    
    # Filter and group by polling unit
    units = defaultdict(lambda: {"constituency": None, "party_list": None})
    
    # The JSON structure has an "items" key
    items = data.get("items", [])
    
    for entry in items:
        if entry.get("province") == province and entry.get("district_number") == district_number:
            unit_no = entry.get("location_number")
            e_type = entry.get("election_type") # constituency or party_list
            
            if unit_no is not None and e_type in ["constituency", "party_list"]:
                units[unit_no][e_type] = entry

    # Analysis
    print(f"{'Unit':<10} | {'Cons. Valid':<12} | {'P.List Valid':<12} | {'Delta':<8} | {'Status'}")
    print("-" * 70)
    
    total_cons = 0
    total_plist = 0
    
    sorted_units = sorted(units.keys())
    for unit_no in sorted_units:
        u = units[unit_no]
        cons = u["constituency"]
        plist = u["party_list"]
        
        # Extract valid votes from rows if available
        def get_valid_votes(entry):
            if not entry or "rows" not in entry:
                return 0
            # Look for a row that represents total valid votes if it exists, 
            # or sum up candidate votes. 
            # In district_dashboard_data.json it's "valid_votes_extracted"
            # Here we might need to check how it's stored in score_structured_per_file
            # Based on previous view_file, 'rows' might be empty or specific per entry.
            # If 'rows' is empty, we might not have the detail here.
            # Let's check district_dashboard_data.json first for the totals.
            return 0 # Placeholder for now

        # Actually, drive2_scores_structured_per_file.json might have the votes in entry['rows']
        # but let's see if we can get it from 'valid_votes' or similar.
        
        v_cons = cons.get("valid_votes", 0) if cons else 0
        v_plist = plist.get("valid_votes", 0) if plist else 0
        
        # If 'valid_votes' key is missing, try to calculate from rows
        # (This depends on the exact schema of the file)
        
        delta = v_cons - v_plist
        status = ""
        if not cons: status = "Missing Constituency"
        elif not plist: status = "Missing Party List"
        elif abs(delta) > 0: status = "DISCREPANCY"
        
        if abs(delta) > 0 or not cons or not plist:
            print(f"{unit_no:<10} | {v_cons:<12} | {v_plist:<12} | {delta:<8} | {status}")
        
        total_cons += v_cons
        total_plist += v_plist

    print("-" * 70)
    print(f"{'TOTAL':<10} | {total_cons:<12} | {total_plist:<12} | {total_cons - total_plist:<8}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--province", required=True)
    parser.add_argument("--district", type=int, required=True)
    args = parser.parse_args()
    
    investigate_district(args.province, args.district)
