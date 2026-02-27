#!/usr/bin/env python3
import json
import re
import os
import sys

# Add current directory to path to import ballot_types
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
try:
    from ballot_types import convert_thai_numerals
except ImportError:
    def convert_thai_num(text):
        thai_num = "๐๑๒๓๔๕๖๗๘๙"
        arabic_num = "0123456789"
        table = str.maketrans(thai_num, arabic_num)
        return text.translate(table)
    convert_thai_numerals = convert_thai_num

def clean_text(text):
    if not text:
        return ""
    # Normalize OCR/PDF artifacts
    text = text.replace('ำ', 'า').replace('เเ', 'แ')
    
    # Standardize BKK
    if "กรุงเทพ" in text or "มหานคร" in text:
        text = "กรุงเทพมหานคร"
    
    # v3 has spaces between characters like ก า
    text = text.replace("ก า", "กา").replace("จ า", "จำ").replace("อำ นาจ", "อำนาจ").replace("อ า นาจ", "อำนาจ")
    text = text.replace("อ านวย", "อำนวย").replace("ส าราญ", "สำราญ")
    
    # Clean up trailing numbers or weird symbols (often page numbers or line counts)
    text = re.sub(r'\s+[๐-๙\d]+$', '', text)
    
    # Common OCR errors in names
    text = text.replace("นำย", "นาย").replace("นำง", "นาง")
    
    return re.sub(r'\s+', ' ', text.strip())

def parse_confirmed_list_v3(file_path):
    if not os.path.exists(file_path):
        print(f"Error: {file_path} not found.")
        return []

    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    results = []
    current_province = None
    
    # Common party names in the doc for fallback
    parties = ["ประชาชน", "เพื่อไทย", "ภูมิใจไทย", "กล้าธรรม", "ประชาธิปัตย์", "ไทยสร้างไทย", "ประชาชาติ", "ไทรวมพลัง", "พลังประชารัฐ", "โอกาสใหม่"]
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        
        # Skip headers/junk
        if not line or "ประกาศคณะกรรมการการเลือกตั้ง" in line or "เรื่อง ผลการเลือกตั้ง" in line:
            i += 1
            continue
        if re.match(r'^[๐-๙\d\s\f]+$', line) and len(line) < 10:
            i += 1
            continue
        if "ลำดับที่ จังหวัด/เขตเลือกตั้งที่" in line:
            i += 1
            continue

        # Detect province line: e.g. "1 กรุงเทพมหำนคร" or "2 กระบี่"
        prov_match = re.search(r'^\d+\s+([ก-๛].*)$', line)
        if prov_match:
            potential_prov = clean_text(prov_match.group(1))
            # Check if this is actually a standalone party name (continuation)
            if any(p.replace('ำ', 'า') == potential_prov.replace('ำ', 'า') for p in parties):
                pass
            else:
                current_province = potential_prov
                i += 1
                continue

        # Detect constituency line: e.g. "เขตเลือกตั้งที่ 1 นำยปำรเมศ วิทยำรักษ์สรรค์ ประชำชน"
        cons_match = re.search(r'เขตเลือกตั้งที่\s*([๐-๙\d]+)\s+(.*)$', line)
        if cons_match:
            cons_no = int(convert_thai_numerals(cons_match.group(1)))
            remaining = cons_match.group(2).strip()
            
            winner_name = remaining
            winner_party = "Unknown"
            
            # Robust party extraction - normalize remaining before check
            norm_remaining = remaining.replace('ำ', 'า').replace('เเ', 'แ')
            
            for p in parties:
                variations = [p, p.replace('ำ', 'า'), p.replace('เเ', 'แ')]
                for var in variations:
                    # Look for party preceded by space in normalized remaining
                    if f" {var}" in norm_remaining:
                        winner_party = p
                        idx = norm_remaining.rindex(var)
                        winner_name = remaining[:idx].strip()
                        break
                    elif norm_remaining.endswith(var) and len(norm_remaining) > len(var) + 3:
                        winner_party = p
                        winner_name = remaining[:-len(var)].strip()
                        break
                if winner_party != "Unknown":
                    break
            
            # If party still unknown, check next line
            if winner_party == "Unknown" and i + 1 < len(lines):
                next_line = lines[i+1].strip()
                if next_line:
                    norm_next = next_line.replace('ำ', 'า').replace('เเ', 'แ')
                    # Check if next line matches a party
                    for p in parties:
                        if norm_next == p or norm_next == p.replace('ำ', 'า'):
                            winner_party = p
                            i += 1
                            break
                    
                    if winner_party == "Unknown" and not "เขตเลือกตั้ง" in next_line and not re.match(r'^\d+\s+[ก-๛]', next_line):
                        winner_name += " " + next_line
                        i += 1
                        # Check one more line for party
                        if i + 1 < len(lines):
                            next_next = lines[i+1].strip()
                            norm_next_next = next_next.replace('ำ', 'า').replace('เเ', 'แ')
                            for p in parties:
                                if norm_next_next == p or norm_next_next == p.replace('ำ', 'า'):
                                    winner_party = p
                                    i += 1
                                    break
            
            if current_province:
                results.append({
                    "province": current_province,
                    "constituency_no": cons_no,
                    "winner_name": clean_text(winner_name),
                    "winner_party": winner_party
                })
            i += 1
            continue

        i += 1

    return results

def main():
    input_file = "/Users/nat/dev/election/data/confirmed_list_v3.txt"
    output_file = "/Users/nat/dev/election/data/confirmed_winners.json"
    
    print(f"Parsing {input_file}...")
    winners = parse_confirmed_list_v3(input_file)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(winners, f, ensure_ascii=False, indent=2)
    
    print(f"Successfully converted {len(winners)} records to {output_file}")

if __name__ == "__main__":
    main()
