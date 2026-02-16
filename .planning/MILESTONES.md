# Milestones

## v1.0 MVP — 2026-02-16

**Phases:** 4 | **Plans:** 4 | **LOC:** 4,966 Python

### Key Accomplishments

1. 100% OCR accuracy with confidence scoring, batch processing, Thai numerals
2. ECT integration with 3,491 candidates, vote matching, discrepancy detection
3. Aggregation engine, statistical analysis, executive summary reports
4. PDF export with charts, constituency reports, batch summaries

### Archived Files

- `.planning/milestones/v1.0-ROADMAP.md`
- `.planning/milestones/v1.0-REQUIREMENTS.md`

---

## v1.1 Scale & Web — 2026-02-17

**Phases:** 4 (5-8) | **Plans:** 7 | **Execution Time:** 75 min

### Key Accomplishments

1. **Parallel Processing**: ThreadPoolExecutor with rate limiting (2 req/sec), tenacity retry logic, memory cleanup for large batches
2. **Web Interface**: Gradio-based UI with real-time progress tracking, bilingual (Thai/English) labels, PDF/JSON/CSV exports
3. **Metadata Inference**: PathMetadataParser with NFC normalization, ECT province validation, OCR fallback
4. **Executive Summary**: One-page PDF with top 5 parties chart, color-coded discrepancy summary, compact layout

### Technical Decisions

| Decision | Rationale |
|----------|-----------|
| ThreadPoolExecutor | I/O-bound API calls benefit from threads under GIL |
| Gradio for web UI | Fastest implementation (10-20 lines vs 100+ for FastAPI) |
| 2.0 req/sec rate limit | Stays under OpenRouter free tier limits |
| NFC Unicode normalization | Consistent Thai character comparison |
| HorizontalBarChart | Better readability for Thai party names |

### Files Delivered

- `batch_processor.py` - Parallel OCR processing
- `web_ui.py` - Gradio web interface
- `metadata_parser.py` - Path-based metadata extraction
- `ballot_ocr.py` - Enhanced with executive summary generation

---

_Next milestone: v1.2 (planning required)_
