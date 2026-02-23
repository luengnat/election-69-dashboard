# Repository Cleanup Plan

## Objective
Reduce random workspace clutter while preserving reproducibility and auditability.

## Current Pain Points

- Root directory contains many ad-hoc outputs (`tmp_*`, `drive2_*`, one-off JSONL/CSV).
- Hard to distinguish production artifacts vs scratch files.
- Onboarding is slow because data products and code paths are mixed.

## Principles

1. Do not delete investigative artifacts blindly.
2. Separate **source code**, **stable datasets**, and **scratch outputs**.
3. Enforce naming and location conventions for generated files.

## Proposed Structure (Incremental)

- Keep product code in root as-is for now.
- Keep stable web data in:
  - `/Users/nat/dev/election/docs/data/`
- Move temporary investigation outputs into:
  - `/Users/nat/dev/election/scratch/`
  - `/Users/nat/dev/election/scratch/<date-or-topic>/`

## Immediate Actions Completed

- Added ignore rules for common scratch patterns in:
  - `/Users/nat/dev/election/.gitignore`
- Added documentation backbone:
  - `/Users/nat/dev/election/docs/PROJECT_OVERVIEW.md`
  - `/Users/nat/dev/election/docs/DATA_CONTRACTS.md`
  - `/Users/nat/dev/election/docs/OPERATIONS_RUNBOOK.md`

## Next Cleanup Actions (Recommended)

1. Create `scratch/` and move existing untracked investigation outputs there.
2. Add a small `scripts/` helper to archive old scratch outputs by date.
3. Define one canonical frontend app filename (avoid many `app-k*.js` variants).
4. Add CI checks for:
   - malformed row keys
   - vote sum consistency
   - duplicated district-form rows

## Definition of Done for Cleanup v1

- New contributors can identify:
  - where to run app,
  - where canonical data lives,
  - where to put temporary experiments,
  in under 10 minutes.
