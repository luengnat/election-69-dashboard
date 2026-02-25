# Election 69 Dashboard

District-level extraction + verification dashboard published via GitHub Pages.

## Data Sources
- Drive/Gemini extraction snapshots
- ECT static reference
- Cross-check with killernay OCR dataset

## Site
After GitHub Pages deploy, open:
- https://luengnat.github.io/election-69-dashboard/

## Operations Manual (TH)
- Detailed self-run manual (without Codex):
  - `docs/MANUAL_SELF_RUN_TH.md`

## Regenerate Export CSV
Generate the two 100%-level export files from dashboard data:

```bash
cd /tmp/election-main
python3 scripts/export_first2_csv.py \
  --input docs/data/district_dashboard_data.json \
  --out-const export_first2_constituency_100.csv \
  --out-party export_first2_party_list_100.csv
```

## Security Hygiene
- Never commit API keys, access tokens, or private keys.
- Keep local secrets in `.env` (ignored by git).
- Run local secret scan before push:

```bash
bash scripts/scan_secrets.sh
```

- CI also runs `.github/workflows/secret-scan.yml` on push/PR.
