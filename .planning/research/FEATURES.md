# Feature Research

**Domain:** Thai Election Ballot OCR - Parallel Processing, Web Interface, Executive Summary
**Researched:** 2026-02-16
**Confidence:** HIGH (based on official docs, current codebase analysis, and web research)

## Executive Summary

For v1.1 "Scale & Web" milestone, the key features are:
1. **Parallel OCR Processing** - Use `ThreadPoolExecutor` (I/O-bound API calls) with rate limiting
2. **Web Interface** - Gradio for fastest MVP; FastAPI alternative for production
3. **Executive Summary PDF** - Already 90% implemented, minor enhancements needed

**Critical Insight:** Number recognition is more important than text OCR. Metadata (province, constituency) can be inferred from Google Drive folder names and filenames. Focus OCR on Thai numerals (๐๑๒๓๔๕๖๗๘๙) and Arabic numerals (0-9).

## Feature Landscape

### Table Stakes (Users Expect These)

Features users assume exist. Missing these = product feels incomplete.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **Multi-file upload** | Batch processing requires uploading multiple ballot images | LOW | Gradio: `gr.File(file_count="multiple")` or FastAPI: `UploadFile` |
| **Processing progress indicator** | Long-running tasks need feedback to prevent user abandonment | MEDIUM | Use `gr.Progress()` with tqdm, or SSE for FastAPI |
| **Results display** | Users need to see extracted vote counts after processing | LOW | JSON table, markdown output, or DataTable component |
| **Error handling with feedback** | Failed OCR attempts should explain what went wrong | MEDIUM | Confidence scores already exist; add error messages |
| **Download results** | Export processed data for further analysis | LOW | Already have JSON + PDF export |
| **Parallel processing** | 100-500 ballots sequentially is too slow (42+ min) | MEDIUM | Use ThreadPoolExecutor for I/O-bound API calls |

### Differentiators (Competitive Advantage)

Features that set the product apart. Not required, but valuable.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **High-accuracy numeral OCR** | Thai numerals + Arabic digits with 100% target (already achieved) | N/A | Existing implementation works well |
| **ECT cross-validation** | Compare against official Election Commission data | N/A | Already implemented with 3,491 candidates |
| **Path-based metadata inference** | Eliminate manual entry by parsing province/constituency from filenames | LOW | Regex patterns for structured paths |
| **Parallel OCR with real-time progress** | Process 100-500 ballots in minutes instead of hours | MEDIUM | ThreadPoolExecutor with rate limiting |
| **Executive Summary PDF with charts** | One-page overview for stakeholders with key statistics and anomalies | LOW | Already have `generate_executive_summary_pdf()` |
| **Zone-based numeral extraction** | Higher accuracy by focusing OCR on numeric regions only | MEDIUM | Template-based coordinate extraction |
| **Confidence-based review queue** | Flag low-confidence results for human review automatically | LOW | Filter by confidence_level < HIGH |
| **Automatic metadata inference** | Province/constituency from folder names, filenames | LOW | Reduces OCR burden, improves accuracy |

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem good but create problems.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| **Real-time streaming OCR** | Immediate feedback as each ballot completes | Adds complexity; API rate limits may throttle; websockets needed | Batch with progress bar is sufficient for 100-500 ballots |
| **Full document OCR (all text)** | Complete extraction of all ballot content | Slower, lower accuracy on numbers, AI hallucinates handwritten Thai names | Zone-based extraction focused on numeric vote counts; use ECT data for names |
| **Drag-and-drop folder upload** | Easy bulk upload | Browser security restrictions; complex implementation | Multiple file picker or ZIP upload |
| **Database persistence** | Store all results for historical queries | Overkill for batch processing use case; adds migration burden | JSON files + optional SQLite for single-session caching |
| **User accounts with roles** | Multi-user organizations | Adds auth complexity, session management | Single-user or simple shared password for v1.1 |
| **API endpoint for programmatic access** | Integration with other systems | Premature optimization; security concerns | CLI already provides programmatic access |
| **Real-time dashboard** | Live updates as ballots come in | Batch processing model doesn't fit; adds complexity | Show summary after batch completes |
| **Multi-model ensemble** | Better accuracy | Single model achieved 100% on test images | Not needed |

## Feature Dependencies

```
Parallel OCR Processing
    └──requires──> Progress Tracking (gr.Progress or SSE)
    └──requires──> Batch File Upload
    └──requires──> Rate Limiting (for API quotas)

Zone-based Numeral Extraction
    └──requires──> Form Type Detection (existing)
    └──requires──> Template Coordinates per form type

Path-based Metadata Inference
    └──requires──> Filename Convention Documentation
    └──enhances──> Parallel OCR (reduces per-image API calls)

Executive Summary PDF
    └──requires──> Aggregated Results (existing aggregate_ballot_results)
    └──requires──> Anomaly Detection (existing detect_anomalous_constituencies)

Web UI
    └──requires──> Gradio OR FastAPI
    └──requires──> Progress Tracking
    └──uses──> Parallel OCR
    └──uses──> PDF Export (existing)
```

### Dependency Notes

- **Parallel OCR requires Progress Tracking:** Users need to see batch progress; without it, long-running batches feel broken
- **Parallel OCR requires Rate Limiting:** OpenRouter API has rate limits; need token bucket or simple delay between requests
- **Zone-based extraction requires Form Type Detection:** Already implemented; need to add coordinate templates for each of the 6 form types
- **Path-based inference enhances Parallel OCR:** By inferring metadata from path, we reduce API round-trips for each image
- **Web UI uses but does not require Parallel OCR:** Sequential processing works; parallel is an optimization

## MVP Definition

### Launch With (v1.1)

Minimum viable product -- what is needed to validate the concept.

- [ ] **Gradio web interface** -- Upload ballots, view results, download PDFs
  - Multiple file upload
  - Progress bar during processing
  - Results table display
  - PDF download buttons

- [ ] **Parallel OCR processing** -- Process 100-500 ballots efficiently
  - `concurrent.futures.ThreadPoolExecutor` for I/O-bound API calls
  - `max_workers=5-10` with rate limiting (2 req/sec)
  - Progress bar integration with `gr.Progress(track_tqdm=True)`

- [ ] **Path-based metadata inference** -- Parse province/constituency from file paths
  - Support pattern: `{province}_{constituency}_{station}_{seq}.png`
  - Fallback to OCR extraction if pattern fails

- [ ] **Executive Summary PDF completion** -- One-page stakeholder overview
  - Already have `generate_executive_summary_pdf()` function
  - Ensure anomaly highlighting works
  - Add top-line statistics

### Add After Validation (v1.2)

Features to add once core is working.

- [ ] **Zone-based numeral extraction** -- Template coordinates for faster, more accurate number OCR
- [ ] **Confidence review queue** -- Filter and export low-confidence results
- [ ] **ZIP file upload support** -- Single upload for large batches
- [ ] **WebSocket progress updates** -- Real-time progress bar without polling

### Future Consideration (v2+)

Features to defer until product-market fit is established.

- [ ] **REST API endpoint** -- Programmatic access for integrations
- [ ] **Database persistence** -- Historical query capability
- [ ] **Multi-user authentication** -- Organization-level access control

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Gradio web UI | HIGH | LOW | P1 |
| Parallel OCR | HIGH | MEDIUM | P1 |
| Progress tracking | HIGH | LOW | P1 |
| Executive Summary PDF | MEDIUM | LOW | P1 |
| Path-based metadata | MEDIUM | LOW | P2 |
| Zone-based extraction | MEDIUM | MEDIUM | P2 |
| Confidence review queue | LOW | LOW | P3 |
| ZIP upload | LOW | MEDIUM | P3 |

**Priority key:**
- P1: Must have for v1.1 launch
- P2: Should have, add when possible
- P3: Nice to have, future consideration

## Competitor Feature Analysis

| Feature | Manual Entry | Generic OCR (Tesseract) | This Project |
|---------|--------------|------------------------|--------------|
| Thai numeral handling | Manual | Poor | Excellent (Thai + Arabic) |
| Form type detection | Manual | None | Automatic (6 types) |
| ECT validation | Manual | None | Automatic (3,491 candidates) |
| Batch processing | Very slow | Sequential | Parallel |
| Progress feedback | None | None | Real-time |
| Executive summary | Manual | None | Automatic PDF |

## Implementation Notes

### Parallel OCR Strategy

Based on research into Python concurrency best practices for I/O-bound API calls:

```python
# Recommended approach using ThreadPoolExecutor (I/O-bound) with rate limiting
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import time

class BatchProcessor:
    def __init__(self, max_workers=5, rate_limit_per_second=2):
        self.max_workers = max_workers
        self.rate_limit = rate_limit_per_second
        self.progress = 0
        self.total = 0
        self.lock = threading.Lock()
        self.last_request_time = 0

    def _rate_limited_process(self, image_path: str) -> BallotData:
        """Process one ballot with rate limiting."""
        with self.lock:
            now = time.time()
            elapsed = now - self.last_request_time
            min_interval = 1.0 / self.rate_limit
            if elapsed < min_interval:
                time.sleep(min_interval - elapsed)
            self.last_request_time = time.time()

        return extract_ballot_data_with_ai(image_path)

    def process_batch(self, image_paths: list[str]) -> list[BallotData]:
        self.total = len(image_paths)
        self.progress = 0
        results = []

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(self._rate_limited_process, path): path
                       for path in image_paths}
            for future in as_completed(futures):
                try:
                    result = future.result(timeout=60)
                    results.append(result)
                except Exception as e:
                    print(f"Failed: {futures[future]} - {e}")
                finally:
                    with self.lock:
                        self.progress += 1

        return results
```

Key considerations:
- **Use ThreadPoolExecutor, not ProcessPoolExecutor:** API calls are I/O-bound; threads work well under GIL
- **Rate limiting:** OpenRouter/Gemini have rate limits; use 2 requests/second as safe default
- **Error isolation:** One failed OCR should not crash entire batch; use timeout per ballot
- **Memory:** Images are small; memory not a concern for 500 ballots

### Web UI Framework Comparison

| Criterion | Gradio | FastAPI |
|-----------|--------|---------|
| Setup time | 5 minutes | 30 minutes |
| Learning curve | Easy | Moderate |
| Async support | Limited | Native |
| File upload | Built-in | Built-in |
| Progress tracking | `gr.Progress()` | SSE or WebSocket |
| API documentation | None | Auto-generated (OpenAPI) |
| Production ready | Yes (with queue) | Yes |
| Best for | ML demos, quick MVPs | Production APIs |

**Recommendation:** Start with **Gradio** for fastest MVP. Consider FastAPI for v1.2 if production API needed.

### Gradio Web UI Pattern

```python
import gradio as gr
from concurrent.futures import ThreadPoolExecutor

def process_ballots(files, progress=gr.Progress()):
    """Process uploaded ballot images with progress tracking."""
    results = []
    processor = BatchProcessor(max_workers=5, rate_limit_per_second=2)

    image_paths = [f.name for f in files]

    for i, result in enumerate(progress.tqdm(
        processor.process_batch_iterator(image_paths),
        total=len(image_paths),
        desc="Processing ballots"
    )):
        results.append(result)

    # Generate PDFs
    pdf_path = generate_executive_summary_pdf(results, [], "output.pdf")

    return format_results(results), pdf_path

with gr.Blocks(title="Thai Election Ballot OCR") as demo:
    gr.Markdown("# Thai Election Ballot OCR")
    gr.Markdown("Upload ballot images to extract and validate vote counts")

    with gr.Row():
        file_input = gr.File(file_count="multiple", label="Upload Ballot Images", file_types=[".png", ".jpg", ".pdf"])

    with gr.Row():
        process_btn = gr.Button("Process Ballots", variant="primary")

    with gr.Row():
        with gr.Column():
            results_output = gr.Dataframe(label="Extracted Results", headers=["Province", "Constituency", "Station", "Confidence", "Status"])
        with gr.Column():
            stats_output = gr.JSON(label="Summary Statistics")

    with gr.Row():
        pdf_output = gr.File(label="Download Executive Summary PDF")
        json_output = gr.File(label="Download JSON Results")

    process_btn.click(
        process_ballots,
        inputs=[file_input],
        outputs=[results_output, stats_output, pdf_output, json_output]
    )

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860)
```

### FastAPI Alternative (for production)

```python
from fastapi import FastAPI, UploadFile, File, BackgroundTasks
from fastapi.responses import FileResponse
import uuid

app = FastAPI(title="Thai Election Ballot OCR API")

# In-memory batch storage (use Redis/DB for production)
batches = {}

@app.post("/api/upload")
async def upload_ballots(files: list[UploadFile] = File(...)):
    """Upload ballot images and start batch processing."""
    batch_id = str(uuid.uuid4())

    # Save files
    image_paths = []
    for file in files:
        path = f"/tmp/{batch_id}_{file.filename}"
        with open(path, "wb") as f:
            f.write(await file.read())
        image_paths.append(path)

    # Start background processing
    batches[batch_id] = {"status": "processing", "progress": 0, "total": len(image_paths), "results": []}
    # background_tasks.add_task(process_batch, batch_id, image_paths)

    return {"batch_id": batch_id, "total_files": len(files)}

@app.get("/api/batch/{batch_id}")
async def get_batch_status(batch_id: str):
    """Get batch processing status and results."""
    return batches.get(batch_id, {"error": "Batch not found"})

@app.get("/api/batch/{batch_id}/pdf")
async def download_pdf(batch_id: str):
    """Download executive summary PDF."""
    pdf_path = f"/tmp/{batch_id}_summary.pdf"
    return FileResponse(pdf_path, media_type="application/pdf", filename="executive_summary.pdf")
```

### Path-Based Metadata Inference

Pattern for Thai election ballot filenames:

```
{province_thai}_{constituency_no}_{polling_station}_{seq}.png

Examples:
- กรุงเทพมหานคร_4_001_001.png  (Bangkok, Constituency 4, Station 001, Seq 001)
- เชียงใหม่_2_015_003.png        (Chiang Mai, Constituency 2, Station 015, Seq 003)

Google Drive folder pattern:
/Province/Constituency#/Station#/images...
```

Implementation:

```python
import re
from pathlib import Path

def infer_metadata_from_path(filepath: str) -> dict:
    """Extract province, constituency, station from filename or folder path."""
    filepath = Path(filepath)

    # Try filename pattern first
    filename = filepath.stem
    pattern = r"^(.+?)_(\d+)_(\d+)_(\d+)$"
    match = re.match(pattern, filename)

    if match:
        return {
            "province": match.group(1),
            "constituency_number": int(match.group(2)),
            "polling_station": match.group(3),
            "sequence": int(match.group(4)),
            "source": "filename"
        }

    # Try folder path pattern: /Province/Constituency#/Station#/...
    parts = filepath.parts
    if len(parts) >= 4:
        province = parts[-4] if len(parts) > 3 else None
        constituency = re.search(r'(\d+)', parts[-3]) if len(parts) > 2 else None
        station = re.search(r'(\d+)', parts[-2]) if len(parts) > 1 else None

        if province and constituency:
            return {
                "province": province,
                "constituency_number": int(constituency.group(1)),
                "polling_station": station.group(1) if station else None,
                "source": "folder"
            }

    return {"source": "ocr_required"}
```

### Zone-Based Numeral Extraction (v1.2)

For forms with consistent layouts (the 6 Thai ballot types), define coordinate zones:

```python
# Template coordinates for each form type (percentage-based for scaling)
FORM_ZONES = {
    FormType.S5_18: {
        "province": (0.05, 0.10, 0.30, 0.15),      # x1%, y1%, x2%, y2%
        "constituency": (0.35, 0.10, 0.50, 0.15),
        "vote_counts": [
            (0.70, 0.25, 0.85, 0.30),  # Candidate 1
            (0.70, 0.32, 0.85, 0.37),  # Candidate 2
            # ... more positions
        ],
    },
    # ... other form types
}
```

This approach:
1. Crops image to numeric regions before OCR
2. Reduces noise from text, signatures, stamps
3. Improves number recognition accuracy
4. Faster processing (smaller regions)

### Numeral OCR Accuracy Optimization

The existing implementation already follows best practices:

| Technique | Status | Impact |
|-----------|--------|--------|
| Thai numeral conversion (๐๑๒๓๔๕๖๗๘๙ -> 0123456789) | Implemented | HIGH - handles both scripts |
| Position-based extraction (not name-based) | Implemented | HIGH - avoids AI hallucination |
| Numeric vs Thai text validation | Implemented | HIGH - catches OCR errors |
| Sum validation (individual votes = total) | Implemented | MEDIUM - catches major errors |
| ECT cross-reference | Implemented | HIGH - validates against official data |

### Executive Summary PDF Enhancement

The existing `generate_executive_summary_pdf()` function (lines 2557-2784 in ballot_ocr.py) includes:
- Key statistics table (total votes, confidence, anomalies)
- Data quality assessment (EXCELLENT/GOOD/ACCEPTABLE/POOR)
- Province summary table
- Top candidates table
- Issues and recommendations section

**Minor enhancements for v1.1:**

| Enhancement | Complexity | Value |
|-------------|------------|-------|
| Add bar chart for top 5 parties | LOW | HIGH |
| Add pie chart for vote distribution | LOW | MEDIUM |
| Add confidence histogram | MEDIUM | MEDIUM |
| Add anomaly heatmap by province | HIGH | MEDIUM |

**Recommendation:** Keep executive summary simple. Add party vote bar chart using existing reportlab chart support (already in imports).

## Sources

### Web UI Frameworks
- [Gradio Quickstart Guide](https://www.gradio.app/guides/quickstart) - Official documentation for web UI
- [Gradio Progress Bars](https://www.gradio.app/guides/progress-bars) - Progress tracking implementation
- [Gradio Batch Functions](https://www.gradio.app/guides/batch-functions) - Batch processing patterns
- [FastAPI File Uploads Guide](https://davidmuraya.com/blog/fastapi-file-uploads/) - Modern Python web file handling
- [FastAPI vs Flask 2025](https://medium.com/@2nick2patel2/fastapi-vs-flask-vs-django-the-2025-ai-playbook-9f55f2a846f5) - Framework comparison for AI apps

### Parallel Processing
- [Python Multiprocessing Documentation](https://docs.python.org/3/library/multiprocessing.html) - Official Python docs
- [Python Concurrency ThreadPoolExecutor vs AsyncIO](https://medium.com/towardsdev/whats-the-best-way-to-handle-concurrency-in-python-threadpoolexecutor-or-asyncio-85da1be58557) - Thread vs async comparison
- [Controlling Concurrency in Python](https://dev.to/ctrix/controlling-concurrency-in-python-semaphores-and-pool-workers-56d7) - Semaphores and rate limiting
- [tqdm with Multiprocessing](https://leimao.github.io/blog/Python-tqdm-Multiprocessing/) - Progress bars for parallel processing

### OCR Best Practices
- [ThaiOCRBench - Vision-Language Models for Thai](https://opentyphoon.ai/blog/en/thaiocrbench) - Thai OCR benchmark including numerals
- [Typhoon OCR Paper (arXiv)](https://arxiv.org/html/2601.14722v1) - State-of-art Thai document OCR
- [Batch OCR Processing Guide](https://dev.to/revisepdf/batch-ocr-processing-for-large-document-collections-4h30) - Parallel processing strategies
- [Zonal OCR Explained](https://nanonets.com/blog/zonal-ocr/) - Zone-based extraction techniques
- [State of Document Processing in Python 2025](https://hyperceptron.substack.com/p/state-of-document-processing-in-python) - OCR best practices

### PDF Generation
- [Executive Summary Best Practices (OpenStax 2025)](https://openstax.org/books/principles-data-science/pages/10-3-effective-executive-summaries) - Data science reporting
- [PDF Report Generation with Python](https://medium.com/@AlexanderObregon/creating-pdf-reports-with-python-a53439031117) - ReportLab patterns
- [Building Production PDF Templates](https://python.plainenglish.io/the-secret-weapon-for-pdfs-building-production-templates-without-touching-css-76eed8d1e17f) - Template-based generation

---
*Feature research for: Thai Election Ballot OCR v1.1*
*Researched: 2026-02-16*
