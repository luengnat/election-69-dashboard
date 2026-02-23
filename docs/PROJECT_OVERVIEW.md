# Project Overview

## What This Project Does
This project reads Thai election result forms, extracts structured vote data, and compares across multiple sources:

- Read (our extracted values from form images/PDFs)
- ECT (94% web data snapshot style source)
- vote62 (volunteer source)
- killernay (official-form OCR/verification source)

It then publishes a web dashboard for reconciliation, anomaly detection, and manual verification support.

## Main Outputs

- Structured district-level dataset:
  - `docs/data/district_dashboard_data.json`
- Frontend dashboard:
  - `docs/index.html`
  - `docs/app-k16.js` (or active variant in current branch)
- Derived comparison exports:
  - CSV/JSON files in `docs/data/`

## Core Workflows

1. Acquire source files and metadata (ECT + Drive + source references)
2. OCR/AI extraction into normalized row model
3. Enrich and reconcile with source datasets (ECT/vote62/killernay)
4. Run consistency checks:
   - vote sum vs valid
   - totals consistency (`valid + invalid + blank`)
   - winner mismatch checks
5. Publish dashboard data and static frontend

## Important Scripts (High Level)

- OCR and extraction:
  - `ballot_ocr.py`
  - `ballot_extraction.py`
  - `adaptive_ocr.py`
  - `tesseract_ocr.py`
- Validation and normalization:
  - `ballot_validation.py`
  - `enrich_dashboard_sources.py`
  - `metadata_parser.py`
- Web/UI:
  - `web_ui.py`
  - `docs/index.html`
  - `docs/app-k16.js`

## Current Repository Reality

This repository contains both:
- product code (should stay stable), and
- many generated/scratch artifacts from investigation loops.

Cleanup should be done as a controlled migration, not by deleting files blindly.
See:
- `docs/REPO_CLEANUP_PLAN.md`
- `docs/OPERATIONS_RUNBOOK.md`
