# Stack Research

**Domain:** Thai Ballot OCR System - Parallel Processing, Web UI, Executive PDF
**Researched:** 2026-02-16
**Confidence:** HIGH (verified with official docs and multiple sources)

## Executive Summary

For the three new capabilities:
1. **Parallel OCR**: Use `asyncio` + `httpx` + `tenacity` - minimal additions to existing stack
2. **Web UI**: Use **Gradio** (10-20 lines) or **FastAPI** (100+ lines) depending on requirements
3. **Executive Summary PDF**: No new libraries - extend existing `reportlab` code

## Recommended Stack

### Core Technologies (NEW Additions)

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| **asyncio** | stdlib | Parallel OCR processing | Built-in Python async runtime. Semaphore for rate limiting OpenRouter (50 req/day free, 20 RPM). Industry standard for I/O-bound API concurrency. |
| **httpx** | 0.28.1 | Async HTTP client | Already installed in project. Supports both sync/async. Cleaner API than aiohttp for mixed workloads. Better exception handling than requests for production. |
| **Gradio** | 5.x | Minimal web UI | Fastest path to file upload + results display. 10-20 lines vs 100+ for FastAPI + frontend. Built-in progress bars, file preview, Thai text support. |
| **tenacity** | 9.x | Retry logic | Exponential backoff for API failures. OpenAI cookbook recommends this pattern for rate-limited LLM APIs. |
| **reportlab** | 4.4.x | Executive Summary PDF | Already installed and used. Charts (bar, pie) via `reportlab.graphics.charts`. Thai font support with custom TTF registration. |

### Existing Stack (Already in Place)

| Technology | Version | Purpose | Notes |
|------------|---------|---------|-------|
| Python | 3.14 | Runtime | Project uses 3.14.2 |
| anthropic | 0.79.0 | Claude Vision API | Fallback OCR when OpenRouter fails |
| requests | 2.32.5 | Sync HTTP (OpenRouter) | Keep for sync use cases |
| reportlab | 4.4.10 | PDF generation | Charts, tables, Thai text |
| Pillow | 12.1.1 | Image processing | Zone extraction with `Image.crop()` |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| **asyncio.Semaphore** | stdlib | Rate limiting | Control concurrent OpenRouter requests. Use `Semaphore(5-10)` to stay under 20 RPM. |
| **tenacity** | 9.x | Retry logic | Exponential backoff for API failures. Recommended for production. |
| **Pillow** | 12.x | Zone extraction | `Image.crop((left, upper, right, lower))` for template-based extraction before OCR. |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| **pytest-asyncio** | Async test support | For testing parallel OCR functions |
| **pytest-cov** | Coverage reporting | Standard coverage tool |

## Installation

```bash
# Core (NEW for parallel OCR + web UI)
pip install httpx==0.28.1  # Already installed
pip install gradio>=5.0
pip install tenacity>=9.0

# Alternative: FastAPI (if needed instead of Gradio)
pip install fastapi>=0.115.0 uvicorn[standard]>=0.40.0 python-multipart>=0.0.20

# Dev dependencies
pip install pytest-asyncio pytest-cov
```

## Web UI Decision: Gradio vs FastAPI

| Factor | Gradio | FastAPI |
|--------|--------|---------|
| **Lines of code** | 10-20 | 100+ |
| **Setup time** | 5 minutes | 30+ minutes |
| **Progress tracking** | Built-in (`gr.Progress()`) | Custom SSE/WebSocket |
| **Thai text support** | Built-in | Manual encoding |
| **Custom styling** | Limited | Full control |
| **Authentication** | Basic | Full control |
| **API exposure** | Auto-generated | Full OpenAPI docs |
| **Best for** | Internal tools, quick prototypes | Production APIs, multi-client |

**Recommendation**: Start with **Gradio** for MVP. Migrate to FastAPI if you need:
- Multiple client types (mobile app, external integrations)
- Custom authentication/authorization
- Complex routing beyond upload/results

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| **httpx** | aiohttp | aiohttp if 100% async-only, higher raw performance (~50% faster). httpx better for mixed sync/async (existing code uses requests). |
| **Gradio** | FastAPI + Jinja2 | If need custom routes, auth, or complex backend. Production multi-tenant systems. |
| **Gradio** | Streamlit | Streamlit if building data dashboard with interactive charts. Gradio simpler for file-in/results-out pattern. |
| **reportlab** | WeasyPrint | WeasyPrint if prefer HTML/CSS templates. reportlab already integrated and has chart support. |
| **reportlab** | FPDF2 | FPDF2 if need simpler PDF generation. reportlab has better chart support built-in. |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| **Celery/Redis** | Overkill for 100-500 ballot batches. Adds infrastructure dependency. | asyncio + BackgroundTasks |
| **Django/Flask** | Too much boilerplate for minimal UI. Flask is 5-10x slower than FastAPI for async. | Gradio (simple) or FastAPI (production) |
| **Multiprocessing** | I/O-bound (API calls), not CPU-bound. GIL not the bottleneck. | asyncio with Semaphore |
| **ThreadPoolExecutor** | asyncio more efficient for HTTP I/O. Higher overhead than coroutines. | asyncio with httpx |
| **Tesseract OCR** | Poor Thai numeral recognition compared to vision LLMs. | OpenRouter (Gemma 3 12B IT) + Claude Vision fallback |
| **WebSocket** | Unnecessary complexity for simple upload/results flow. | REST polling or Server-Sent Events |

## Stack Patterns by Variant

### Parallel OCR Processing (100-500 ballots)

- Use `asyncio.gather()` with `asyncio.Semaphore(10)` for rate limiting
- Batch in groups of 20-50 with progress tracking
- **Why**: OpenRouter free tier = 50 requests/day, 20 RPM. Semaphore controls concurrency, not rate. Combine with time-based throttling if needed.

### Zone-Based Extraction (NEW)

```python
from PIL import Image

# Define zones for ส.ส. 5/18 constituency form
ZONES = {
    "province": (50, 100, 300, 150),      # (left, upper, right, lower)
    "constituency": (50, 160, 300, 210),
    "station": (50, 220, 300, 270),
    "candidate_1": (100, 400, 200, 450),  # Vote count for position 1
    "candidate_2": (100, 460, 200, 510),  # Vote count for position 2
    # ... more zones based on form template
}

def extract_zone(image_path: str, zone_name: str) -> Image.Image:
    """Extract a specific zone from ballot image."""
    img = Image.open(image_path)
    return img.crop(ZONES[zone_name])
```

**Why Pillow crop**: Reduces OCR token usage by 10-50x (only send relevant regions). Improves accuracy by focusing model on specific areas. Template coordinates can be calibrated once per form type.

### Web UI (Upload + View Results)

- Use Gradio `gr.File(file_count="multiple")` for batch upload
- `gr.Progress()` for real-time OCR status
- **Why**: 10 lines of code vs 100+ for custom FastAPI frontend. Built-in polling for long-running tasks.

### Executive Summary PDF

- Use existing `reportlab.graphics.charts` for bar/pie charts
- Register Thai font: `reportlab.pdfbase.pdfmetrics.registerFont(TTFont('Thai', 'NotoSansThai.ttf'))`
- **Why**: Already implemented for constituency/batch PDFs. Extend existing `generate_executive_summary_pdf()` function.

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| httpx 0.28.x | Python 3.9+ | Works with 3.14 |
| gradio 5.x | Python 3.8+ | Works with 3.14 |
| reportlab 4.4.x | Python 3.7+ | Works with 3.14 |
| anthropic 0.79.x | Python 3.8+ | Works with 3.14 |
| tenacity 9.x | Python 3.8+ | Works with 3.14 |
| Pillow 12.x | Python 3.10+ | Works with 3.14 |

## Integration Points

### Parallel OCR -> Existing Code

```python
# ballot_ocr.py modification pattern
import asyncio
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

MAX_CONCURRENT = 10  # Stay under OpenRouter 20 RPM

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=retry_if_exception_type(httpx.HTTPStatusError)
)
async def extract_ballot_data_async(
    image_path: str,
    semaphore: asyncio.Semaphore
) -> BallotData:
    async with semaphore:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload
            )
            response.raise_for_status()
            return parse_response(response.json())

async def process_batch_parallel(
    image_paths: list[str],
    max_concurrent: int = MAX_CONCURRENT
) -> list[BallotData]:
    semaphore = asyncio.Semaphore(max_concurrent)
    tasks = [extract_ballot_data_async(p, semaphore) for p in image_paths]
    return await asyncio.gather(*tasks, return_exceptions=True)
```

### Gradio -> ballot_ocr.py

```python
# web_ui.py (new file)
import gradio as gr
from ballot_ocr import process_batch_parallel, generate_executive_summary_pdf

def process_uploads(files, progress=gr.Progress()):
    results = []
    for i, file in enumerate(progress.tqdm(files, desc="Processing ballots")):
        result = process_single_ballot(file.name)
        results.append(result)
    return format_results(results), generate_summary_pdf(results)

demo = gr.Interface(
    fn=process_uploads,
    inputs=gr.File(file_count="multiple", label="Upload Ballot Images"),
    outputs=[
        gr.JSON(label="Results"),
        gr.File(label="Download Executive Summary PDF")
    ],
    title="Thai Ballot OCR",
    description="Upload ballot images to extract vote counts"
)

if __name__ == "__main__":
    demo.launch()
```

### Executive Summary -> Existing PDF Functions

The existing PDF code in ballot_ocr.py already handles:
- Multiple constituency aggregation
- Chart generation (`VerticalBarChart`, `Pie` from `reportlab.graphics.charts`)
- Thai text rendering
- Summary statistics tables

Extend with:
- Discrepancy highlighting (detected anomalies vs official results)
- National-level party vote aggregation
- Timestamp and batch metadata

## Rate Limiting Strategy

OpenRouter constraints:
- **Free tier**: 50 requests/day, 20 RPM
- **$10+ balance**: 1,000 requests/day

Recommended approach:
```python
# For 100-500 ballots, use controlled concurrency
SEMAPHORE_LIMIT = 10  # Max concurrent requests
REQUEST_DELAY = 0.1   # Small delay between batches

async def rate_limited_batch(paths: list[str]) -> list[BallotData]:
    semaphore = asyncio.Semaphore(SEMAPHORE_LIMIT)
    results = []
    for batch in chunked(paths, 20):  # Process in 20s
        batch_results = await asyncio.gather(
            *[extract_ballot_data_async(p, semaphore) for p in batch]
        )
        results.extend(batch_results)
        await asyncio.sleep(REQUEST_DELAY)  # Rate limit padding
    return results
```

## Sources

- **httpx vs aiohttp** — [Dev.to Comparison (Apr 2025)](https://dev.to/leapcell/comparing-requests-aiohttp-and-httpx-which-http-client-should-you-use-3784) — MEDIUM confidence (multiple sources agree)
- **FastAPI vs Flask 2026** — [Medium Performance Analysis](https://medium.com/@inprogrammer/fastapi-vs-flask-in-2026-i-migrated-a-real-app-with-metrics-864042103f5a) — MEDIUM confidence
- **Gradio File Upload** — [Gradio Docs](https://www.gradio.app/docs/gradio/file) — HIGH confidence (official docs)
- **asyncio Semaphore** — [Medium Guide (Sep 2025)](https://medium.com/@mr.sourav.raj/mastering-asyncio-semaphores-in-python-a-complete-guide-to-concurrency-control-6b4dd940e10e) — HIGH confidence (standard Python pattern)
- **Tenacity for Rate Limiting** — [OpenAI Cookbook](https://github.com/openai/openai-cookbook/blob/main/examples/How_to_handle_rate_limits.ipynb) — HIGH confidence (official)
- **FastAPI Background Tasks** — [FastAPI Docs](https://fastapi.tiangolo.com/tutorial/background-tasks/) — HIGH confidence (official docs)
- **Pillow Image.crop()** — [Pillow Documentation](https://pillow.readthedocs.io/en/stable/reference/Image.html) — HIGH confidence (official)
- **reportlab Charts** — [ReportLab Chart Gallery](https://www.reportlab.com/chartgallery/) — HIGH confidence (official)
- **Streamlit vs Gradio** — [Squadbase 2025](https://www.squadbase.dev/en/blog/streamlit-vs-gradio-in-2025-a-framework-comparison-for-ai-apps) — MEDIUM confidence (framework comparison)
- **Existing codebase analysis** — `/Users/nat/dev/election/ballot_ocr.py` — HIGH confidence (direct inspection)

---
*Stack research for: Thai Ballot OCR - Parallel Processing, Web UI, Executive PDF*
*Researched: 2026-02-16*
