# Architecture

**Analysis Date:** 2024-02-16

## Pattern Overview

**Overall:** Data Processing Pipeline with External Integration

**Key Characteristics:**
- Batch processing of Thai election ballot images
- Multi-modal OCR (Tesseract + custom extraction)
- External API validation against official ECT data
- Error detection through cross-validation techniques
- File-based data persistence with JSON output

## Layers

**Data Layer:**
- Purpose: Stores raw images and processed results
- Location: `/Users/nat/dev/election/data/` and `/Users/nat/dev/election/test_images/`
- Contains: PNG images, JSON result files
- Dependencies: File system operations
- Used by: Ballot OCR processor, Test runner

**Processing Layer:**
- Purpose: Extracts and processes ballot information from images
- Location: `/Users/nat/dev/election/ballot_ocr.py`
- Contains: OCR logic, form classification, vote extraction
- Depends on: Tesseract OCR, PIL imaging library
- Used by: Main application entry point

**Validation Layer:**
- Purpose: Validates extracted data against official sources
- Location: `/Users/nat/dev/election/ect_api.py`
- Contains: ECT API client, data models, caching
- Depends on: HTTP requests, official ECT endpoints
- Used by: Ballot OCR processor for validation

**Integration Layer:**
- Purpose: Handles external data sources and authentication
- Location: `/Users/nat/dev/election/gdrivedl.py` and `/Users/nat/dev/election/drive_auth.py`
- Contains: Google Drive integration, OAuth authentication
- Depends on: Google APIs, authentication tokens
- Used by: Data download component

## Data Flow

**Ballot Processing Pipeline:**

1. **Input**: PNG image of Thai ballot form
2. **Form Detection**: Analyze form headers to determine type (ส.ส. 5/16, 5/17, 5/18 with/without party-list)
3. **OCR Processing**: Extract text using Tesseract Thai+English language pack
4. **Vote Extraction**: Identify numeric and Thai text vote counts for each candidate/position
5. **Cross-Validation**: Compare numeric vs Thai text representations
6. **Sum Validation**: Verify individual votes sum to reported total
7. **ECT Validation**: Cross-check against official Election Commission data
8. **Output**: JSON structured result with metadata and validation flags

**State Management:**
- Intermediate results stored in memory during processing
- Final outputs saved as JSON files
- ECT data cached locally with LRU strategy
- Authentication tokens persisted for Google Drive access

## Key Abstractions

**FormType:**
- Purpose: Enumerates the 6 Thai election ballot form variations
- Examples: `ballot_ocr.py:40-63`
- Pattern: Enum class with computed properties

**VoteCount:**
- Purpose: Represents extracted vote counts with validation status
- Examples: Data structures in `ballot_ocr.py`
- Pattern: Dictionary-based with validation flags

**ECT Client:**
- Purpose: Interface to official Election Commission API
- Examples: `ect_api.py:15-27`
- Pattern: API client with caching, HTTP requests, data models

**Thai Number Parser:**
- Purpose: Converts Thai numeral text to integers
- Examples: `ballot_ocr.py:91-100`
- Pattern: Rule-based parser with digit/ten/hundred/thousand mappings

## Entry Points

**Main Processing:**
- Location: `/Users/nat/dev/election/ballot_ocr.py`
- Triggers: Direct script execution with image path argument
- Responsibilities: Complete ballot processing pipeline

**Google Drive Integration:**
- Location: `/Users/nat/dev/election/gdrivedl.py`
- Triggers: Script execution with Google Drive URL
- Responsibilities: Download ballot images from Drive

**Tesseract OCR:**
- Location: `/Users/nat/dev/election/tesseract_ocr.py`
- Triggers: Direct script execution with image path
- Responsibilities: Basic OCR extraction for testing

## Error Handling

**Strategy:** Multi-layer validation with graceful degradation

**Patterns:**
- OCR errors: Cross-validate numeric vs Thai text representations
- API failures: Cache ECT data locally and continue processing
- Authentication errors: Prompt for re-authentication with clear instructions
- Validation failures: Include discrepancy details in output

## Cross-Cutting Concerns

**Logging:** Basic print statements for debugging, minimal structured logging
**Validation:** Multiple layers - OCR accuracy, data consistency, ECT reference matching
**Authentication:** OAuth 2.0 flow for Google Drive access with token persistence
**Internationalization:** Thai language text processing throughout the pipeline

---

*Architecture analysis: 2024-02-16*
```