# Operations Runbook

## 1) Local Setup

```bash
cd /tmp/election-main
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 2) Start Verifier / Web App

```bash
cd /tmp/election-main
./venv/bin/python verify_ground_truth_app.py
```

Expected local URL:
- `http://0.0.0.0:7861` (or per app log)

## 3) Dashboard Data Refresh Flow (Operational)

1. Update extraction/corrections in source JSON
2. Re-run enrichment/comparison scripts used by current branch
3. Rebuild dashboard data artifacts under:
   - `docs/data/`
4. Validate key checks:
   - row count (expected around 800)
   - pair completeness (constituency + party_list per district)
   - `sum(votes) == valid` where votes exist
   - skew logic uses same-source totals only

## 4) Critical Validation Commands

Use project-specific validators already in repo (examples):

```bash
cd /tmp/election-main
./venv/bin/python verify_vote_sums.py
```

If adding new validators, keep them deterministic and output machine-readable JSON/CSV.

## 5) Publishing Static Web

Primary static files:
- `docs/index.html`
- `docs/styles.css`
- `docs/app-k16.js` (or active app file)
- `docs/data/*.json`

Cache busting rule:
- bump query version in script tag when frontend logic changes.

## 6) Regenerate Comparison CSV (Current Data)

Regenerate CSV/summary files from `docs/data/district_dashboard_data.json`:

```bash
cd /tmp/election-main
python3 - <<'PY'
import json, csv
p='docs/data/district_dashboard_data.json'
d=json.load(open(p,encoding='utf-8'))
items=d.get('items',[])
summary={'all_rows':0,'with_killernay':0,'exact_votes_match':0,'diff_votes_rows':0}
diffs=[]
sum_issues=[]
for r in items:
    summary['all_rows'] += 1
    s=r.get('sources') or {}
    k=s.get('killernay') or {}
    kv=k.get('votes') or {}
    cv=r.get('votes') or {}
    if kv:
        summary['with_killernay'] += 1
        keys=sorted(set([x for x in cv if str(x).isdigit()]) | set([x for x in kv if str(x).isdigit()]), key=lambda x:int(x))
        row_d=[]
        for key in keys:
            a=cv.get(key); b=kv.get(key)
            if isinstance(a,(int,float)) and isinstance(b,(int,float)):
                if int(a)!=int(b): row_d.append((int(key),int(a),int(b)))
            elif isinstance(a,(int,float)) or isinstance(b,(int,float)):
                row_d.append((int(key),a,b))
        if not row_d:
            summary['exact_votes_match'] += 1
        else:
            summary['diff_votes_rows'] += 1
            diffs.append({
                'province':r.get('province'),
                'district_number':r.get('district_number'),
                'form_type':r.get('form_type'),
                'drive_id':r.get('drive_id'),
                'diff_key_count':len(row_d),
                'sample':' | '.join([f"{x[0]}:{x[1]}->{x[2]}" for x in row_d[:8]])
            })
    if r.get('form_type')=='party_list':
        v=r.get('votes') or {}
        sv=sum(int(val) for kk,val in v.items() if str(kk).isdigit() and 1<=int(kk)<=57 and isinstance(val,(int,float)))
        valid=r.get('valid_votes_extracted')
        if isinstance(valid,(int,float)) and sv!=int(valid):
            sum_issues.append({
                'province':r.get('province'),
                'district_number':r.get('district_number'),
                'drive_id':r.get('drive_id'),
                'valid':int(valid),
                'sum_votes':sv,
                'delta':int(valid)-sv
            })
json.dump({'summary':summary,'remaining_partylist_sum_issues':len(sum_issues)},open('docs/data/recheck_all_vs_killernay_summary.json','w',encoding='utf-8'),ensure_ascii=False,indent=2)
with open('docs/data/recheck_all_vs_killernay_diffs.csv','w',newline='',encoding='utf-8') as f:
    w=csv.DictWriter(f,fieldnames=['province','district_number','form_type','drive_id','diff_key_count','sample'])
    w.writeheader(); w.writerows(diffs)
with open('docs/data/recheck_all_partylist_sum_issues.csv','w',newline='',encoding='utf-8') as f:
    w=csv.DictWriter(f,fieldnames=['province','district_number','drive_id','valid','sum_votes','delta'])
    w.writeheader(); w.writerows(sum_issues)
print('done')
PY
```

## 7) Incident Checklist (Data Looks Wrong)

When dashboard rows are suspicious:

1. Verify district + form_type identity fields
2. Verify source block used in UI (`latest` vs `ect` vs `vote62` vs `killernay`)
3. Recompute:
   - `valid + invalid + blank`
   - winner from vote map
4. Confirm winner labels:
   - constituency should show candidate identity, not only party fallback
5. If form text is inconsistent, mark row with explicit note (`document_inconsistent_possible_error`)

## 8) Known Source Caveats

- ECT web figure may represent 94% phase snapshot in some analyses.
- vote62 is volunteer-sourced and may have low coverage by district.
- Official form scans can still contain clerical inconsistencies; annotate explicitly.
