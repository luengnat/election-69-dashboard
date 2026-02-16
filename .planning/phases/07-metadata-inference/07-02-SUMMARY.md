---
phase: 07-metadata-inference
plan: 02
subsystem: batch_processor
tags: [metadata-integration, ocr-fallback, path-parsing, confidence-tracking]
dependencies:
  requires: [metadata_parser, ballot_ocr]
  provides: [BatchProcessor.metadata_parser, metadata pre-fill, source tracking]
  affects: [web_ui]
tech_stack:
  added: []
  patterns: [gap-filling merge, metadata source tracking, mismatch logging]
key_files:
  created: []
  modified: [batch_processor.py]
decisions:
  - OCR is authoritative - path metadata only fills gaps (never overwrites)
  - Metadata source tracked in confidence_details for auditing
  - Province mismatches logged to detect path/OCR conflicts
metrics:
  duration: 4 minutes
  completed_date: 2026-02-16
  task_count: 3
  file_count: 1
---

# Phase 7 Plan 2: BatchProcessor Metadata Integration Summary

## One-liner

BatchProcessor integration with PathMetadataParser for pre-filling ballot metadata from file paths before OCR extraction, with OCR as authoritative fallback and source tracking for auditing.

## What was accomplished

Modified batch_processor.py to integrate path-based metadata extraction with OCR processing:

1. **PathMetadataParser initialization** - Added import and initialization of PathMetadataParser in BatchProcessor.__init__() for access to path-based metadata extraction.

2. **Metadata pre-fill logic** - Modified process_single() to extract path metadata before OCR call and pre-fill BallotData fields (province, constituency_number, district, polling_unit) only when OCR returned empty values.

3. **Source tracking and mismatch logging** - Added confidence_details tracking to record whether each field came from path or OCR, and log any province mismatches between path and OCR for debugging.

## Key decisions

1. **OCR is authoritative** - Path metadata only fills gaps where OCR returned empty/None. Never overwrites OCR-extracted values with path-derived values.

2. **Metadata source tracking** - All field origins are recorded in confidence_details["metadata_source"] for auditing transparency.

3. **Mismatch logging** - Province mismatches between path and OCR are logged in confidence_details["province_mismatch"] to detect potential path naming issues.

## Files created/modified

| File | Action | Purpose |
|------|--------|---------|
| batch_processor.py | Modified | Added PathMetadataParser integration, pre-fill logic, source tracking |

## Integration points

- **metadata_parser.py**: Uses `PathMetadataParser().parse_path()` for path-based extraction
- **ballot_ocr.py**: Pre-fills BallotData before OCR extraction, merges after
- **ect_api.py**: Province validation through PathMetadataParser's ECT integration

## Deviations from Plan

None - plan executed exactly as written.

## Verification results

All 5 verification criteria passed:
1. BatchProcessor imports PathMetadataParser from metadata_parser
2. BatchProcessor.__init__ creates self.metadata_parser instance
3. process_single() calls metadata_parser.parse_path() before OCR
4. process_single() pre-fills BallotData fields only when OCR returned empty
5. confidence_details["metadata_source"] tracks field origins

## Commits

| Hash | Message |
|------|---------|
| dcf22e9 | feat(07-02): add PathMetadataParser to BatchProcessor |
| c201239 | feat(07-02): add metadata pre-fill and OCR fallback logic |
| 41eb7fc | feat(07-02): add metadata source tracking to confidence_details |

## Self-Check: PASSED

- [x] batch_processor.py modified with all expected changes
- [x] Commit dcf22e9 exists
- [x] Commit c201239 exists
- [x] Commit 41eb7fc exists
