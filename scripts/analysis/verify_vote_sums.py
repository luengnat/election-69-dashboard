import json
from collections import defaultdict

def main():
    data_path = 'docs/data/district_dashboard_data.json'
    
    with open(data_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    items = data.get('items', [])
    print(f"Loaded {len(items)} items from {data_path}")
    
    mismatches = []
    
    for item in items:
        province = item.get('province', 'Unknown')
        district = item.get('district_number', 'Unknown')
        form_type = item.get('form_type', 'Unknown')
        name = f"{province} เขต {district} ({form_type})"
        
        # Check primary read
        valid_extracted = item.get('valid_votes_extracted')
        votes_dict = item.get('votes', {})
        if valid_extracted is not None and votes_dict:
            try:
                # Some votes might be '-' or something not numeric, try to convert safely
                sum_votes = sum(int(v) for v in votes_dict.values() if str(v).isdigit())
                if sum_votes != valid_extracted:
                    mismatches.append({
                        'name': name,
                        'source': 'Read',
                        'reported_valid': valid_extracted,
                        'summed_votes': sum_votes,
                        'delta': valid_extracted - sum_votes
                    })
            except Exception as e:
                pass

        # Check sources
        sources = item.get('sources', {})
        for src_name, src_data in sources.items():
            if not isinstance(src_data, dict):
                continue
                
            reported_valid = src_data.get('valid_votes')
            src_votes_dict = src_data.get('votes', {})
            
            if reported_valid is not None and src_votes_dict:
                try:
                    sum_votes = sum(int(v) for v in src_votes_dict.values() if str(v).isdigit())
                    if sum_votes != reported_valid:
                        mismatches.append({
                            'name': name,
                            'source': src_name,
                            'reported_valid': reported_valid,
                            'summed_votes': sum_votes,
                            'delta': int(reported_valid) - sum_votes
                        })
                except Exception as e:
                    pass

    print(f"\nFound {len(mismatches)} mismatches where reported valid votes != sum of individual votes.")
    
    # Group by source
    by_source = defaultdict(list)
    for m in mismatches:
        by_source[m['source']].append(m)
        
    for src, mism in by_source.items():
        print(f"\n=== Mismatches in source: {src} ({len(mism)}) ===")
        # Print top 10
        for m in sorted(mism, key=lambda x: abs(x['delta']), reverse=True)[:10]:
            print(f"  {m['name']}: Reported={m['reported_valid']}, Sum={m['summed_votes']}, Delta={m['delta']}")

if __name__ == '__main__':
    main()
