#!/usr/bin/env python3
import json
import os
import re

def load_json(file_path):
    if not os.path.exists(file_path):
        return None
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def normalize_name(name):
    if not name:
        return ""
    # Remove titles (expanded list)
    titles = [
        "นาย", "นางสาว", "นาง", "ว่าที่ร้อยตรี", "เรืออากาศโท", 
        "พลตำรวจตรี", "นาวาอากาศเอก", "พล.ต.ต.", "หม่อมหลวง",
        "ดร.", "ศาสตราจารย์", "พ.ต.ท.", "พ.ต.อ.", "ร.ต.อ.",
        "นายแพทย์", "สัตวแพทย์", "เภสัชกร", "ทนายความ"
    ]
    for title in titles:
        if name.startswith(title):
            name = name[len(title):].strip()
            
    # Remove extra spaces
    name = re.sub(r'\s+', '', name)
    
    # Map 'ำ' (SARA AM) to 'า' (SARA AA) as they are often confused in OCR/PDF
    name = name.replace('ำ', 'า')
    name = name.replace('เเ', 'แ')
    
    # Remove Thai tone marks
    # ่ (U+0E48), ้ (U+0E49), ๊ (U+0E4A), ๋ (U+0E4B), ็ (U+0E47), ์ (U+0E4C), ํ (U+0E4D - NIKHAHIT)
    tone_marks = ['่', '้', '๊', '๋', '็', '์', 'ํ']
    for mark in tone_marks:
        name = name.replace(mark, '')
        
    # Standardize similar characters
    replacements = {
        'ฎ': 'ฏ',
        'ซ': 'ช',
        'ศ': 'ส',
        'ท': 'ธ',
        'ณ': 'น',
        'พ': 'ภ'  # Common OCR error
    }
    for old, new in replacements.items():
        name = name.replace(old, new)
        
    return name

def normalize_province(name):
    if not name:
        return ""
    # Normalize OCR/PDF artifacts in province names
    name = name.replace('ำ', 'า').replace('เเ', 'แ')
    
    if "กรุงเทพ" in name or "มหานคร" in name:
        name = "กรุงเทพมหานคร"
    
    name = name.replace("ก า", "กา").replace("จ า", "จำ").replace("อำ นาจ", "อำนาจ").replace("อ า นาจ", "อำนาจ")
    
    # Remove extra spaces
    name = re.sub(r'\s+', '', name)
    return name.strip()

def compare_results():
    dashboard_path = "/tmp/election-main/docs/data/district_dashboard_data.json"
    confirmed_path = "/Users/nat/dev/election/data/confirmed_winners.json"
    
    dashboard_data = load_json(dashboard_path)
    confirmed_winners = load_json(confirmed_path)
    
    if not dashboard_data or not confirmed_winners:
        print("Error: Missing data files.")
        return

    confirmed_map = {}
    for item in confirmed_winners:
        prov = normalize_province(item["province"])
        key = (prov, item["constituency_no"])
        if key not in confirmed_map:
            confirmed_map[key] = []
        confirmed_map[key].append(item)

    items = dashboard_data.get("items", [])
    discrepancies = []
    
    for item in items:
        if item.get("form_type") != "constituency":
            continue
            
        prov = normalize_province(item.get("province"))
        dist = item.get("district_number")
        key = (prov, dist)
        
        possible_confirmed = confirmed_map.get(key)
        if not possible_confirmed:
            discrepancies.append({
                "type": "missing_confirmed",
                "province": prov,
                "district": dist,
                "message": "Constituency not found in confirmed list"
            })
            continue

        votes = item.get("votes", {})
        if not votes:
            discrepancies.append({
                "type": "no_votes",
                "province": prov,
                "district": dist,
                "message": "No vote data in dashboard"
            })
            continue
            
        dashboard_winner_no = max(votes, key=lambda k: int(votes[k]))
        dashboard_winner_name = item.get("candidate_names", {}).get(dashboard_winner_no)
        dashboard_winner_party = item.get("candidate_parties", {}).get(dashboard_winner_no)
        
        norm_dashboard_name = normalize_name(dashboard_winner_name)
        
        match_found = False
        best_match_confirmed = possible_confirmed[-1]
        
        for conf in possible_confirmed:
            norm_confirmed_name = normalize_name(conf["winner_name"])
            
            if norm_dashboard_name == norm_confirmed_name or \
               norm_confirmed_name in norm_dashboard_name or \
               norm_dashboard_name in norm_confirmed_name:
                match_found = True
                best_match_confirmed = conf
                break
        
        if not match_found:
            discrepancies.append({
                "type": "winner_mismatch",
                "province": prov,
                "district": dist,
                "dashboard_winner": f"{dashboard_winner_name} ({dashboard_winner_party})",
                "confirmed_winner": f"{best_match_confirmed['winner_name']} ({best_match_confirmed['winner_party']})",
                "votes": votes
            })
        else:
            dashboard_party_norm = dashboard_winner_party.replace(" ", "").replace("ประชา", "ประชำ")
            confirmed_party_norm = best_match_confirmed["winner_party"].replace(" ", "").replace("ประชา", "ประชำ")
            if confirmed_party_norm != dashboard_party_norm:
                discrepancies.append({
                    "type": "party_mismatch",
                    "province": prov,
                    "district": dist,
                    "winner_name": best_match_confirmed["winner_name"],
                    "dashboard_party": dashboard_winner_party,
                    "confirmed_party": best_match_confirmed["winner_party"]
                })
            
        item["confirmed_winner_official"] = best_match_confirmed

    report = {
        "summary": {
            "total_constituencies": len([i for i in items if i.get("form_type") == "constituency"]),
            "matches": len([i for i in items if i.get("form_type") == "constituency"]) - len(discrepancies),
            "discrepancies": len(discrepancies)
        },
        "discrepancies": discrepancies
    }
    
    with open("/Users/nat/dev/election/data/comparison_report.json", "w", encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
        
    output_dashboard_path = "/Users/nat/dev/election/data/district_dashboard_data_updated.json"
    with open(output_dashboard_path, "w", encoding='utf-8') as f:
        json.dump(dashboard_data, f, ensure_ascii=False, indent=2)
        
    print(f"Comparison complete. {len(discrepancies)} discrepancies found.")

if __name__ == "__main__":
    compare_results()
