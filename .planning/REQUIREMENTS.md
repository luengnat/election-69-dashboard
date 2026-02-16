# Requirements: Thai Election Ballot OCR v1.1

**Defined:** 2026-02-16
**Core Value:** Automated ballot verification with 100% OCR accuracy and ECT data cross-validation

---

## v1.1 Requirements

Requirements for Scale & Web milestone. Each maps to roadmap phases.

### Parallel Processing (PARA)

- [ ] **PARA-01**: User can process 100-500 ballot images in a single batch
- [ ] **PARA-02**: System processes ballots concurrently using ThreadPoolExecutor
- [ ] **PARA-03**: System enforces API rate limiting (2 req/sec max) to avoid quota exhaustion
- [ ] **PARA-04**: System retries failed OCR requests with exponential backoff
- [ ] **PARA-05**: User receives real-time progress updates during batch processing
- [ ] **PARA-06**: System preserves 100% OCR accuracy when processing in parallel
- [ ] **PARA-07**: System cleans up memory after every 50 ballots to prevent OOM

### Web Interface (WEB)

- [ ] **WEB-01**: User can upload multiple ballot images (100-500) via web UI
- [ ] **WEB-02**: User can view extracted vote counts in a structured table
- [ ] **WEB-03**: User can download constituency PDF reports from web UI
- [ ] **WEB-04**: User can download batch summary PDF from web UI
- [ ] **WEB-05**: User sees processing progress bar during batch operations
- [ ] **WEB-06**: User receives error messages when individual ballots fail OCR
- [ ] **WEB-07**: Web UI supports Thai text display for province/constituency names

### Metadata Inference (META)

- [ ] **META-01**: System extracts province name from Google Drive folder path
- [ ] **META-02**: System extracts constituency number from file path
- [ ] **META-03**: System validates inferred province against ECT province list
- [ ] **META-04**: System falls back to OCR extraction when path parsing fails
- [ ] **META-05**: System normalizes Thai Unicode in file paths (NFC normalization)

### Executive Summary PDF (PDF)

- [ ] **PDF-01**: User can generate one-page executive summary PDF
- [ ] **PDF-02**: Executive summary includes total ballots processed count
- [ ] **PDF-03**: Executive summary includes discrepancy summary by severity
- [ ] **PDF-04**: Executive summary includes bar chart of top 5 parties by votes
- [ ] **PDF-05**: Executive summary includes timestamp and batch metadata

---

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Zone-Based Extraction

- **ZONE-01**: System crops ballot images to numeric regions before OCR
- **ZONE-02**: System maintains calibrated zone coordinates for 6 form variants
- **ZONE-03**: System improves OCR speed 10-50x via zone extraction

### Advanced Web Features

- **WEB-08**: User can resume interrupted batch processing
- **WEB-09**: User can review low-confidence results in a queue
- **WEB-10**: User can authenticate with Google account

---

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Mobile app | Web-first approach, responsive Gradio sufficient |
| Real-time dashboard | Batch processing sufficient for election monitoring use case |
| Multi-model ensemble | Single model with fallback achieved 100% accuracy |
| REST API | CLI provides programmatic access, web UI for interactive use |
| Database persistence | JSON files sufficient for batch processing workflows |
| WebSocket progress | SSE/gr.Progress simpler for one-way progress updates |

---

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| PARA-01 | Phase 5 | Pending |
| PARA-02 | Phase 5 | Pending |
| PARA-03 | Phase 5 | Pending |
| PARA-04 | Phase 5 | Pending |
| PARA-05 | Phase 5 | Pending |
| PARA-06 | Phase 5 | Pending |
| PARA-07 | Phase 5 | Pending |
| WEB-01 | Phase 6 | Pending |
| WEB-02 | Phase 6 | Pending |
| WEB-03 | Phase 6 | Pending |
| WEB-04 | Phase 6 | Pending |
| WEB-05 | Phase 6 | Pending |
| WEB-06 | Phase 6 | Pending |
| WEB-07 | Phase 6 | Pending |
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
- v1.1 requirements: 24 total
- Mapped to phases: 24
- Unmapped: 0 ✓

---

*Requirements defined: 2026-02-16*
*Last updated: 2026-02-16 after v1.1 scoping*
