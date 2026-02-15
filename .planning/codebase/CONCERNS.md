# Codebase Concerns

**Analysis Date:** 2026-02-16

## Tech Debt

### Error Handling Inconsistencies
**Files:** `ballot_ocr.py`, `ect_api.py`, `gdrivedl.py`
- Issue: Mixed error handling patterns - some functions return None on failure, others raise exceptions
- Files: Multiple functions with bare try/except blocks that print and return None
- Impact: Makes error tracking difficult and inconsistent
- Fix approach: Standardize on custom exceptions with proper error codes and logging

### Hardcoded API Keys and Endpoints
**Files:** `ballot_ocr.py` (lines 617, 624)
- Issue: API endpoints and model names hardcoded in multiple places
- Files: `/Users/nat/dev/election/ballot_ocr.py`
- Impact: Difficult to change providers or environments
- Fix approach: Move to configuration files with environment variable overrides

### File Size and Complexity
**Files:** `ballot_ocr.py` (1,158 lines)
- Issue: Large monolithic file handling multiple responsibilities (OCR, API calls, validation, export)
- Files: `/Users/nat/dev/election/ballot_ocr.py`
- Impact: Difficult to maintain, test, and extend
- Fix approach: Split into modules: ocr/, api/, validation/, export/

### Thai Text Processing Fragility
**Files:** `ballot_ocr.py` (lines 91-169)
- Issue: Complex Thai number parsing with hardcoded mappings and fragile string matching
- Files: `/Users/nat/dev/election/ballot_ocr.py`
- Impact: Prone to errors with variations in handwriting or spelling
- Fix approach: Implement robust Thai number parsing library with better error handling

## Known Bugs

### PDF Processing Reliability
**Files:** `ballot_ocr.py` (lines 213-225)
- Issue: PDF to image conversion uses pdftoppm without error checking for corrupt PDFs
- Files: `/Users/nat/dev/election/ballot_ocr.py`
- Symptoms: Silent failures on malformed PDFs, no output generated
- Trigger: Corrupt or password-protected PDF files
- Workaround: Add PDF validation and error handling

### API Response Parsing
**Files:** `ballot_ocr.py` (lines 651-656)
- Issue: Fragile JSON parsing that assumes markdown code blocks
- Files: `/Users/nat/dev/election/ballot_ocr.py`
- Symptoms: Failures when API returns plain JSON without markdown formatting
- Trigger: Changes in API response format
- Workaround: More robust JSON extraction with multiple fallback patterns

## Security Considerations

### API Key Exposure Risk
**Files:** `ballot_ocr.py` (line 597)
- Risk: OPENROUTER_API_KEY read from environment variables, stored in process memory
- Files: `/Users/nat/dev/election/ballot_ocr.py`
- Current mitigation: Using environment variables (good)
- Recommendations: Add rotation policy, audit logging for API usage

### Google Drive Authentication
**Files:** `drive_auth.py` (lines 11-12, 28-35)
- Risk: Credentials stored in pickle file without encryption
- Files: `/Users/nat/dev/election/drive_auth.py`
- Current mitigation: Local file only, proper OAuth flow
- Recommendations: Add encryption to token file, consider service accounts for production

### External API Dependencies
**Files:** `ballot_ocr.py`, `ect_api.py`
- Risk: Third-party APIs (OpenRouter, ECT) could change or become unavailable
- Files: `/Users/nat/dev/election/ballot_ocr.py`, `/Users/nat/dev/election/ect_api.py`
- Current mitigation: Basic fallback to Claude Vision
- Recommendations: Implement proper circuit breaker pattern, add rate limiting

## Performance Bottlenecks

### Synchronous API Calls
**Files:** `ballot_ocr.py` (lines 614-643, 860-896)
- Problem: Sequential API calls for form detection and data extraction
- Files: `/Users/nat/dev/election/ballot_ocr.py`
- Cause: No async/await or multiprocessing for batch processing
- Improvement path: Implement async processing with aiohttp for concurrent API calls

### Image Encoding Overhead
**Files:** `ballot_ocr.py` (lines 593-594, 740)
- Problem: Base64 encoding for every API call (doubles memory usage)
- Files: `/Users/nat/dev/election/ballot_ocr.py`
- Cause: No streaming or chunked upload support
- Improvement path: Implement streaming uploads or use SDKs that support it

### ECT API Caching
**Files:** `ect_api.py` (lines 64-69)
- Problem: Limited lru_cache(1) means repeated API calls for same data
- Files: `/Users/nat/dev/election/ect_api.py`
- Cause: Cache only remembers last call, not all data
- Improvement path: Use persistent caching (Redis/database) with TTL

## Fragile Areas

### PDF Processing Chain
**Files:** `ballot_ocr.py` (lines 213-225, 592-594)
- Files: `/Users/nat/dev/election/ballot_ocr.py`
- Why fragile: Depends on external pdftoppm utility, no error handling for corrupt files
- Safe modification: Add PDF validation, try/catch around subprocess
- Test coverage: Missing automated tests for PDF conversion

### Form Type Detection
**Files:** `ballot_ocr.py` (lines 234-311)
- Files: `/Users/nat/dev/election/ballot_ocr.py`
- Why fragile: Uses AI vision with complex prompts, prone to hallucination
- Safe modification: Add confidence scores, fallback to pattern matching
- Test coverage: Multiple test results exist but no automated detection tests

### Google Drive Integration
**Files:** `gdrivedl.py`
- Files: `/Users/nat/dev/election/gdrivedl.py`
- Why fragile: Depends on HTML parsing of Google pages, fragile to UI changes
- Safe modification: Add API-based fallback for folder listing
- Test coverage: No automated tests for download functionality

## Scaling Limits

### Batch Processing Capability
**Files:** `ballot_ocr.py` (main function, lines 1086-1158)
- Current capacity: Sequential processing of one file at a time
- Limit: No parallel processing, slow for large batches
- Scaling path: Implement worker pool with asyncio or multiprocessing

### Memory Usage
**Files:** Multiple files
- Current capacity: Limited by system RAM (base64 encoding doubles image size)
- Limit: Large PDFs or many images will cause OOM
- Scaling path: Implement streaming processing and chunked file handling

## Dependencies at Risk

### Tesseract OCR
**Files:** `tesseract_ocr.py`
- Risk: Legacy version without proper Thai language support
- Impact: Poor OCR accuracy for handwritten Thai numbers
- Migration plan: Switch to PaddleOCR or commercial OCR services with better Thai support

### requests Library
**Files:** `ballot_ocr.py`, `ect_api.py`
- Risk: Basic HTTP client without advanced features
- Impact: No connection pooling, retries, or proper timeout handling
- Migration plan: Use httpx for better async support and features

## Missing Critical Features

### Data Validation Pipeline
**Issue:** No comprehensive validation of extracted data against expected patterns
- Problem: Could accept invalid vote counts or malformed province names
- Blocks: Production deployment without data integrity guarantees

### Audit Trail
**Issue:** No logging of processing decisions or data provenance
- Problem: Difficult to trace errors or verify results
- Blocks: Regulatory compliance and debugging

### Unit Test Coverage
**Issue:** No automated tests detected in codebase
- Problem: High risk of regressions during development
- Blocks: Continuous integration and reliable deployments

## Test Coverage Gaps

### Core OCR Functionality
**What's not tested:** Form detection, vote extraction, validation logic
- Files: `/Users/nat/dev/election/ballot_ocr.py`
- Risk: Changes to AI prompts could break extraction silently
- Priority: High - core functionality

### Error Handling Paths
**What's not tested:** API failures, corrupt PDFs, invalid responses
- Files: All files
- Risk: System appears to work but fails gracefully
- Priority: Medium - robustness

### Edge Cases
**What's not tested:** Handwritten variations, unusual province names, malformed inputs
- Files: `/Users/nat/dev/election/ballot_ocr.py`
- Risk: Poor performance on real-world data
- Priority: High - real-world readiness

---

*Concerns audit: 2026-02-16*