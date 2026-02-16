# Architecture Research

**Domain:** Thai Ballot OCR System - Parallel Processing, Web Interface, Executive Summary
**Researched:** 2026-02-16
**Confidence:** HIGH (based on existing codebase analysis and established Python patterns)

## Current Architecture

### Existing System Overview

```
+------------------------------------------------------------------+
|                        CLI Entry Point                            |
|                     (ballot_ocr.py:main)                          |
+------------------------------------------------------------------+
                              |
                              v
+------------------------------------------------------------------+
|                    Processing Pipeline                            |
|  +--------------+  +----------------+  +------------------+      |
|  | PDF/Image    |->| Form Detection |->| AI Vision OCR    |      |
|  | Conversion   |  | (6 form types) |  | (OpenRouter/     |      |
|  | (pdftoppm)   |  |                |  |  Claude fallback)|      |
|  +--------------+  +----------------+  +------------------+      |
+------------------------------------------------------------------+
                              |
                              v
+------------------------------------------------------------------+
|                     Data Layer                                    |
|  +--------------+  +----------------+  +------------------+      |
|  | BallotData   |  | ECT API        |  | Aggregated       |      |
|  | (dataclass)  |  | (ect_api.py)   |  | Results          |      |
|  +--------------+  +----------------+  +------------------+      |
+------------------------------------------------------------------+
                              |
                              v
+------------------------------------------------------------------+
|                     Output Layer                                  |
|  +--------------+  +----------------+  +------------------+      |
|  | JSON Export  |  | Markdown       |  | PDF Reports      |      |
|  |              |  | Reports        |  | (reportlab)      |      |
|  +--------------+  +----------------+  +------------------+      |
+------------------------------------------------------------------+
```

### Current Component Responsibilities

| Component | File | Responsibility | Lines |
|-----------|------|----------------|-------|
| Main Entry | ballot_ocr.py | CLI parsing, orchestration, sequential processing | ~4208 |
| OCR Engine | ballot_ocr.py | AI vision extraction, Thai numeral conversion | ~1200 |
| Form Detection | ballot_ocr.py | Form type classification (S5_16, S5_17, S5_18 + party list) | ~300 |
| Data Models | ballot_ocr.py | BallotData, AggregatedResults, VoteEntry dataclasses | ~100 |
| ECT Integration | ect_api.py | Official election data, candidate matching | ~440 |
| PDF Generation | ballot_ocr.py | reportlab-based reports, charts, executive summary | ~900 |
| Aggregation | ballot_ocr.py | Constituency-level vote aggregation | ~200 |
| Drive Auth | drive_auth.py | Google Drive OAuth, file listing | ~81 |

### Current Processing Flow

```
1. Input (file/directory) -> 2. Sequential processing (one ballot at a time)
                           -> 3. Individual ballot results
                           -> 4. Aggregation by constituency
                           -> 5. Report/PDF generation
```

**Problem:** Sequential processing blocks on each API call (2-5 seconds per ballot), making 100-500 ballots impractical (8-40 minutes for 500 ballots vs ~3-5 minutes with parallel processing).

---

## Proposed Architecture (v1.1)

### System Overview

```
+------------------------------------------------------------------+
|                        Web Layer                                  |
|  +---------------------------+  +-----------------------------+   |
|  | FastAPI Server            |  | Static Files (minimal UI)   |   |
|  | (main.py)                 |  | (HTML upload form, results) |   |
|  +---------------------------+  +-----------------------------+   |
+------------------------------------------------------------------+
         |                      |                      |
         v                      v                      v
+------------------------------------------------------------------+
|                     API Layer                                     |
|  +-------------+  +----------------+  +--------------------+      |
|  | POST /batch |  | GET /jobs/{id} |  | GET /jobs/{id}/    |      |
|  | (upload)    |  | (status)       |  |  results           |      |
|  +-------------+  +----------------+  +--------------------+      |
|  +---------------------------+  +----------------------------+    |
|  | GET /jobs/{id}/stream     |  | GET /download/{job}/pdf   |    |
|  | (SSE progress)            |  | (executive summary)       |    |
|  +---------------------------+  +----------------------------+    |
+------------------------------------------------------------------+
                              |
                              v
+------------------------------------------------------------------+
|                   Processing Layer                                |
|  +-------------------+  +-----------------+  +----------------+   |
|  | Path Metadata     |  | Parallel OCR    |  | Progress       |   |
|  | Extractor         |  | Orchestrator    |  | Tracker        |   |
|  | (NEW)             |  | (NEW)           |  | (NEW)          |   |
|  +-------------------+  +-----------------+  +----------------+   |
+------------------------------------------------------------------+
                              |
                              v
+------------------------------------------------------------------+
|                     Core Layer (EXISTING)                         |
|  +----------------+  +----------------+  +------------------+     |
|  | ballot_ocr.py  |  | ect_api.py     |  | PDF Generation   |     |
|  | (refactored)   |  | (unchanged)    |  | (enhanced)       |     |
|  +----------------+  +----------------+  +------------------+     |
+------------------------------------------------------------------+
```

### Component Responsibilities

| Component | File | Responsibility | New/Modified |
|-----------|------|----------------|--------------|
| FastAPI Server | server/main.py | HTTP endpoints, file uploads, SSE | NEW |
| Job Manager | server/jobs.py | Job state, persistence, cleanup | NEW |
| Path Metadata | server/path_parser.py | Extract province/constituency from paths | NEW |
| Parallel OCR | server/parallel_ocr.py | Concurrent processing with ProcessPool | NEW |
| Progress Tracker | server/progress.py | Real-time progress, SSE events | NEW |
| Ballot Core | ballot_ocr.py | Single-ballot OCR (extracted functions) | MODIFIED |
| ECT Data | ect_api.py | Official election data (unchanged) | UNCHANGED |
| PDF Reports | ballot_ocr.py | Executive summary already implemented | UNCHANGED |

---

## Recommended Project Structure

```
election/
+-- ballot_ocr.py           # Core OCR engine (refactored to expose functions)
+-- ect_api.py              # ECT API client (unchanged)
+-- drive_auth.py           # Google Drive auth (unchanged)
+-- server/                 # NEW: Web interface layer
|   +-- __init__.py
|   +-- main.py             # FastAPI app, routes
|   +-- jobs.py             # Job management, state
|   +-- parallel_ocr.py     # ProcessPool-based parallel processing
|   +-- path_parser.py      # Path-based metadata extraction
|   +-- progress.py         # SSE progress tracking
|   +-- zones.py            # Zone-based extraction (optional optimization)
|   +-- static/
|   |   +-- index.html      # Minimal upload UI
|   |   +-- style.css       # Basic styling
|   |   +-- app.js          # Fetch API, SSE client
|   +-- templates/          # Jinja2 templates (optional)
+-- reports/                # Output directory (existing)
+-- tests/                  # Test files (existing)
+-- requirements.txt        # Add: fastapi, uvicorn, python-multipart
```

### Structure Rationale

- **server/**: Isolates all web-related code from core OCR logic
- **parallel_ocr.py**: Uses ProcessPoolExecutor (not just asyncio) for true parallelism
- **path_parser.py**: Single responsibility for metadata inference from paths
- **progress.py**: Isolated SSE logic for easy testing
- **zones.py**: Optional zone-based extraction for faster/cheaper OCR
- **Minimal static/**: No build step, vanilla HTML/CSS/JS

---

## Architectural Patterns

### Pattern 1: ProcessPoolExecutor for True Parallelism (CRITICAL)

**What:** Use `concurrent.futures.ProcessPoolExecutor` for CPU-bound OCR processing, NOT just asyncio.

**When:** OCR involves both CPU-intensive image processing AND blocking API calls. The Python GIL prevents true parallelism with threads/asyncio alone.

**Trade-offs:**
- Pros: True parallelism, bypasses GIL, each worker has its own Python interpreter
- Cons: Process spawn overhead, data must be pickle-serializable (all our data is JSON-compatible)

**Why NOT just asyncio:** Asyncio is for I/O-bound tasks. OCR processing has CPU-bound components (image encoding, base64 conversion, JSON parsing). With asyncio alone, these block the event loop.

```python
# server/parallel_ocr.py
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Callable
import asyncio

class ParallelOCRProcessor:
    """
    ProcessPool-based parallel OCR processing.

    IMPORTANT: Use ProcessPoolExecutor, NOT asyncio.gather() for CPU-bound work.
    - asyncio.gather() provides concurrency but NOT parallelism due to GIL
    - ProcessPoolExecutor provides true parallelism by using separate processes
    """

    def __init__(self, max_workers: int = 4):
        # 4 workers is optimal for most cases (diminishing returns beyond 4)
        self.max_workers = max_workers
        self.progress_callback: Callable[[int, int, str], None] = None

    def process_batch(
        self,
        images: list[str],
        metadata_extractor: 'PathMetadataParser',
    ) -> tuple[list, list]:
        """
        Process images with true parallelism using ProcessPool.

        Returns:
            tuple of (results, errors)
        """
        results = []
        errors = []
        total = len(images)

        # Use ProcessPoolExecutor for CPU-bound OCR work
        with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all jobs
            future_to_path = {
                executor.submit(
                    self._process_single,
                    path,
                    metadata_extractor.extract(path)
                ): path
                for path in images
            }

            # Collect results as they complete
            for i, future in enumerate(as_completed(future_to_path)):
                path = future_to_path[future]
                try:
                    result = future.result(timeout=60)  # 60s per ballot
                    results.append(result)
                except Exception as e:
                    errors.append({'path': path, 'error': str(e)})

                # Update progress
                if self.progress_callback:
                    self.progress_callback(i + 1, total, path)

        return results, errors

    @staticmethod
    def _process_single(path: str, metadata: dict) -> 'BallotData':
        """Static method for pickling - runs in separate process."""
        # Import inside function to avoid pickling issues
        from ballot_ocr import extract_ballot_data_with_ai

        ballot = extract_ballot_data_with_ai(path)

        # Merge path metadata with OCR results
        if ballot and metadata.get('province'):
            ballot.province = ballot.province or metadata['province']
            ballot.constituency_number = (
                ballot.constituency_number or metadata.get('constituency_no', 0)
            )

        return ballot
```

### Pattern 2: Path-Based Metadata Inference

**What:** Extract province, constituency, polling unit from file path BEFORE OCR to reduce complexity.

**When:** Google Drive folder structures often encode this information.

**Trade-offs:**
- Pros: Reduces OCR scope to just numbers, faster, more accurate
- Cons: Requires consistent folder naming convention, fallback needed

**Example:**
```python
# server/path_parser.py
import re
from pathlib import Path

class PathMetadataParser:
    """
    Extract metadata from Google Drive folder/file paths.

    Google Drive URL patterns:
    - https://drive.google.com/drive/folders/{folder_id}
    - Folder names often encode: Province/Constituency/Unit
    """

    PROVINCE_PATTERNS = [
        r"จังหวัด([^\s/]+)",           # "จังหวัดแพร่"
        r"^([^\s/]+)/(?:เขต|District)", # "แพร่/เขต..."
    ]

    CONSTITUENCY_PATTERNS = [
        r"เขตเลือกตั้งที่\s*(\d+)",     # "เขตเลือกตั้งที่ 1"
        r"เขต\s*(\d+)",                # "เขต 1"
        r"District\s*(\d+)",           # "District 1"
    ]

    POLLING_UNIT_PATTERNS = [
        r"หน่วยเลือกตั้งที่\s*(\d+)",   # "หน่วยเลือกตั้งที่ 5"
        r"หน่วย\s*(\d+)",              # "หน่วย 5"
        r"Unit\s*(\d+)",               # "Unit 5"
    ]

    def __init__(self, ect_data: 'ECTData' = None):
        """Initialize with optional ECT data for province validation."""
        self.ect_data = ect_data

    def extract(self, path: str) -> dict:
        """Extract metadata from path, return defaults if not found."""
        return {
            'province': self._extract_province(path),
            'constituency_no': self._extract_constituency(path),
            'polling_unit': self._extract_polling_unit(path),
            'confidence': self._calculate_confidence(path),
            'source': 'path_inference',
        }

    def _extract_province(self, path: str) -> str | None:
        for pattern in self.PROVINCE_PATTERNS:
            match = re.search(pattern, path)
            if match:
                province = match.group(1)
                # Validate against ECT data if available
                if self.ect_data:
                    valid, canonical = self.ect_data.validate_province_name(province)
                    if valid:
                        return canonical
                return province
        return None

    def _extract_constituency(self, path: str) -> int | None:
        for pattern in self.CONSTITUENCY_PATTERNS:
            match = re.search(pattern, path)
            if match:
                return int(match.group(1))
        return None

    def _extract_polling_unit(self, path: str) -> int | None:
        for pattern in self.POLLING_UNIT_PATTERNS:
            match = re.search(pattern, path)
            if match:
                return int(match.group(1))
        return None

    def _calculate_confidence(self, path: str) -> float:
        """Calculate confidence score based on how much metadata was extracted."""
        score = 0.0
        if self._extract_province(path):
            score += 0.4
        if self._extract_constituency(path):
            score += 0.3
        if self._extract_polling_unit(path):
            score += 0.3
        return score
```

### Pattern 3: Server-Sent Events for Progress

**What:** Use SSE to stream progress updates to client without polling.

**When:** Long-running batch jobs with progress tracking.

**Trade-offs:**
- Pros: Simple, native browser support, works over HTTP/2
- Cons: Unidirectional (server to client only), requires connection management

**Example:**
```python
# server/progress.py
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
import asyncio
import json

router = APIRouter()

# In-memory job progress (use Redis for production)
job_progress: dict[str, dict] = {}

@router.get("/jobs/{job_id}/stream")
async def stream_progress(job_id: str):
    """SSE endpoint for real-time progress updates."""

    async def event_generator():
        while True:
            progress = job_progress.get(job_id, {})

            # Send event
            data = json.dumps(progress)
            yield f"data: {data}\n\n"

            # Check completion
            if progress.get("status") in ("completed", "failed"):
                break

            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
    )

def update_progress(job_id: str, current: int, total: int, message: str):
    """Called by parallel processor to update progress."""
    job_progress[job_id] = {
        "current": current,
        "total": total,
        "percent": round(current / total * 100, 1) if total > 0 else 0,
        "message": message,
        "status": "processing" if current < total else "completed",
    }
```

### Pattern 4: UploadFile + BackgroundTasks Safety

**What:** Properly handle UploadFile in background tasks (known FastAPI gotcha).

**When:** File uploads with background processing.

**Trade-offs:**
- Pros: Prevents "file closed" errors
- Cons: Requires explicit file content save before background task

**Example:**
```python
# server/routes/upload.py
from fastapi import UploadFile, BackgroundTasks, APIRouter
import shutil
import uuid
import os

router = APIRouter()

@router.post("/batch")
async def upload_batch(
    files: list[UploadFile],
    background_tasks: BackgroundTasks,
):
    """
    Upload multiple ballot images for batch processing.

    CRITICAL: Save files BEFORE background task.
    UploadFile.file is a SpooledTemporaryFile that closes after response.
    """
    job_id = str(uuid.uuid4())[:8]

    # Save files BEFORE background task
    saved_paths = []
    upload_dir = f"uploads/{job_id}"
    os.makedirs(upload_dir, exist_ok=True)

    for file in files:
        dest = f"{upload_dir}/{file.filename}"
        with open(dest, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        saved_paths.append(dest)

    # Initialize job state
    from server.progress import job_progress
    job_progress[job_id] = {
        "status": "queued",
        "total": len(saved_paths),
        "current": 0,
    }

    # Schedule background processing
    background_tasks.add_task(
        process_batch_job,
        job_id,
        saved_paths,
    )

    return {"job_id": job_id, "files": len(saved_paths)}
```

### Pattern 5: Zone-Based Extraction (Optional Optimization)

**What:** Extract only specific regions of ballot images rather than full-document OCR.

**When:** Consistent form layouts (6 variants known), reduces API costs and improves accuracy.

**Trade-offs:**
- Pros: Faster, cheaper, more accurate (focus on number regions)
- Cons: Requires form type detection first, zone coordinates must be accurate

```python
# server/zones.py
from dataclasses import dataclass
from PIL import Image

@dataclass
class Zone:
    """Rectangular region on ballot form."""
    name: str
    bbox: tuple[int, int, int, int]  # x, y, width, height
    content_type: str  # 'number', 'thai_text', 'province'

# Zone definitions for ส.ส. 5/18 constituency form
# These coordinates are approximate - need calibration with real forms
ZONES_S5_18_CONSTITUENCY = {
    'form_code': Zone('form_code', (720, 20, 100, 40), 'text'),
    'province': Zone('province', (50, 80, 200, 30), 'thai_text'),
    'constituency': Zone('constituency', (50, 120, 150, 30), 'thai_text'),
    'vote_table': Zone('vote_table', (30, 200, 760, 500), 'table'),
    'totals': Zone('totals', (30, 720, 760, 80), 'table'),
}

ZONES_S5_18_PARTY_LIST = {
    'form_code': Zone('form_code', (720, 20, 100, 40), 'text'),
    'province': Zone('province', (50, 80, 200, 30), 'thai_text'),
    'party_table': Zone('party_table', (30, 150, 760, 600), 'table'),
    'totals': Zone('totals', (30, 780, 760, 80), 'table'),
}

def extract_zones(image_path: str, zones: dict[str, Zone]) -> dict:
    """Extract specific zones from ballot image."""
    img = Image.open(image_path)
    results = {}

    for zone_name, zone in zones.items():
        x, y, w, h = zone.bbox
        cropped = img.crop((x, y, x + w, y + h))
        # Could save cropped regions for zone-specific OCR
        # or encode directly to base64
        results[zone_name] = cropped

    return results
```

---

## Data Flow

### Request Flow (Batch Upload)

```
[User uploads files]
       |
       v
+-----------------+     +-------------------+
| POST /batch     | --> | Save files to     |
| (FastAPI)       |     | uploads/{job_id}/ |
+-----------------+     +-------------------+
       |                        |
       v                        v
+-----------------+     +-------------------+
| Return job_id   |     | Background task:  |
| immediately     |     | process_batch_job |
+-----------------+     +-------------------+
                               |
                               v
               +-------------------------------+
               | ParallelOCRProcessor.process()|
               | (ProcessPool with 4 workers)  |
               +-------------------------------+
                               |
                               v
               +-------------------------------+
               | For each image (in parallel): |
               | 1. Path metadata extraction   |
               | 2. AI Vision OCR (numbers)    |
               | 3. ECT validation             |
               | 4. Update progress (SSE)      |
               +-------------------------------+
                               |
                               v
               +-------------------------------+
               | Aggregate by constituency     |
               | Generate Executive Summary PDF|
               +-------------------------------+
```

### State Management

```
+------------------+     +-------------------+
| In-Memory Dict   | <-> | SSE Connected     |
| job_progress{}   |     | Clients           |
+------------------+     +-------------------+
        |
        v
+------------------+
| On completion:   |
| - Save to JSON   |
| - Generate PDF   |
| - Cleanup uploads|
+------------------+
```

### Key Data Flows

1. **Upload Flow:** Files -> save to disk -> return job_id immediately -> process in background
2. **Progress Flow:** Processor updates job_progress -> SSE streams to connected clients
3. **Result Flow:** Completed ballots -> aggregate by constituency -> generate PDF -> available for download

---

## Integration Points

### Existing Components to Modify

| Component | Changes Required |
|-----------|-----------------|
| ballot_ocr.py | Extract `extract_ballot_data_with_ai()` as importable function, add optional pre-filled metadata parameter |
| ect_api.py | No changes needed |
| generate_executive_summary_pdf() | Already implemented, just needs to be called from API |

### New Components

| Component | Dependencies | Integration |
|-----------|-------------|-------------|
| FastAPI server | fastapi, uvicorn, python-multipart | Calls ballot_ocr functions |
| Parallel processor | concurrent.futures | Wraps ballot_ocr.extract_ballot_data_with_ai |
| Path parser | re, pathlib | Pre-processes before OCR |
| SSE progress | FastAPI StreamingResponse | Receives updates from processor |
| Job manager | uuid, dataclasses | Stores state for API |

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Using Asyncio for CPU-Bound OCR (CRITICAL)

**What people do:** Use `asyncio.gather()` for parallel OCR processing.

**Why it's wrong:** OCR involves CPU-bound work (image encoding, JSON parsing). Asyncio provides concurrency but NOT parallelism due to Python's GIL. All tasks will still block each other.

**Do this instead:** Use `ProcessPoolExecutor` for true parallelism.

```python
# WRONG - No true parallelism, tasks block each other
results = await asyncio.gather(*[
    extract_ballot_async(path) for path in paths
])

# CORRECT - True parallelism with separate processes
with ProcessPoolExecutor(max_workers=4) as executor:
    results = list(executor.map(extract_ballot, paths))
```

### Anti-Pattern 2: Blocking the Event Loop

**What people do:** Call synchronous OCR functions directly in async handlers.

**Why it's wrong:** Blocks the entire event loop, no concurrent processing.

**Do this instead:** Use `loop.run_in_executor()` for blocking calls.

```python
# WRONG
async def process():
    result = extract_ballot_data_with_ai(path)  # Blocks!

# CORRECT
async def process():
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        extract_ballot_data_with_ai,
        path,
    )
```

### Anti-Pattern 3: UploadFile in Background Tasks

**What people do:** Pass `UploadFile` directly to background task.

**Why it's wrong:** File is closed after response, background task sees empty file.

**Do this instead:** Save file content to disk first, pass file path.

```python
# WRONG
async def upload(file: UploadFile, bg: BackgroundTasks):
    bg.add_task(process, file)  # File closed before task runs!

# CORRECT
async def upload(file: UploadFile, bg: BackgroundTasks):
    path = f"/tmp/{file.filename}"
    with open(path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    bg.add_task(process, path)  # Pass path, not file object
```

### Anti-Pattern 4: In-Memory State Without Persistence

**What people do:** Store all job state in memory.

**Why it's wrong:** Lost on restart, no recovery.

**Do this instead:** Write job state to JSON file, check on startup for recovery.

```python
# Add simple file-based persistence
JOBS_FILE = "data/jobs.json"

def save_job_state(job_id: str, state: dict):
    jobs = json.load(open(JOBS_FILE)) if os.path.exists(JOBS_FILE) else {}
    jobs[job_id] = state
    json.dump(jobs, open(JOBS_FILE, "w"))

def load_job_state(job_id: str) -> dict | None:
    if os.path.exists(JOBS_FILE):
        return json.load(open(JOBS_FILE)).get(job_id)
    return None
```

---

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| 1-100 ballots | Current proposed architecture is sufficient |
| 100-500 ballots | Increase ProcessPool workers (4 -> 8), add request timeout |
| 500+ ballots | Consider ARQ + Redis for persistent queue, or split into batches |
| 5000+ ballots | Consider Celery + RabbitMQ, horizontal worker scaling |

### Task Queue Comparison (for future scaling)

| Tool | Best For | When to Use |
|------|----------|-------------|
| FastAPI BackgroundTasks | Simple post-response tasks | < 100 ballots, lightweight |
| ARQ + Redis | Async-native apps, moderate scale | 100-1000 ballots |
| Celery + Redis/RabbitMQ | Enterprise-scale, heavy processing | 1000+ ballots, distributed |

### Scaling Priorities

1. **First bottleneck:** API rate limits (OpenRouter/Claude) - implement retry with exponential backoff
2. **Second bottleneck:** Memory with many concurrent uploads - add file cleanup after processing
3. **Third bottleneck:** Redis connection pool (if using ARQ) - use connection pooling

---

## Build Order Recommendation

Based on dependencies, recommended implementation order:

### Phase 1: Core Refactoring (No new features)
1. Extract importable functions from `ballot_ocr.py`:
   - `extract_ballot_data_with_ai(image_path, form_type=None) -> BallotData`
   - `aggregate_ballot_results(ballot_data_list) -> dict`
   - `generate_executive_summary_pdf(..., output_path) -> bool`
2. Verify CLI still works with refactored code

**Why first:** Enables parallel work on web layer, makes testing easier.

### Phase 2: Path Parser (standalone, no dependencies)
- Create `server/path_parser.py`
- Unit tests for path extraction
- Validate against sample Google Drive paths

**Why second:** Standalone, can be developed independently.

### Phase 3: Parallel Processor (connects to existing OCR)
- Create `server/parallel_ocr.py` with ProcessPoolExecutor
- Add `config.py` for worker count, timeouts
- Test with 50-ballot batch via CLI

**Why third:** Adds value without web dependency, validates parallel approach.

### Phase 4: FastAPI Skeleton + SSE
- Create `server/main.py` with basic routes
- Add SSE endpoint for streaming progress
- Create simple HTML client to test SSE

**Why fourth:** Depends on progress tracking, provides testing interface.

### Phase 5: Full Web Interface
- Add file upload endpoint
- Create upload/progress/results templates
- Wire up complete flow: upload -> process -> view results

**Why fifth:** Depends on all previous phases, provides user-facing value.

### Phase 6: Executive Summary Integration
- Wire API endpoint to existing `generate_executive_summary_pdf()`
- Add download route

**Why last:** Independent of web, completes v1.0 PDF feature set.

---

## Sources

- [FastAPI Background Tasks vs Celery vs ARQ](https://medium.com/@komalbaparmar007/fastapi-background-tasks-vs-celery-vs-arq-picking-the-right-asynchronous-workhorse-b6e0478ecf4a) (Nov 2025) - MEDIUM confidence
- [Managing Background Tasks: BackgroundTasks vs ARQ](https://davidmuraya.com/blog/fastapi-background-tasks-arq-vs-built-in/) (Aug 2025) - MEDIUM confidence
- [Build LLM Web App: FastAPI Background Tasks + SSE](https://dev.to/zachary62/build-an-llm-web-app-in-python-from-scratch-part-4-fastapi-background-tasks-sse-21g4) (Jun 2025) - HIGH confidence (code examples)
- [Real-Time Celery Progress Bars with FastAPI](https://celery.school/celery-progress-bars-with-fastapi-htmx) (Feb 2025) - MEDIUM confidence
- [Using HTMX with FastAPI](https://testdriven.io/blog/fastapi-htmx/) (Jul 2024) - HIGH confidence (established tutorial)
- [Python Parallel Processing - Real Python](https://realpython.com/python-parallel-processing/) - HIGH confidence
- [ProcessPoolExecutor vs multiprocessing.Pool](https://stackoverflow.com/questions/38311431/concurrent-futures-processpoolexecutor-vs-multiprocessing-pool-pool) - HIGH confidence
- [FastAPI Background Tasks Official Docs](https://fastapi.tiangolo.com/tutorial/background-tasks/) - HIGH confidence
- [UploadFile + BackgroundTasks Issue](https://github.com/fastapi/fastapi/discussions/10936) - HIGH confidence (known gotcha)
- [Google Drive API Python Quickstart](https://developers.google.com/workspace/drive/api/quickstart/python) (Dec 2025) - HIGH confidence (official docs)

---
*Architecture research for: Thai Ballot OCR v1.1*
*Researched: 2026-02-16*
