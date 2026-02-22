# Current App State

Last updated: 2026-02-22

## Scope

This project currently ships two main surfaces:

- OCR/extraction app (`web_ui.py`, verifier tooling)
- Public comparison dashboard (`docs/` on GitHub Pages)

## Dashboard State (`docs/`)

- Active page: `docs/index.html`
- Active script: `docs/app-k16.js`
- Active stylesheet: `docs/styles.css`
- Map mode: district-level choropleth (no bubble markers)
  - Red: constituency total > party-list total
  - Blue: party-list total > constituency total
  - Neutral center: no skew
  - Gray: no data

## Data Snapshot

From `docs/data/district_dashboard_data.json`:

- Total rows: 800
- Rows with extracted valid votes: 775
- Rows with ECT totals attached: 800
- Rows with vote62 totals attached: 771
- Rows with embedded killernay totals attached: 772

District skew coverage (computed from rows with both forms + complete totals):

- Districts with both forms and computable totals: 386
- Skew districts: 365
- Normal districts: 21

## killernay Validation Status

Latest generated artifacts:

- `comparison_unified_preview.csv`
- `comparison_unified_preview.json`
- `killernay_diff_audit.csv`
- `killernay_diff_audit.json`

Current result:

- `rows_with_ref=769`
- `exact_match=769`
- `mismatch_rows=0`

## Known Caveats

- `sources.killernay` embedded inside `docs/data/district_dashboard_data.json` can lag behind latest killernay CSV refresh for specific rows.
  - Cross-check reports (`compare_sources_unified.py` + `audit_killernay_diffs.py`) are the source of truth for current parity.
- Map polygon source is `docs/data/constituencies_optimized_4dp.geojson` (large file). First load can be slower on cold cache.
- There are known districts still missing complete source files from upstream publication; those appear as gray/no-data in map.

## How To Re-Validate

```bash
./venv/bin/python compare_sources_unified.py
./venv/bin/python audit_killernay_diffs.py
```

Optional metadata refresh from latest source CSV/API joins:

```bash
./venv/bin/python enrich_dashboard_sources.py
```

## Recent Manual Overrides

Manual, user-verified corrections are tracked in:

- `docs/data/district_dashboard_data.json` -> `validation_notes`

