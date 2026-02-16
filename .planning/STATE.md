# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-16)

**Core value:** Automated ballot verification with 100% OCR accuracy on test images and ECT data cross-validation
**Current focus:** v1.1 Scale & Web - COMPLETE

## Current Position

Phase: 8 of 8 (Executive Summary) - COMPLETE
Plan: 1 of 1 in current phase
Status: v1.1 complete - All phases finished, ready for release
Last activity: 2026-02-17 - Completed 08-01 (One-page executive summary PDF)

Progress: [##########] 100% (v1.1 complete)

## Performance Metrics

**Velocity:**
- Total plans completed (v1.0): 4
- v1.1 plans completed: 7 (Phase 5: 2, Phase 6: 2, Phase 7: 2, Phase 8: 1)
- v1.1 plans created: 5 (Phase 6: 2, Phase 7: 2, Phase 8: 1)
- Total execution time: 75 min (Phase 5.01-5.02: 27min, Phase 6.01-6.02: 25min, Phase 7.01-7.02: 7.5min, Phase 8.01: 15min)

**By Phase (v1.0):**

| Phase | Plans | Status |
|-------|-------|--------|
| 1. OCR Accuracy | 1 | Complete |
| 2. ECT Integration | 1 | Complete |
| 3. Aggregation | 1 | Complete |
| 4. PDF Export | 1 | Complete |

**v1.1 Progress:**

| Phase | Plans | Requirements | Status |
|-------|-------|--------------|--------|
| 5. Parallel Processing | 2/2 | PARA-01 to PARA-07 | Complete |
| 6. Web Interface | 2/2 | WEB-01 to WEB-07 | Complete |
| 7. Metadata Inference | 2/2 | META-01 to META-05 | Complete |
| 8. Executive Summary | 1/1 | PDF-01 to PDF-05 | Complete |

## Accumulated Context

### v1.0 Lessons Learned
- Single model (Gemma 3 12B IT) achieved 100% accuracy on test images
- Claude Vision fallback provides reliability
- IQR-based outlier detection statistically sound
- reportlab sufficient for PDF generation
- CLI workflow is functional but limited for non-technical users

### Key Technical Decisions (v1.1)

| Decision | Rationale | Source |
|----------|-----------|--------|
| ThreadPoolExecutor for parallelism | I/O-bound API calls benefit from threads under GIL | Research |
| Gradio for web UI | Fastest implementation (10-20 lines vs 100+ for FastAPI) | Research |
| Semaphore rate limiting | Prevents API quota exhaustion (OpenRouter 20 RPM, 50/day) | Research |
| Path-based metadata | Reduces OCR burden by pre-filling province/constituency | Research |
| tenacity library for retry | Exponential backoff with minimal code, well-tested library | Phase 5.01 |
| Sequential processing as default | Backward compatibility, parallel requires explicit --parallel flag | Phase 5.01 |
| 2.0 req/sec rate limit | Stays under OpenRouter free tier limits (20 RPM, 50/day) | Phase 5.01 |
| Protocol over ABC for callbacks | Duck-typed protocol enables any class with matching methods | Phase 5.02 |
| 50 ballot memory cleanup interval | Balances overhead vs memory safety for large batches | Phase 5.02 |
| gr.Progress() for progress bar | Built-in Gradio progress tracking with minimal code | Phase 6.01 |
| 100 result display limit | Prevents UI overload for large batches | Phase 6.01 |
| Bilingual UI labels | Thai + English for accessibility | Phase 6.01 |
| gr.State for ballot results | Persist results between process and download actions | Phase 6.02 |
| Separate export buttons | PDF, JSON, and CSV exports for different use cases | Phase 6.02 |
| Compact vote summary in table | Shows key info without expanding full details | Phase 6.02 |
| NFC Unicode normalization | Consistent Thai character comparison for path parsing | Phase 7.01 |
| Confidence scoring for metadata | Province (+0.3), constituency (+0.2), district (+0.1) | Phase 7.01 |
| ECT province validation | Only valid Thai provinces (77 official) stored | Phase 7.01 |
| OCR is authoritative | Path metadata only fills gaps, never overwrites OCR values | Phase 7.02 |
| Metadata source tracking | confidence_details tracks field origin (path vs OCR) | Phase 7.02 |
| Province mismatch logging | Logs path/OCR conflicts for debugging | Phase 7.02 |
| HorizontalBarChart for Thai labels | Better readability for party names in PDF charts | Phase 8.01 |
| Compact one-page PDF layout | 0.5 inch margins, 8-10pt fonts for executive summary | Phase 8.01 |
| Color-coded discrepancy summary | CRITICAL(red), MEDIUM(orange), LOW(blue), NONE(green) | Phase 8.01 |
| Top 5 parties limit on charts | Ensures content fits on single page | Phase 8.01 |

### Pending Todos

None yet.

### Blockers/Concerns

- ~~**API Rate Limits:** OpenRouter free tier has 20 RPM, 50 req/day. Must implement rate limiting from Phase 5 start.~~ (RESOLVED - RateLimiter implemented in Phase 5.01)
- ~~**Google Drive Path Conventions:** Path-based metadata assumes specific naming patterns - needs validation during Phase 7.~~ (RESOLVED - Implemented with fallback to OCR in Phase 7.02)

## Session Continuity

Last session: 2026-02-17
Stopped at: v1.1 complete - All phases finished
Resume file: None
