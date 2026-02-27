# Operations Runbook

## 1) Local Setup

```bash
cd /Users/nat/dev/election
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 2) Start Verifier / Web App

```bash
cd /Users/nat/dev/election
./venv/bin/python verify_ground_truth_app.py
```

Expected local URL:
- `http://0.0.0.0:7861` (or per app log)

## 3) Dashboard Data Refresh Flow (Operational)

1. Update extraction/corrections in source JSON
2. Re-run enrichment/comparison scripts used by current branch
3. Rebuild dashboard data artifacts under:
   - `/Users/nat/dev/election/docs/data/`
4. Validate key checks:
   - row count (expected around 800)
   - pair completeness (constituency + party_list per district)
   - `sum(votes) == valid` where votes exist
   - skew logic uses same-source totals only

## 4) Critical Validation Commands

Use project-specific validators already in repo (examples):

```bash
cd /Users/nat/dev/election
./venv/bin/python verify_vote_sums.py
```

If adding new validators, keep them deterministic and output machine-readable JSON/CSV.

## 5) Publishing Static Web

Primary static files:
- `/Users/nat/dev/election/docs/index.html`
- `/Users/nat/dev/election/docs/styles.css`
- `/Users/nat/dev/election/docs/app-k16.js` (or active app file)
- `/Users/nat/dev/election/docs/data/*.json`

Cache busting rule:
- bump query version in script tag when frontend logic changes.

## 6) Incident Checklist (Data Looks Wrong)

When dashboard rows are suspicious:

1. Verify district + form_type identity fields
2. Verify source block used in UI (`latest` vs `ect` vs `vote62` vs `killernay`)
3. Recompute:
   - `valid + invalid + blank`
   - winner from vote map
4. Confirm winner labels:
   - constituency should show candidate identity, not only party fallback
5. If form text is inconsistent, mark row with explicit note (`document_inconsistent_possible_error`)

## 7) Known Source Caveats

- ECT web figure may represent 94% phase snapshot in some analyses.
- vote62 is volunteer-sourced and may have low coverage by district.
- Official form scans can still contain clerical inconsistencies; annotate explicitly.
