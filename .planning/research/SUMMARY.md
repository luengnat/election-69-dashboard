# Project Research Summary

**Project:** Thai Ballot OCR System v1.1 - Scale & Web
**Domain:** Election Ballot OCR with Parallel Processing, Web Interface, Executive Summary
**Researched:** 2026-02-16
**Confidence:** HIGH

## Executive Summary

This is an enhancement to an existing Thai election ballot OCR system (v1.0) that already achieves 100% accuracy on test images. The v1.1 milestone adds three critical capabilities: parallel processing for 100-500 ballot batches, a web interface for non-technical users, and an enhanced executive summary PDF. The existing codebase is mature with well-structured OCR logic, ECT API integration for candidate validation, and working PDF generation.

The recommended approach prioritizes simplicity and code reuse: use `ThreadPoolExecutor` with rate limiting for parallel OCR (I/O-bound API calls), Gradio for a minimal web UI (10-20 lines vs 100+ for FastAPI), and extend the existing `reportlab`-based PDF functions. Path-based metadata inference from Google Drive folder structures can significantly reduce OCR complexity by pre-filling province/constituency data.

Key risks are API rate limiting (OpenRouter 20 RPM, 50 req/day free tier), memory management during batch uploads, and async state race conditions. All are preventable with semaphore-limited concurrency, explicit file cleanup, and proper locking mechanisms. The research strongly recommends implementing rate limiting from the start, not as an afterthought.

## Key Findings

### Recommended Stack

The existing Python 3.14 codebase already uses the right core libraries. Only minimal additions needed:

**Core technologies (NEW):**
- **asyncio + ThreadPoolExecutor**: Parallel OCR processing - I/O-bound API calls benefit from threads under GIL; semaphore for rate limiting
- **Gradio 5.x**: Minimal web UI - fastest path to file upload + results display with built-in progress bars and Thai text support
- **tenacity 9.x**: Retry logic - exponential backoff for API rate limits per OpenAI cookbook recommendations
- **httpx 0.28.x**: Async HTTP client - already installed, supports both sync/async for mixed workloads

**Existing stack (unchanged):**
- **reportlab 4.4.x**: PDF generation with charts - already implements constituency/batch PDFs
- **Pillow 12.x**: Zone extraction - `Image.crop()` for template-based region extraction
- **anthropic 0.79.x**: Claude Vision API fallback when OpenRouter fails

### Expected Features

**Must have (table stakes):**
- Multi-file upload for batch processing - users expect to upload 100-500 images at once
- Processing progress indicator - long-running tasks need feedback to prevent abandonment
- Results display - JSON table or markdown showing extracted vote counts
- Error handling with feedback - failed OCR should explain what went wrong
- Parallel processing - sequential processing of 100-500 ballots is impractical (42+ minutes)

**Should have (differentiators):**
- Path-based metadata inference - eliminate manual entry by parsing province/constituency from filenames/folder structure
- Real-time progress with SSE or `gr.Progress()` - show current ballot count during processing
- Executive Summary PDF with charts - one-page stakeholder overview already 90% implemented
- Confidence-based review queue - flag low-confidence results for human review

**Defer (v2+):**
- REST API endpoint - CLI already provides programmatic access
- Database persistence - JSON files sufficient for batch processing
- User authentication - single-user for v1.1
- Zone-based numeral extraction - template coordinates require calibration per form type

### Architecture Approach

The existing CLI-based architecture will be extended with a new `server/` module containing web-related code, while keeping core OCR logic in `ballot_ocr.py`. The parallel processing uses `ThreadPoolExecutor` with semaphore-limited concurrency (5-10 workers) and rate limiting (2 req/sec) to stay under API quotas.

**Major components:**
1. **Gradio Web UI** (`web_ui.py`) - File upload, progress tracking, results display, PDF download
2. **Batch Processor** (new class in `ballot_ocr.py`) - ThreadPoolExecutor with rate limiting and progress callbacks
3. **Path Metadata Parser** (new `path_parser.py`) - Regex-based extraction of province/constituency from file paths
4. **Executive Summary PDF** (existing, enhanced) - Add party vote bar chart to existing `generate_executive_summary_pdf()`

### Critical Pitfalls

1. **API Rate Limiting** - Use `asyncio.Semaphore(5-10)` with exponential backoff; OpenRouter free tier has 20 RPM, 50 req/day limits. Implement from Phase 1, not as afterthought.

2. **UploadFile in Background Tasks** - FastAPI's `UploadFile` is closed after response returns. Always save file content to disk BEFORE passing to background task. This is a documented gotcha.

3. **Async State Race Conditions** - Multiple concurrent tasks updating shared progress counters can cause inconsistent state. Use `threading.Lock` for shared mutable state or prefer immutable append-only structures.

4. **Path Encoding with Thai Characters** - Thai characters in filenames cause `UnicodeEncodeError` on different filesystems. Use `pathlib.Path` consistently and implement NFC Unicode normalization.

5. **PDF Memory Bloat** - reportLab builds entire PDF in memory. For 100+ ballots, generate in chunks (per-constituency) or use streaming build with `SimpleDocTemplate.build()`.

## Implications for Roadmap

Based on research, suggested phase structure:

### Phase 1: Parallel OCR Processing
**Rationale:** Core capability that enables all other features. Must be implemented with rate limiting from the start.
**Delivers:** Ability to process 100-500 ballots in minutes instead of hours with controlled API usage.
**Addresses:** Parallel processing from FEATURES.md
**Avoids:** Pitfall 1 (API Rate Limiting), Pitfall 2 (Numeral Accuracy Degradation)
**Key implementation:**
- `BatchProcessor` class with `ThreadPoolExecutor(max_workers=5-10)`
- Rate limiting with `threading.Lock` and time-based throttling (2 req/sec)
- Progress callback interface for UI integration
- Retry logic with `tenacity` for exponential backoff

### Phase 2: Web Interface (Gradio)
**Rationale:** Once parallel processing works, add UI for non-technical users. Gradio is fastest path.
**Delivers:** File upload, real-time progress, results display, PDF download in 10-20 lines of code.
**Uses:** Gradio 5.x from STACK.md, `gr.Progress()` for progress tracking
**Implements:** Web UI component from ARCHITECTURE.md
**Avoids:** Pitfall 3 (Memory Overflow), Pitfall 4 (Path Encoding)
**Key implementation:**
- `web_ui.py` with `gr.Interface()` or `gr.Blocks()`
- `gr.File(file_count="multiple")` for batch upload
- `gr.Progress(track_tqdm=True)` for progress bar
- Results as `gr.Dataframe()` or `gr.JSON()`

### Phase 3: Path-Based Metadata Inference
**Rationale:** Reduces OCR burden by inferring province/constituency from file paths. Enables faster, more accurate processing.
**Delivers:** Automatic metadata extraction from Google Drive folder structure patterns.
**Uses:** Regex patterns from FEATURES.md
**Avoids:** Pitfall 4 (Path Encoding) with Unicode normalization
**Key implementation:**
- `PathMetadataParser` class with regex patterns for Thai province names
- Fallback to OCR extraction if pattern matching fails
- Validation against ECT province list

### Phase 4: Executive Summary PDF Enhancement
**Rationale:** Stakeholders need one-page overview. Existing implementation is 90% complete.
**Delivers:** Enhanced PDF with party vote bar chart and anomaly highlighting.
**Uses:** Existing `generate_executive_summary_pdf()` from `ballot_ocr.py`
**Implements:** reportlab charts from STACK.md
**Avoids:** Pitfall 6 (PDF Memory Bloat) with chunked generation
**Key implementation:**
- Add `VerticalBarChart` for top 5 parties using existing reportlab imports
- Ensure anomaly highlighting works correctly
- Add timestamp and batch metadata

### Phase Ordering Rationale

- Phase 1 comes first because it is the core capability that enables batch processing at scale
- Phase 2 depends on Phase 1 for progress callbacks during parallel processing
- Phase 3 can be developed in parallel with Phase 2 but is lower priority than core web UI
- Phase 4 is independent and can be done anytime after Phase 1 provides batch results

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 3 (Path Inference):** Needs validation of actual Google Drive folder naming conventions used by election observers. The regex patterns are based on assumed conventions, not verified field usage.
- **Phase 4 (PDF Charts):** May need chart library research if existing reportlab chart support proves insufficient for desired visualizations.

Phases with standard patterns (skip research-phase):
- **Phase 1 (Parallel OCR):** Well-documented ThreadPoolExecutor patterns with rate limiting
- **Phase 2 (Gradio UI):** Official Gradio documentation is comprehensive with file upload examples

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Verified with official docs; existing codebase already uses most libraries |
| Features | HIGH | Based on official docs, codebase analysis, and established web UI patterns |
| Architecture | HIGH | Existing architecture is mature; additions follow standard Python patterns |
| Pitfalls | HIGH | Based on current industry research and FastAPI/asyncio best practices |

**Overall confidence:** HIGH

### Gaps to Address

- **Google Drive folder conventions:** The path-based metadata inference assumes specific naming patterns. Need to verify actual conventions used by election observers during Phase 3 planning.
- **Rate limit specifics:** OpenRouter free tier limits are documented as 50 req/day, 20 RPM but real-world behavior may differ. Monitor during Phase 1 testing and adjust semaphore/rate values.
- **Thai font rendering in charts:** The existing PDF code handles Thai text, but chart labels may need additional font registration. Verify during Phase 4.

## Sources

### Primary (HIGH confidence)
- Gradio Official Docs (gradio.app) - Web UI framework, file upload, progress bars
- FastAPI Official Docs (fastapi.tiangolo.com) - Background tasks, UploadFile handling
- Python asyncio Documentation (docs.python.org) - Semaphore, ThreadPoolExecutor patterns
- OpenAI Cookbook (github.com/openai/openai-cookbook) - Rate limiting with tenacity
- Existing codebase analysis (/Users/nat/dev/election/ballot_ocr.py) - Direct inspection

### Secondary (MEDIUM confidence)
- Medium: Python Concurrency in 2025 - asyncio patterns
- Medium: FastAPI vs Flask 2026 - framework comparison
- Dev.to: Comparing requests, aiohttp, httpx - HTTP client comparison
- Better Stack: Uploading Files Using FastAPI - file handling patterns

### Tertiary (LOW confidence)
- Various Medium articles on OCR accuracy and PDF generation - general best practices, need validation for Thai-specific requirements

---
*Research completed: 2026-02-16*
*Ready for roadmap: yes*
