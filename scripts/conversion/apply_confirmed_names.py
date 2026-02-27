import json
import os
import sys

# Paths
DATA_DIR = "/Users/nat/dev/election/data"
DASHBOARD_DATA_PATH = "/tmp/election-main/docs/data/district_dashboard_data.json"
CONFIRMED_WINNERS_PATH = os.path.join(DATA_DIR, "confirmed_winners.json")
COMPARISON_REPORT_PATH = os.path.join(DATA_DIR, "comparison_report.json")

def load_json(filepath):
    print(f"Loading {filepath}...")
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_json(data, filepath):
    print(f"Saving updated data to {filepath}...")
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def main():
    if not os.path.exists(DASHBOARD_DATA_PATH):
        print(f"Error: Dashboard data not found at {DASHBOARD_DATA_PATH}")
        sys.exit(1)
        
    dashboard_data = load_json(DASHBOARD_DATA_PATH)
    comparison_report = load_json(COMPARISON_REPORT_PATH)
    confirmed_winners = load_json(CONFIRMED_WINNERS_PATH)
    
    # Create lookup for confirmed winners
    confirmed_lookup = {}
    for entry in confirmed_winners:
        key = (entry["province"], entry["constituency_no"])
        confirmed_lookup[key] = entry
        
    mismatches_to_fix = [d for d in comparison_report["discrepancies"] if d["type"] == "winner_mismatch"]
    
    if not mismatches_to_fix:
        print("No winner mismatches found in the comparison report. Nothing to update.")
        return

    print(f"\nFound {len(mismatches_to_fix)} spelling variations to fix...")
    
    updates_applied = 0
    province_fixes_applied = 0
    # Iterate through dashboard data to apply fixes
    for doc in dashboard_data.get("items", []):
            
        province = doc.get("province")
        const_num = doc.get("district_number")
        if doc.get("form_type") != "constituency":
            continue
            
        # Normalize province for lookup because comparison_report saves normalized names
        prov_lookup = province.replace('ำ', 'า').replace('เเ', 'แ')
        key = (province, const_num)
        
        # Check if this constituency is in our list of mismatches
        mismatch_info = next((m for m in mismatches_to_fix if m["province"] == prov_lookup and m["district"] == const_num), None)
        
        if mismatch_info:
            confirmed_entry = confirmed_lookup.get(key)
            if not confirmed_entry:
                continue
                
            confirmed_name = confirmed_entry["winner_name"]
            
            # Find the winner's candidate number by looking at the highest vote count among actual candidates
            votes = doc.get("votes", {})
            candidate_names = doc.get("candidate_names", {})
            
            if not votes or not candidate_names:
                continue
                
            winner_cand_no = None
            max_votes = -1
            
            for cand_no, vote_str in votes.items():
                if str(cand_no) in ["no_pick", "bad_boxes", "empty"]:
                    continue
                try:
                    vote_count = int(vote_str)
                    if vote_count > max_votes:
                        max_votes = vote_count
                        winner_cand_no = str(cand_no)
                except ValueError:
                    pass
            
            if winner_cand_no and winner_cand_no in candidate_names:
                old_name = candidate_names[winner_cand_no]
                # To be absolutely sure, only update if the old name matches what we found in the report
                db_name_clean = old_name.split('(')[0].strip()
                dashboard_winner_clean = mismatch_info["dashboard_winner"].split('(')[0].strip()
                if db_name_clean == dashboard_winner_clean:
                    print(f"[{province} {const_num}] Updating candidate {winner_cand_no}: '{old_name}' -> '{confirmed_name}'")
                    candidate_names[winner_cand_no] = confirmed_name
                    updates_applied += 1

    print(f"\nSuccessfully applied {updates_applied} name updates, and {province_fixes_applied} province spelling fixes.")
    
    if updates_applied > 0 or province_fixes_applied > 0:
        save_json(dashboard_data, DASHBOARD_DATA_PATH)
        print("Dashboard data updated.")

if __name__ == "__main__":
    main()
