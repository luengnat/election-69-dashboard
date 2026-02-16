# Roadmap: Thai Election Ballot OCR

## Milestones

- **v1.0 MVP** - Phases 1-4 (shipped 2026-02-16)
- **v1.1 Scale & Web** - Phases 5-8 (in progress)

## Overview

This roadmap continues from v1.0 MVP (4,966 LOC Python with 100% OCR accuracy). The v1.1 milestone adds parallel batch processing, a web interface for non-technical users, intelligent metadata extraction from file paths, and an enhanced executive summary PDF.

## Phases

**Phase Numbering:**
- Phases 1-4: v1.0 MVP (shipped)
- Phases 5-8: v1.1 Scale & Web (current milestone)

<details>
<summary>v1.0 MVP (Phases 1-4) - SHIPPED 2026-02-16</summary>

### Phase 1: OCR Accuracy & Core Extraction
**Goal**: Extract vote counts from ballot images with confidence scoring
**Plans**: 1 plan (complete)

### Phase 2: ECT Integration & Matching
**Goal**: Validate extracted data against official ECT candidate data
**Plans**: 1 plan (complete)

### Phase 3: Results Aggregation & Analysis
**Goal**: Aggregate results and detect statistical anomalies
**Plans**: 1 plan (complete)

### Phase 4: PDF Export Implementation
**Goal**: Generate PDF reports with charts and constituency summaries
**Plans**: 1 plan (complete)

**Key accomplishments:**
- 100% OCR accuracy with confidence scoring
- 3,491 candidates from ECT API
- Statistical analysis with outlier detection
- PDF export with charts

</details>

### v1.1 Scale & Web (In Progress)

**Milestone Goal:** Scale batch processing to 100-500 ballots with parallel execution and add a minimal web interface for upload and results viewing.

- [ ] **Phase 5: Parallel Processing** - Concurrent OCR processing with rate limiting and progress tracking
- [ ] **Phase 6: Web Interface** - Gradio-based UI for batch upload and results viewing
- [ ] **Phase 7: Metadata Inference** - Automatic province/constituency extraction from file paths
- [ ] **Phase 8: Executive Summary** - One-page PDF with charts and batch statistics

## Phase Details

### Phase 5: Parallel Processing
**Goal**: Users can process 100-500 ballot images concurrently with controlled API usage
**Depends on**: Phase 4 (v1.0 - builds on existing OCR infrastructure)
**Requirements**: PARA-01, PARA-02, PARA-03, PARA-04, PARA-05, PARA-06, PARA-07
**Success Criteria** (what must be TRUE):
  1. User can submit 100-500 ballot images in a single batch and receive complete results
  2. User sees real-time progress updates during batch processing (X of Y ballots processed)
  3. System maintains 100% OCR accuracy when processing in parallel (same as sequential)
  4. System automatically retries failed API requests without stopping the batch
  5. System cleans up memory during large batches to prevent out-of-memory errors
**Plans**: 2 plans

Plans:
- [ ] 05-01: Implement BatchProcessor with ThreadPoolExecutor, rate limiting, and retry logic
- [ ] 05-02: Add progress callback interface and memory cleanup for large batches

### Phase 6: Web Interface
**Goal**: Users can upload ballots and view results through a web browser
**Depends on**: Phase 5 (uses progress callbacks from parallel processing)
**Requirements**: WEB-01, WEB-02, WEB-03, WEB-04, WEB-05, WEB-06, WEB-07
**Success Criteria** (what must be TRUE):
  1. User can upload 100-500 ballot images via web browser and see them queued for processing
  2. User sees a progress bar that updates in real-time during batch processing
  3. User can view extracted vote counts in a structured table after processing completes
  4. User can download constituency and batch summary PDFs directly from the web UI
  5. User sees clear error messages when individual ballots fail OCR, with Thai text support
**Plans**: 2 plans

Plans:
- [ ] 06-01: Create Gradio web UI with multi-file upload and real-time progress tracking
- [ ] 06-02: Add results display table, PDF downloads, and Thai text support

### Phase 7: Metadata Inference
**Goal**: System automatically extracts province and constituency from file paths, reducing OCR burden
**Depends on**: Phase 5 (integrates with batch processing pipeline)
**Requirements**: META-01, META-02, META-03, META-04, META-05
**Success Criteria** (what must be TRUE):
  1. System correctly extracts province name from Google Drive folder path (e.g., "/path/Bangkok/..." -> "Bangkok")
  2. System correctly extracts constituency number from file path (e.g., "district_4.jpg" -> constituency 4)
  3. System validates extracted province against ECT province list and flags invalid names
  4. System falls back to OCR extraction when path parsing fails
**Plans**: 2 plans

Plans:
- [ ] 07-01: Implement PathMetadataParser with Thai regex patterns and Unicode normalization
- [ ] 07-02: Integrate with batch processor, add ECT validation, and OCR fallback

### Phase 8: Executive Summary
**Goal**: Users can generate a one-page executive summary PDF with key batch statistics and charts
**Depends on**: Phase 5 (uses batch processing results)
**Requirements**: PDF-01, PDF-02, PDF-03, PDF-04, PDF-05
**Success Criteria** (what must be TRUE):
  1. User can generate a one-page executive summary PDF from any batch result
  2. Executive summary displays total ballots processed count and batch metadata
  3. Executive summary includes discrepancy summary organized by severity level
  4. Executive summary includes a bar chart showing top 5 parties by total votes
**Plans**: 1 plan

Plans:
- [ ] 08-01: Create one-page executive summary with compact layout, top 5 parties chart, and web UI download

## Progress

**Execution Order:**
Phases execute in numeric order: 5 -> 6 -> 7 -> 8

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. OCR Accuracy | v1.0 | 1/1 | Complete | 2026-02-16 |
| 2. ECT Integration | v1.0 | 1/1 | Complete | 2026-02-16 |
| 3. Aggregation | v1.0 | 1/1 | Complete | 2026-02-16 |
| 4. PDF Export | v1.0 | 1/1 | Complete | 2026-02-16 |
| 5. Parallel Processing | v1.1 | 0/2 | Not started | - |
| 6. Web Interface | v1.1 | 0/2 | Not started | - |
| 7. Metadata Inference | v1.1 | 0/2 | Not started | - |
| 8. Executive Summary | v1.1 | 0/1 | Not started | - |

---

## Current Status

**Active Milestone:** v1.1 Scale & Web

**Next Action:** Run `/gsd:plan-phase 5` to start Phase 5 planning
