# Pitfalls Research

**Domain:** Parallel OCR Processing, Web Interface, PDF Generation for Thai Ballot OCR
**Researched:** 2026-02-16
**Confidence:** HIGH (based on codebase analysis + current industry research)

---

## Critical Pitfalls

### Pitfall 1: API Rate Limiting with Parallel Requests

**What goes wrong:**
When parallelizing OCR API calls (OpenRouter, Claude Vision), hitting rate limits causes cascading failures. The current code has no rate limiting, retries, or backoff logic. With 100-500 ballots each making 1-2 API calls, this will fail silently or with cryptic errors.

**Why it happens:**
- OpenRouter free tier has undisclosed but real rate limits
- Sequential processing masked this issue in v1.0
- Developers assume "fire and forget" parallel execution works without throttling

**Consequences:**
- Partial batch completion with no visibility into which ballots failed
- Wasted API credits on retries without exponential backoff
- Silent data loss (ballots marked as processed but never actually extracted)

**How to avoid:**
- Use `asyncio.Semaphore` to limit concurrent API calls (recommend: 3-5 concurrent)
- Implement exponential backoff with jitter (10s, 30s, 60s delays)
- Track failed requests separately from successful ones
- Use `return_exceptions=True` with `asyncio.gather()` to prevent one failure from stopping all

**Warning signs:**
- HTTP 429 responses in logs
- Increasing API call duration
- Inconsistent batch sizes (some ballots missing from results)

**Phase to address:** Phase 1 (Parallel OCR Processing)

---

### Pitfall 2: Numeral OCR Accuracy Degradation at Scale

**What goes wrong:**
Single-threaded processing achieved 100% accuracy on test images, but parallel processing can introduce accuracy loss through:
1. **Digit confusion pairs**: 1/7, 5/6, 3/8, 4/9 are commonly confused in handwritten OCR
2. **Image quality variance**: Different lighting/resolution in real batches
3. **API response variation**: Same model can return different results for same image

**Why it happens:**
- Research shows 15-25% accuracy degradation in production vs benchmarks
- Thai numerals add confusion (similar shapes in handwriting)
- No confidence-based retry or validation in current code

**Consequences:**
- Vote count errors propagate to final tallies
- Discrepancy reports flag incorrect "mismatches"
- User trust erosion when comparing against ECT data

**How to avoid:**
- Keep the existing Thai text cross-validation (it's working)
- Add explicit validation for known confusion pairs (1 vs 7, 5 vs 6)
- Implement confidence threshold: if confidence < 0.8, queue for manual review
- Log raw API responses for post-hoc accuracy analysis

**Warning signs:**
- Thai text validation failures increasing
- Sum validation failures (votes don't add to total)
- Unusual digit patterns (many 7s where 1s expected)

**Phase to address:** Phase 1 (Parallel OCR Processing) - validation logic enhancement

---

### Pitfall 3: Web UI File Upload Memory Overflow

**What goes wrong:**
FastAPI/Flask file uploads store files in memory or temp files. With multiple ballot images (potentially 50-500 MB per batch), this causes memory exhaustion or disk space issues.

**Why it happens:**
- FastAPI's `UploadFile` uses `SpooledTemporaryFile` which writes to disk at 2MB threshold
- However, the temp files are not always cleaned up if errors occur
- Multiple concurrent uploads multiply memory usage

**Consequences:**
- Server OOM crashes during batch uploads
- Temp directory filling up with orphaned files
- Upload timeouts on slow connections

**How to avoid:**
- Use streaming uploads with `await file.read(chunk_size)` (e.g., 64KB chunks)
- Explicitly call `await file.close()` in finally blocks (not just relying on GC)
- Set maximum file size limits per upload and per batch
- Implement cleanup job for orphaned temp files

**Warning signs:**
- Increasing RSS memory during upload processing
- `/tmp` directory filling with `tmp*` files
- Upload endpoint becoming unresponsive under load

**Phase to address:** Phase 2 (Web Interface)

---

### Pitfall 4: Path-Based Metadata Inference Failures

**What goes wrong:**
The existing code builds `polling_station_id` from extracted province/district/unit data. If adding path-based inference (e.g., parsing `พระนครศรีอยุธยา_4/ballot_001.png`), Unicode encoding issues and inconsistent naming will cause failures.

**Why it happens:**
- Thai characters in filenames cause encoding issues on different filesystems
- Users may use inconsistent naming conventions
- PEP 529 changes Windows filesystem encoding behavior

**Consequences:**
- Ballots processed but with wrong/missing province data
- Lookup failures against ECT API (province name mismatch)
- Files that "should work" failing silently

**How to avoid:**
- Never rely solely on path parsing; always validate against ECT province list
- Use `pathlib.Path` consistently (handles encoding better than string concatenation)
- Implement explicit Unicode normalization (NFC form for Thai)
- Add path sanitization that preserves Thai characters but removes problematic ones

**Warning signs:**
- `UnicodeEncodeError` in logs
- Province validation failures on files with Thai names
- Inconsistent polling station IDs in output

**Phase to address:** Phase 2 (Web Interface) - file handling logic

---

### Pitfall 5: Async State Management Race Conditions

**What goes wrong:**
When tracking batch processing progress (for web UI updates), shared state between concurrent tasks can cause race conditions. Progress counters, result lists, and status flags can become inconsistent.

**Why it happens:**
- Multiple async tasks updating the same dict/list
- No locking mechanism for shared state
- `asyncio.gather()` with `return_exceptions=True` doesn't guarantee order

**Consequences:**
- Progress bar showing wrong completion percentage
- Missing or duplicate results in final output
- UI showing "processing" after all tasks complete

**How to avoid:**
- Use `asyncio.Lock` for any shared mutable state
- Prefer immutable data structures (append-only lists, new dicts)
- Use a proper task queue (e.g., background worker pattern) for long-running batches
- Store intermediate results in files/database, not just memory

**Warning signs:**
- Intermittent assertion failures
- Final count doesn't match input count
- Progress exceeding 100%

**Phase to address:** Phase 2 (Web Interface) and Phase 1 (Parallel OCR Processing)

---

### Pitfall 6: PDF Generation Memory Bloat

**What goes wrong:**
Generating PDF reports (especially batch summaries with charts) using reportlab keeps images and drawing objects in memory until the PDF is finalized. With 100-500 ballots, this can consume gigabytes of RAM.

**Why it happens:**
- ReportLab builds the entire PDF in memory before writing
- Chart objects hold references to all data points
- Image embeddings duplicate memory usage

**Consequences:**
- Memory exhaustion during report generation
- Slow report generation (minutes instead of seconds)
- Failed batches after hours of processing

**How to avoid:**
- Generate PDFs in chunks (e.g., per-constituency, then merge)
- Use `SimpleDocTemplate.build()` with story that releases objects as processed
- Limit chart data points (aggregate rather than detail for large batches)
- Consider streaming to file incrementally if possible

**Warning signs:**
- Increasing memory during PDF generation phase
- PDFs taking >30 seconds to generate for 100+ ballots
- System swapping during report generation

**Phase to address:** Phase 3 (Executive Summary PDF)

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Skip rate limiting in MVP | Faster development | API bans, failed batches | Never - implement from start |
| In-memory progress tracking | Simpler code | Race conditions, lost state | Single-user, <50 ballots |
| No temp file cleanup | Saves a few lines of code | Disk exhaustion | Never - always cleanup |
| Trust path metadata | Less OCR calls | Wrong province assignments | Never - always validate |
| Skip confidence logging | Faster processing | No audit trail for errors | Never - debugging impossible |

---

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| OpenRouter API | No timeout handling | Set explicit timeout (30s) + retry with backoff |
| FastAPI UploadFile | Not closing file handles | Always `await file.close()` in finally block |
| reportlab PDF | Building entire doc in memory | Use streaming build with page templates |
| asyncio | Using gather() without return_exceptions | Use `return_exceptions=True` and check results |
| Path handling | String concatenation with Thai chars | Use `pathlib.Path` + validate against known list |

---

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| No concurrency limit | API 429 errors, random failures | Semaphore with 3-5 concurrent limit | 10+ parallel requests |
| Memory-based progress tracking | Missing results, wrong counts | File/database-backed state | 50+ concurrent tasks |
| Full image in memory | OOM errors, swap thrashing | Stream uploads, process in chunks | 50+ MB uploads |
| PDF with all data points | Generation takes minutes | Aggregate data, limit points per chart | 100+ ballots in one PDF |

---

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| No upload size limit | DoS via large files | Set max file size (e.g., 10MB) and batch size (500) |
| Trusted path metadata | Path injection attacks | Sanitize paths, validate against whitelist |
| Unvalidated file types | Malicious file uploads | Check magic bytes, not just extension |
| API keys in logs | Credential exposure | Mask API keys in all log output |

---

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| No progress feedback | Users think system frozen | Real-time progress with current ballot count |
| Silent partial failures | Missing data undetected | Explicit "X of Y processed, Z failed" summary |
| No retry mechanism | Manual re-upload required | Retry button for failed ballots |
| Generic error messages | Users can't fix issues | Specific error (e.g., "Province name not recognized") |

---

## "Looks Done But Isn't" Checklist

- [ ] **Parallel Processing:** Often missing rate limiting — verify API calls have backoff and limits
- [ ] **Progress Tracking:** Often missing state persistence — verify progress survives server restart
- [ ] **File Cleanup:** Often missing temp file deletion — verify `finally` blocks close and delete
- [ ] **Error Aggregation:** Often missing error collection — verify all errors logged, not just last one
- [ ] **Unicode Handling:** Often missing normalization — verify Thai chars in paths work on all platforms
- [ ] **Confidence Thresholds:** Often missing low-confidence handling — verify below-threshold ballots flagged

---

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Rate limit exceeded | LOW | Wait and retry with backoff |
| Memory overflow | MEDIUM | Restart batch from last checkpoint |
| Partial batch failure | MEDIUM | Identify failed ballots via logs, re-process |
| Path encoding corruption | HIGH | Re-extract from original files |
| Lost progress state | HIGH | Re-scan output directory to determine progress |

---

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| API Rate Limiting | Phase 1 (Parallel OCR) | Test with 20 concurrent requests, verify no 429s |
| Numeral Accuracy | Phase 1 (Parallel OCR) | Run existing test suite on parallel output |
| File Upload Memory | Phase 2 (Web Interface) | Upload 100MB batch, verify memory bounded |
| Path Encoding | Phase 2 (Web Interface) | Test with Thai filenames on different OS |
| Async Race Conditions | Phase 2 (Web Interface) | Stress test with concurrent uploads |
| PDF Memory | Phase 3 (Exec Summary) | Generate PDF for 500 ballots, monitor memory |

---

## Sources

- [Python Asyncio for LLM Concurrency: Best Practices](https://www.newline.co/@zaoyang/python-asyncio-for-llm-concurrency-best-practices--bc079176) - Newline, Sep 2025
- [Async APIs with FastAPI: Patterns, Pitfalls & Best Practices](https://shiladtyamajumder.medium.com/async-apis-with-fastapi-patterns-pitfalls-best-practices-2d72b2b66f25) - Medium, Nov 2025
- [Uploading Files Using FastAPI: Complete Guide](https://betterstack.com/community/guides/scaling-python/uploading-files-using-fastapi/) - Better Stack, Jul 2025
- [Chasing a Memory 'Leak' in our Async FastAPI Service](https://build.betterup.com/chasing-a-memory-leak-in-our-async-fastapi-service-how-jemalloc-fixed-our-rss-creep/) - BetterUp Engineering, Sep 2025
- [FastAPI UploadFile Memory Discussion](https://github.com/tiangolo/fastapi/issues/4833) - FastAPI GitHub
- [Handwritten Digit Confusion Research](https://www.researchgate.net/publication/356092240_Enhanced_Handwritten_Document_Recognition_Using_Confusion_Matrix_Analysis) - ResearchGate
- [The Definitive Guide to OCR Accuracy: Benchmarks and Best Practices for 2025](https://medium.com/@sanjeeva.bora/the-definitive-guide-to-ocr-accuracy-benchmarks-and-best-practices-for-2025-8116609655da) - Medium, Apr 2025
- [10 Python Mistakes You Might Still Be Making in 2025](https://python.plainenglish.io/10-python-mistakes-you-might-still-be-making-in-2025-fbb6d4435373) - Plain English, Mar 2025
- [ReportLab Memory Usage Discussion](https://stackoverflow.com/questions/57775447/reportlab-using-a-lot-of-memory-generating-large-pdf-files) - Stack Overflow
- Codebase analysis: `/Users/nat/dev/election/ballot_ocr.py`, `/Users/nat/dev/election/.planning/codebase/CONCERNS.md`

---

*Pitfalls research for: Thai Ballot OCR v1.1 (Parallel Processing, Web UI, Executive Summary)*
*Researched: 2026-02-16*
