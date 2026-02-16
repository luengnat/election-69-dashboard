---
phase: 07-metadata-inference
plan: 01
subsystem: metadata_parser
tags: [thai-text, unicode, regex, path-parsing, validation]
dependencies:
  requires: [ect_api]
  provides: [PathMetadataParser, InferredMetadata]
  affects: [batch_processor]
tech_stack:
  added: [metadata_parser.py]
  patterns: [NFC normalization, Thai regex extraction, ECT validation]
key_files:
  created: [metadata_parser.py]
  modified: []
decisions:
  - NFC normalization for consistent Thai character comparison (not NFKD)
  - Confidence scoring based on extracted fields (province +0.3, constituency +0.2, district +0.1)
  - Province validation against ECT's 77 official provinces
metrics:
  duration: 3.5 minutes
  completed_date: 2026-02-16
  task_count: 3
  file_count: 1
---

# Phase 7 Plan 1: PathMetadataParser Summary

## One-liner

PathMetadataParser class with Thai regex patterns, NFC Unicode normalization, and ECT province validation for extracting ballot metadata from file paths.

## What was accomplished

Created the metadata_parser.py module with two main classes:

1. **InferredMetadata dataclass** - Holds metadata extracted from file paths with fields for province, constituency number, district, subdistrict, polling unit, form type, source tracking, and confidence scoring.

2. **PathMetadataParser class** - Extracts Thai metadata from ballot file paths using:
   - Regex patterns for Thai patterns (เขตเลือกตั้งที่, อำเภอ, ตำบล, etc.)
   - NFC Unicode normalization for consistent Thai character comparison
   - Province validation against ECT's 77 official provinces
   - Confidence scoring based on extracted fields

## Key decisions

1. **NFC normalization** - Used NFC (Canonical Composition) for text comparison, not NFKD which is used for filename sanitization in gdrivedl.py
2. **Confidence scoring** - Implemented weighted scoring: province (+0.3), constituency (+0.2), district (+0.1)
3. **Province validation** - All province names are validated and converted to canonical Thai names via ect_data.validate_province_name()

## Files created/modified

| File | Action | Purpose |
|------|--------|---------|
| metadata_parser.py | Created | PathMetadataParser and InferredMetadata classes |

## Integration points

- **ect_api.py**: Uses `ect_data.validate_province_name()` for province validation
- **batch_processor.py**: Future integration to pre-fill BallotData before OCR

## Deviations from Plan

None - plan executed exactly as written.

## Verification results

All 6 verification criteria passed:
1. metadata_parser.py exists and is importable
2. InferredMetadata dataclass has all required fields
3. PathMetadataParser.parse_path() extracts constituency from Thai patterns
4. PathMetadataParser normalizes paths with NFC
5. Province validation uses ect_data.validate_province_name()
6. Confidence scoring accumulates correctly

## Commits

| Hash | Message |
|------|---------|
| 851b9a6 | feat(07-01): add InferredMetadata dataclass |
| aa23995 | feat(07-01): add PathMetadataParser with Thai regex patterns |
| bc2ef32 | feat(07-01): add province validation against ECT official list |

## Self-Check: PASSED

- [x] metadata_parser.py exists
- [x] Commit 851b9a6 exists
- [x] Commit aa23995 exists
- [x] Commit bc2ef32 exists
