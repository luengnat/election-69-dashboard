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

## Security Hygiene
- Never commit API keys, access tokens, or private keys.
- Keep local secrets in `.env` (ignored by git).
- Run local secret scan before push:

```bash
bash scripts/scan_secrets.sh
```

- CI also runs `.github/workflows/secret-scan.yml` on push/PR.
