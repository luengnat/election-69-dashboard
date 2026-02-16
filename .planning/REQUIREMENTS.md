# Requirements: Thai Election Ballot OCR v1.1

**Defined:** 2026-02-16
**Core Value:** Automated ballot verification with 100% OCR accuracy and scalable batch processing

## v1 Requirements

### Parallel Processing

- [ ] **PARA-01**: User can process 100-500 ballots concurrently with rate-limited API calls
- [ ] **PARA-02**: User sees real-time progress feedback during batch processing (X/Y ballots processed)
- [ ] **PARA-03**: System retries failed ballots with exponential backoff (max 3 retries)
- [ ] **PARA-04**: System limits concurrent API calls to prevent rate limit errors (3-5 concurrent)
- [ ] **PARA-05**: User receives summary of successful/failed ballots after batch completes

### Web Interface

- [ ] **WEB-01**: User can upload ballot images via web browser
- [ ] **WEB-02**: User can view OCR results in browser after processing
- [ ] **WEB-03**: User sees live progress bar during batch processing
- [ ] **WEB-04**: User can download results as JSON file
- [ ] **WEB-05**: User can download results as CSV file
- [ ] **WEB-06**: System displays confidence level for each extracted vote count

### Path-Based Metadata

- [ ] **META-01**: System extracts province name from Google Drive folder path
- [ ] **META-02**: System extracts constituency number from filename
- [ ] **META-03**: System validates extracted metadata against ECT province list
- [ ] **META-04**: System handles Thai character encoding in paths (Unicode normalization)
- [ ] **META-05**: System logs warning when path metadata conflicts with OCR results

### Executive Summary PDF

- [ ] **PDF-01**: User can generate executive summary PDF with key findings
- [ ] **PDF-02**: PDF includes total ballots processed, success rate, discrepancy count
- [ ] **PDF-03**: PDF includes party vote distribution bar chart
- [ ] **PDF-04**: PDF includes top candidates by vote count table
- [ ] **PDF-05**: PDF includes quality distribution pie chart (high/medium/low confidence)

## v2 Requirements

Deferred to future release.

### Advanced Web Features

- **WEB-07**: User can drag-drop folder of ballot images
- **WEB-08**: User can pause and resume batch processing
- **WEB-09**: User can configure processing options (concurrency, timeout)
- **WEB-10**: System persists job state across browser sessions

### Advanced Reporting

- **PDF-06**: PDF includes constituency comparison table
- **PDF-07**: PDF includes historical comparison with previous elections

## Out of Scope

| Feature | Reason |
|---------|--------|
| Mobile app | Web-first approach, mobile browser sufficient |
| Real-time dashboard | Batch processing with progress bar sufficient |
| Multi-model ensemble | Single model + fallback achieved 100% accuracy |
| Celery/Redis queue | In-process async sufficient for 100-500 ballots |
| User authentication | Single-user tool, no auth needed for v1.1 |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| PARA-01 | Phase 5 | Pending |
| PARA-02 | Phase 5 | Pending |
| PARA-03 | Phase 5 | Pending |
| PARA-04 | Phase 5 | Pending |
| PARA-05 | Phase 5 | Pending |
| WEB-01 | Phase 6 | Pending |
| WEB-02 | Phase 6 | Pending |
| WEB-03 | Phase 6 | Pending |
| WEB-04 | Phase 6 | Pending |
| WEB-05 | Phase 6 | Pending |
| WEB-06 | Phase 6 | Pending |
| META-01 | Phase 7 | Pending |
| META-02 | Phase 7 | Pending |
| META-03 | Phase 7 | Pending |
| META-04 | Phase 7 | Pending |
| META-05 | Phase 7 | Pending |
| PDF-01 | Phase 8 | Pending |
| PDF-02 | Phase 8 | Pending |
| PDF-03 | Phase 8 | Pending |
| PDF-04 | Phase 8 | Pending |
| PDF-05 | Phase 8 | Pending |

**Coverage:**
- v1 requirements: 21 total
- Mapped to phases: 21
- Unmapped: 0 ✓

---
*Requirements defined: 2026-02-16*
*Last updated: 2026-02-16 after initial definition*
