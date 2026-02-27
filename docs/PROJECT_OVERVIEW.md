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
  - `/Users/nat/dev/election/docs/data/district_dashboard_data.json`
- Frontend dashboard:
  - `/Users/nat/dev/election/docs/index.html`
  - `/Users/nat/dev/election/docs/app-k16.js` (or active variant in current branch)
- Derived comparison exports:
  - CSV/JSON files in `/Users/nat/dev/election/docs/data/`

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
  - `/Users/nat/dev/election/ballot_ocr.py`
  - `/Users/nat/dev/election/ballot_extraction.py`
  - `/Users/nat/dev/election/adaptive_ocr.py`
  - `/Users/nat/dev/election/tesseract_ocr.py`
- Validation and normalization:
  - `/Users/nat/dev/election/ballot_validation.py`
  - `/Users/nat/dev/election/enrich_dashboard_sources.py`
  - `/Users/nat/dev/election/metadata_parser.py`
- Web/UI:
  - `/Users/nat/dev/election/web_ui.py`
  - `/Users/nat/dev/election/docs/index.html`
  - `/Users/nat/dev/election/docs/app-k16.js`

## Current Repository Reality

This repository contains both:
- product code (should stay stable), and
- many generated/scratch artifacts from investigation loops.

Cleanup should be done as a controlled migration, not by deleting files blindly.
See:
- `/Users/nat/dev/election/docs/REPO_CLEANUP_PLAN.md`
- `/Users/nat/dev/election/docs/OPERATIONS_RUNBOOK.md`
