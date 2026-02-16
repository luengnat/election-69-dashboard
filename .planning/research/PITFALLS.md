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
- OpenRouter enforces 20 requests/minute hard limit (verified [official docs](https://openrouter.ai/docs/api/reference/limits))
- Free tier: additional 50 requests/day cap for users with <$10 credits
- Sequential processing masked this issue in v1.0
- Developers assume "fire and forget" parallel execution works without throttling

**Consequences:**
- Partial batch completion with no visibility into which ballots failed
- Wasted API credits on retries without exponential backoff
- Silent data loss (ballots marked as processed but never actually extracted)
- For 500 ballots at 20/min: minimum 25 minutes processing time

**How to avoid:**
- Implement Token Bucket rate limiter (not just Semaphore)
- Use `asyncio.Semaphore` to limit concurrent API calls (recommend: 3-5 concurrent)
- Implement exponential backoff with jitter (1s, 2s, 4s max 3 retries)
- Track failed requests separately from successful ones
- Use `return_exceptions=True` with `asyncio.gather()` to prevent one failure from stopping all

**Warning signs:**
- HTTP 429 responses in logs
- Increasing API call duration
- Inconsistent batch sizes (some ballots missing from results)
- Processing throughput suddenly dropping to 0

**Phase to address:** Phase 1 (Parallel OCR Processing)

---

### Pitfall 2: OCR Number Accuracy Degradation Under Parallel Processing

**What goes wrong:**
Single-threaded processing achieved 100% accuracy on test images, but parallel processing can introduce accuracy loss through:
1. **Digit confusion pairs**: 1/7, 5/6, 3/8, 4/9 are commonly confused in handwritten OCR
2. **Image quality variance**: Different lighting/resolution in real batches
3. **API response variation**: Same model can return different results for same image
4. **Context loss**: The AI's cross-validation context may be affected by parallel request handling

**Why it happens:**
- Research shows 15-25% accuracy degradation in production vs benchmarks per [OCR accuracy research](https://www.researchgate.net/publication/362410986_iOCR_Informed_Optical_Character_Recognition_for_Election_Ballot_Tallies)
- Thai numerals add confusion (similar shapes in handwriting)
- No confidence-based retry or validation in current code
- Race conditions in API client reuse across async contexts

**Consequences:**
- Vote count errors propagate to final tallies (CRITICAL for election data)
- Discrepancy reports flag incorrect "mismatches"
- User trust erosion when comparing against ECT data
- Difficult to detect without checksum validation

**How to avoid:**
- Keep the existing Thai text cross-validation (it's working)
- Create fresh API client instances per worker/thread (no shared clients)
- Add explicit validation for known confusion pairs (1 vs 7, 5 vs 6)
- Implement confidence threshold: if confidence < 0.95, queue for manual review
- Log raw API responses for post-hoc accuracy analysis
- Maintain per-request timeout guards (30s per ballot)
- Verify extracted sums against reported totals before accepting results

**Warning signs:**
- Thai text validation failures increasing
- Sum validation failures (votes don't add to total)
- Unusual digit patterns (many 7s where 1s expected)
- Confidence scores dropping below 0.95 on previously accurate images

**Phase to address:** Phase 1 (Parallel OCR Processing) - validation logic enhancement

---

### Pitfall 3: Web UI File Upload Memory Overflow

**What goes wrong:**
FastAPI/Flask file uploads store files in memory or temp files. With multiple ballot images (potentially 50-500 MB per batch), this causes memory exhaustion or disk space issues.

**Why it happens:**
- FastAPI's `UploadFile` uses `SpooledTemporaryFile` which writes to disk at 2MB threshold
- However, the temp files are not always cleaned up if errors occur
- Multiple concurrent uploads multiply memory usage
- Base64 encoding doubles memory usage per image

**Consequences:**
- Server OOM crashes during batch uploads
- Temp directory filling up with orphaned files
- Upload timeouts on slow connections

**How to avoid:**
- Use streaming uploads with `await file.read(chunk_size)` (e.g., 64KB chunks)
- Explicitly call `await file.close()` in finally blocks (not just relying on GC)
- Set maximum file size limits per upload and per batch
- Implement cleanup job for orphaned temp files
- Process images one at a time (stream, don't batch load)
- Use generator pattern for batch processing

**Warning signs:**
- Increasing RSS memory during upload processing
- `/tmp` directory filling with `tmp*` files
- Upload endpoint becoming unresponsive under load

**Phase to address:** Phase 2 (Web Interface)

---

### Pitfall 4: Path-Based Metadata Inference Failures

**What goes wrong:**
The existing code builds `polling_station_id` from extracted province/district/unit data. If adding path-based inference (e.g., parsing Thai filenames), Unicode encoding issues and inconsistent naming will cause failures. A single misparsed path can associate votes with the wrong jurisdiction.

**Why it happens:**
- Thai characters in filenames cause encoding issues on different filesystems
- Users may use inconsistent naming conventions (e.g., `บัตร_แพร่_1_2.png` vs `ballot_phrae_cons1_unit2.png`)
- PEP 529 changes Windows filesystem encoding behavior
- Form header OCR errors on province names

**Consequences:**
- Ballots processed but with wrong/missing province data
- Lookup failures against ECT API (province name mismatch)
- Votes attributed to wrong constituency
- Files that "should work" failing silently
- ECT validation fails (wrong cons_id lookup)

**How to avoid:**
- Never rely solely on path parsing; always validate against ECT province list (77 provinces)
- Cross-check: filename metadata vs form header metadata must agree
- Use `pathlib.Path` consistently (handles encoding better than string concatenation)
- Implement explicit Unicode normalization (NFC form for Thai)
- Add path sanitization that preserves Thai characters but removes problematic ones
- Use canonical province lookup: `ect_data.validate_province_name(thai_name)`
- Flag ballots with mismatch for manual review

**Warning signs:**
- `UnicodeEncodeError` in logs
- Province name not in ECT list
- Filename says Province A, form says Province B
- Constituency number outside valid range for province
- Inconsistent polling station IDs in output

**Phase to address:** Phase 1 (Parallel OCR Processing) - validation logic enhancement

---

### Pitfall 5: Async State Management Race Conditions

**What goes wrong:**
When tracking batch processing progress (for web UI updates), shared state between concurrent tasks can cause race conditions. Progress counters, result lists, and status flags can become inconsistent.

**Why it happens:**
- Multiple async tasks updating the same dict/list
- No locking mechanism for shared state
- `asyncio.gather()` with `return_exceptions=True` doesn't guarantee order
- No persistence of job state to disk

**Consequences:**
- Progress bar showing wrong completion percentage
- Missing or duplicate results in final output
- UI showing "processing" after all tasks complete
- No resume capability after interruption
- Progress lost on page refresh or browser close

**How to avoid:**
- Use `asyncio.Lock` for any shared mutable state
- Prefer immutable data structures (append-only lists, new dicts)
- Use a proper task queue (e.g., background worker pattern) for long-running batches
- Store intermediate results in files/database, not just memory
- Persist job state to SQLite/file (job_id, total, completed, failed, results)
- Use Server-Sent Events (SSE) for progress updates (simpler than WebSocket per [FastAPI patterns](https://pub.towardsai.net/background-tasks-vs-websockets-vs-sse-in-python-which-one-should-you-use-for-long-running-af18a3d98d23))
- Implement checkpointing: save progress every 10 ballots
- Job status endpoint: `GET /jobs/{job_id}/status`

**Warning signs:**
- Intermittent assertion failures
- Final count doesn't match input count
- Progress exceeding 100%
- Progress resets to 0 on page refresh

**Phase to address:** Phase 2 (Web Interface) and Phase 1 (Parallel OCR Processing)

---

### Pitfall 6: Zone Misalignment for Form Variants

**What goes wrong:**
The 6 form types (5/16, 5/17, 5/18, each with constituency and party-list variants) have different layouts. The AI vision prompts are carefully calibrated for each. Wrong form type detection leads to extracting from wrong "zones" - reading party numbers as candidate positions, or vice versa.

**Why it happens:**
- Form type detection happens first, but can be wrong
- Similar headers between variants
- Thai numeral confusion: ๑๖ (16) vs ๑๗ (17) vs ๑๘ (18)
- Party-list forms span multiple pages with different party ranges (e.g., 1-20, 21-40)

**Consequences:**
- Extract candidate votes as party votes (or vice versa)
- Miss rows entirely (expecting 6 candidates, form has 57 parties)
- Aggregation produces nonsense totals
- Discrepancy reports show wild mismatches

**How to avoid:**
- Form type detection must be 100% confident before extraction
- Verify: detected form type matches expected candidate/party count
- Cross-check: `is_party_list` flag vs presence of `(บช)` in form code
- Log form type confidence and flag low-confidence detections
- For multi-page party-list forms, track `page_parties` range
- If candidate count > 10 detected on non-party-list form, flag for review

**Warning signs:**
- Form says constituency but 57 entries extracted
- Form says party-list but only 6 entries extracted
- Mismatch between detected form type and prompt used
- Page parties range overlapping or missing

**Phase to address:** Phase 1 (Parallel OCR Processing) - form detection accuracy is prerequisite

---

### Pitfall 7: PDF Generation Memory Bloat

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
- Call `gc.collect()` after each PDF generation

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
| Single API client instance | Less overhead | Race conditions in parallel | Never for parallel processing |
| Skip numeric/Thai validation | Faster processing | Silent accuracy errors | Never - election data critical |
| No checkpointing | Faster initial dev | No resume capability | MVP only, fix in Phase 2 |

---

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| OpenRouter API | No timeout handling, fire concurrent requests | Set explicit timeout (30s) + Token Bucket limiter |
| Claude Vision | Reuse client across async tasks | Fresh client per worker |
| FastAPI UploadFile | Not closing file handles | Always `await file.close()` in finally block |
| reportlab PDF | Building entire doc in memory | Use streaming build with page templates |
| asyncio | Using gather() without return_exceptions | Use `return_exceptions=True` and check results |
| Path handling | String concatenation with Thai chars | Use `pathlib.Path` + validate against ECT list |
| ECT API | Lookup before validating province name | Validate first, then lookup cons_id |
| PIL/Pillow | Keep Image objects open | Close immediately after encoding |

---

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| No concurrency limit | API 429 errors, random failures | Semaphore + Token Bucket (3-5 concurrent) | 10+ parallel requests |
| Memory-based progress tracking | Missing results, wrong counts | File/database-backed state | 50+ concurrent tasks |
| Full image in memory | OOM errors, swap thrashing | Stream uploads, process one at a time | 50+ MB uploads |
| PDF with all data points | Generation takes minutes | Aggregate data, limit points per chart | 100+ ballots in one PDF |
| Base64 memory bloat | RAM usage 2x expected | Delete after use, gc.collect() every 50 images | 50+ images |
| Unbounded parallelism | System instability | Semaphore(max_workers=2-4 based on RAM) | 10+ concurrent |

---

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| No upload size limit | DoS via large files | Set max file size (10MB) and batch size (500) |
| Trusted path metadata | Path injection attacks | Sanitize paths, validate against whitelist |
| Unvalidated file types | Malicious file uploads | Check magic bytes, not just extension |
| API keys in logs | Credential exposure | Mask API keys in all log output |
| No rate limiting on upload | DoS via large batch | Max 500 with clear messaging |

---

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| No progress feedback | Users think system frozen | SSE progress stream with current ballot count/% |
| Silent partial failures | Missing data undetected | Explicit "X of Y processed, Z failed" summary |
| No retry mechanism | Manual re-upload required | Retry button for failed ballots |
| Generic error messages | Users can't fix issues | Specific error (e.g., "Province name not recognized") |
| No download notification | User leaves before completion | Browser notification + email |
| Batch size unlimited | User uploads 10,000 images | Max 500 with clear messaging |
| No resume capability | Must restart 500-ballot batch | Checkpoint every 10 ballots |

---

## Known Issues (v1.1)

| Issue | Impact | Status | Workaround |
|-------|--------|--------|------------|
| Form type detection for party-list forms | OCR may not detect `(บช)` suffix correctly, classifying party-list forms as constituency | Open | Manual review of forms with many entries (>10) |
| Ground truth test failures | Test suite expects specific form types that may differ from current OCR output | Documented | Update ground truth to match current behavior or improve detection |
| Province extraction variance | Different AI models may extract different provinces for same image | Monitored | Use ECT validation to catch invalid provinces |

---

## "Looks Done But Isn't" Checklist

- [ ] **Parallel Processing:** Often missing rate limiting - verify Token Bucket + Semaphore implemented
- [ ] **Progress Tracking:** Often missing persistence - verify survives page refresh
- [ ] **File Cleanup:** Often missing temp file deletion - verify `finally` blocks close and delete
- [ ] **Error Aggregation:** Often missing error collection - verify all errors logged, not just last one
- [ ] **Unicode Handling:** Often missing normalization - verify Thai chars in paths work on all platforms
- [ ] **Confidence Thresholds:** Often missing low-confidence handling - verify below-threshold ballots flagged
- [ ] **Memory Management:** Often missing explicit cleanup - verify gc.collect() called, base64 deleted
- [ ] **Validation Pipeline:** Often skipped for speed - verify numeric/Thai cross-check still runs
- [ ] **Form Type Detection:** Often assumed correct - verify confidence threshold enforced

---

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Rate limit exceeded | LOW | Wait 60s, resume from checkpoint |
| Memory overflow | MEDIUM | Reduce concurrency, resume from checkpoint |
| Partial batch failure | MEDIUM | Identify failed ballots via logs, re-process |
| Path encoding corruption | HIGH | Re-extract from original files |
| Lost progress state | HIGH | Re-scan output directory to determine progress |
| Wrong jurisdiction attribution | HIGH | Re-process affected ballots with validation |
| Silent accuracy errors | CRITICAL | Re-process entire batch with validation |

---

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| API Rate Limiting | Phase 1 (Parallel OCR) | Test with 20 concurrent requests, verify no 429s |
| Number Accuracy Degradation | Phase 1 (Parallel OCR) | Run accuracy tests on 100-ballot batch, compare to single-threaded |
| Path Inference Failures | Phase 1 (Parallel OCR) | Run validation tests, verify all provinces match ECT |
| Zone Misalignment | Phase 1 (Parallel OCR) | Run form detection tests on all 6 variants |
| Memory Management | Phase 1 (Parallel OCR) | Profile memory usage, verify no growth over 100 images |
| File Upload Memory | Phase 2 (Web Interface) | Upload 100MB batch, verify memory bounded |
| Async Race Conditions | Phase 2 (Web Interface) | Stress test with concurrent uploads |
| Progress Tracking Loss | Phase 2 (Web Interface) | Refresh browser mid-batch, verify progress restored |
| PDF Memory | Phase 3 (Exec Summary) | Generate PDF for 500 ballots, monitor memory |

---

## Sources

- [OpenRouter API Rate Limits](https://openrouter.ai/docs/api/reference/limits) - Official documentation (HIGH confidence)
- [Informed OCR for Election Ballots](https://www.researchgate.net/publication/362410986_iOCR_Informed_Optical_Character_Recognition_for_Election_Ballot_Tallies) - Election OCR accuracy research (MEDIUM confidence)
- [Python Asyncio for LLM Concurrency: Best Practices](https://www.newline.co/@zaoyang/python-asyncio-for-llm-concurrency-best-practices--bc079176) - Newline, Sep 2025
- [Async APIs with FastAPI: Patterns, Pitfalls & Best Practices](https://shiladtyamajumder.medium.com/async-apis-with-fastapi-patterns-pitfalls-best-practices-2d72b2b66f25) - Medium, Nov 2025
- [Uploading Files Using FastAPI: Complete Guide](https://betterstack.com/community/guides/scaling-python/uploading-files-using-fastapi/) - Better Stack, Jul 2025
- [Background Tasks vs WebSockets vs SSE in Python](https://pub.towardsai.net/background-tasks-vs-websockets-vs-sse-in-python-which-one-should-you-use-for-long-running-af18a3d98d23) - Towards AI, Aug 2025
- [TensorFlow OOM Issues](https://github.com/tensorflow/models/issues/1817) - Image processing memory patterns (HIGH confidence)
- [Batch Image Processing Memory](https://www.centron.de/en/tutorial/how-to-maximize-gpu-utilization-with-the-right-batch-size-for-deep-learning/) - Memory exhaustion patterns (MEDIUM confidence)
- [ReportLab Memory Usage Discussion](https://stackoverflow.com/questions/57775447/reportlab-using-a-lot-of-memory-generating-large-pdf-files) - Stack Overflow
- Codebase analysis: `/Users/nat/dev/election/ballot_ocr.py` - Existing implementation patterns (HIGH confidence)
- Codebase concerns: `/Users/nat/dev/election/.planning/codebase/CONCERNS.md` - Known issues (HIGH confidence)

---

*Pitfalls research for: Thai Ballot OCR v1.1 (Parallel Processing, Web UI, Executive Summary)*
*Researched: 2026-02-16*
