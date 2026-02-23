# Documentation Index

This folder contains operational docs for the dashboard and data pipeline.

## Core Docs

- `PROJECT_OVERVIEW.md`
  - Scope, architecture, and major workflows.
- `DATA_CONTRACTS.md`
  - Data schema expectations for dashboard JSON/CSV artifacts.
- `OPERATIONS_RUNBOOK.md`
  - Step-by-step run, validate, regenerate, and publish process.
- `CURRENT_STATE.md`
  - Current project status snapshot and known caveats.

## Data Outputs

Primary dashboard dataset:
- `docs/data/district_dashboard_data.json`

Common validation/report exports:
- `docs/data/recheck_all_vs_killernay_summary.json`
- `docs/data/recheck_all_vs_killernay_diffs.csv`
- `docs/data/recheck_all_partylist_sum_issues.csv`
- `docs/data/crosscheck_latest_vs_killernay_detailed.csv`
- `docs/data/crosscheck_integrity_issues.csv`

## Frontend Entrypoints

- `docs/index.html`
- `docs/app-k16.js`
- `docs/styles.css`

