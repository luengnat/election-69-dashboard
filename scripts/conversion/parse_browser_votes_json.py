#!/usr/bin/env python3
from __future__ import annotations
import json,re,sys
from difflib import SequenceMatcher
from pathlib import Path
from ect_api import ECTData

TH=str.maketrans('๐๑๒๓๔๕๖๗๘๙','0123456789')
ect_data = ECTData()

def to_int(v):
    if v is None: return None
    if isinstance(v,bool): return None
    if isinstance(v,(int,float)): return int(v)
    s=str(v).translate(TH)
    m=re.findall(r'\d+',s.replace(',',''))
    return int(''.join(m)) if m else None

def extract_json(text):
    if not text: return None
    t=text.strip()
    if t.startswith('```'):
        t=re.sub(r'^```(?:json)?\s*','',t,flags=re.I)
        t=re.sub(r'\s*```$','',t)
    for cand in [t]:
        try:
            o=json.loads(cand)
            if isinstance(o,dict): return o
        except: pass
    i=t.find('{'); j=t.rfind('}')
    if i>=0 and j>i:
        try:
            o=json.loads(t[i:j+1])
            if isinstance(o,dict): return o
        except: pass
    return None

def normalize_election_type(raw, form_type, name):
    t=(str(raw or '') + ' ' + str(form_type or '') + ' ' + str(name or '')).lower()
    if '(บช)' in t or 'party' in t or 'บัญชีรายชื่อ' in t:
        return 'party_list'
    return 'constituency'

def filter_votes_with_refs(province, district_number, election_type, votes):
    kept={}
    dropped={}
    # Always enforce numeric party range.
    if election_type == 'party_list':
        for k,v in votes.items():
            n=to_int(k)
            if n is None or n < 1 or n > 57:
                dropped[k]=v
                continue
            kept[str(n)] = v
        return kept, dropped

    # Constituency: prefer official candidate positions from ECT.
    valid_positions=set()
    if province and district_number:
        try:
            ok, canonical = ect_data.validate_province_name(str(province))
            p = canonical if ok and canonical else str(province)
            cands = ect_data.get_candidates_by_thai_province(p, int(district_number))
            valid_positions = {int(c.position) for c in cands if getattr(c, 'position', None) is not None}
        except Exception:
            valid_positions=set()

    for k,v in votes.items():
        n=to_int(k)
        if n is None:
            dropped[k]=v
            continue
        if valid_positions:
            if n in valid_positions:
                kept[str(n)] = v
            else:
                dropped[str(n)] = v
        else:
            # Conservative fallback when refs unavailable.
            if 1 <= n <= 40:
                kept[str(n)] = v
            else:
                dropped[str(n)] = v
    return kept, dropped

def normalize_name(s):
    t=(str(s or '')).translate(TH).lower().strip()
    t=re.sub(r'[\s\-_\.,"“”\'\(\)\[\]{}:;]+','',t)
    return t

def similarity(a,b):
    na,nb=normalize_name(a),normalize_name(b)
    if not na or not nb:
        return 0.0
    if na==nb:
        return 1.0
    return SequenceMatcher(None, na, nb).ratio()

def build_name_checks(province, district_number, election_type, row_names):
    checks=[]
    if not row_names:
        return checks
    if election_type == 'party_list':
        for num,name in sorted(row_names.items(), key=lambda x: int(x[0])):
            party = ect_data.get_party_by_number(int(num))
            expected = getattr(party, 'name', None) if party else None
            sim = similarity(name, expected)
            checks.append({
                'number': int(num),
                'observed_name': name,
                'expected_name': expected,
                'similarity': round(sim, 3),
                'matched': bool(expected) and sim >= 0.72,
            })
        return checks

    # constituency
    expected_by_pos={}
    try:
        ok, canonical = ect_data.validate_province_name(str(province))
        p = canonical if ok and canonical else str(province)
        cands = ect_data.get_candidates_by_thai_province(p, int(district_number))
        for c in cands:
            pos = to_int(getattr(c, 'position', None) or getattr(c, 'mp_app_no', None))
            if pos is None:
                continue
            expected_by_pos[pos] = getattr(c, 'mp_app_name', None)
    except Exception:
        expected_by_pos={}

    for num,name in sorted(row_names.items(), key=lambda x: int(x[0])):
        n=int(num)
        expected=expected_by_pos.get(n)
        sim=similarity(name, expected)
        checks.append({
            'number': n,
            'observed_name': name,
            'expected_name': expected,
            'similarity': round(sim, 3),
            'matched': bool(expected) and sim >= 0.7,
        })
    return checks

def main(inp,out):
    ect_data.load()
    rows=[]
    for ln in Path(inp).read_text(encoding='utf-8').splitlines():
        if not ln.strip(): continue
        try:r=json.loads(ln)
        except: continue
        ans=(r.get('summary') or '').strip()
        obj=extract_json(ans)
        if not obj: continue
        votes=obj.get('votes') if isinstance(obj.get('votes'),dict) else {}
        votes2={}
        for k,v in votes.items():
            key=str(k).strip().translate(TH)
            if not re.fullmatch(r'\d{1,3}', key):
                continue
            n=to_int(v)
            if n is None:
                continue
            votes2[key]=n
        row_names={}
        rows_obj = obj.get('rows') if isinstance(obj.get('rows'), list) else []
        for rr in rows_obj:
            if not isinstance(rr, dict):
                continue
            num = to_int(rr.get('number'))
            nm = str(rr.get('name') or rr.get('candidate_name') or rr.get('party_name') or '').strip()
            if num is None or num < 1 or not nm:
                continue
            row_names[str(num)] = nm
        election_type = normalize_election_type(obj.get('election_type'), obj.get('form_type') or r.get('form_type_hint'), r.get('name'))
        province = obj.get('province') or r.get('province_hint')
        district_number = to_int(obj.get('district_number')) or r.get('district_number_hint')
        filtered_votes, dropped_votes = filter_votes_with_refs(province, district_number, election_type, votes2)
        name_checks = build_name_checks(province, district_number, election_type, row_names)

        rows.append({
            'drive_id':r.get('drive_id'),
            'name':r.get('name'),
            'province':province,
            'district_number':district_number,
            'election_type':election_type,
            'form_type':obj.get('form_type') or r.get('form_type_hint'),
            'valid_votes':to_int(obj.get('valid_votes')),
            'invalid_votes':to_int(obj.get('invalid_votes')),
            'blank_votes':to_int(obj.get('blank_votes')),
            'total_votes':to_int(obj.get('total_votes')),
            'votes':filtered_votes,
            'dropped_vote_keys':sorted(dropped_votes.keys(), key=lambda x: (to_int(x) is None, to_int(x) or 0, str(x))),
            'name_checks': name_checks,
            'notes':obj.get('notes'),
            'drive_url':r.get('drive_url'),
        })
    Path(out).write_text(json.dumps({'count':len(rows),'items':rows},ensure_ascii=False,indent=2),encoding='utf-8')
    print('parsed',len(rows),'->',out)

if __name__=='__main__':
    if len(sys.argv)!=3:
        print('usage: parse_browser_votes_json.py <input_jsonl> <output_json>'); raise SystemExit(2)
    main(sys.argv[1],sys.argv[2])
