# Technology Stack

**Analysis Date:** 2026-02-16

## Languages

**Primary:**
- Python 3.14.2 - Core language for OCR processing, Thai text handling, and API integration
- Used in: `ballot_ocr.py`, `ect_api.py`, `gdrivedl.py`, `tesseract_ocr.py`, `drive_auth.py`

**Secondary:**
- Shell scripting - For file operations and image processing workflows
- JSON - For configuration and data exchange

## Runtime

**Environment:**
- Python 3.14.2 - Runtime environment
- Virtual environment: `venv/` - Isolated dependency management

**Package Manager:**
- pip - Package management (v25.3)
- Lockfile: Requirements.txt not present, dependencies in venv/

## Frameworks

**Core:**
- Standard library - Built-in Python modules (json, os, sys, dataclasses, enum)
- Custom framework - Homegrown OCR solution for Thai ballot processing

**OCR Processing:**
- Tesseract OCR v0.3.13 - Optical character recognition for ballot images
- PIL (Pillow) v12.1.1 - Image manipulation and processing
- Language: Thai + English (`tha+eng`) for multilingual ballot text

**OCR Variants:**
- Custom Thai number parsing (`ballot_ocr.py` lines 66-89) - Handles handwritten Thai numerals
- Tesseract fallback (`tesseract_ocr.py`) - Alternative OCR implementation

## Key Dependencies

**Critical:**
- pytesseract v0.3.13 - Tesseract OCR Python wrapper for image text extraction
- google-api-python-client v2.190.0 - Google Drive API integration
- gdown v5.2.1 - Google Drive file download utility
- requests v2.32.5 - HTTP requests for ECT API data fetching
- httpx v0.28.1 - Alternative HTTP client with async support

**Infrastructure:**
- BeautifulSoup4 v4.14.3 - HTML parsing for Google Drive web scraping
- google-auth v2.48.0 - Authentication framework for Google APIs
- oauthlib v3.3.1 - OAuth protocol implementation
- PyYAML (not present) - Not used, configuration handled via code

**OCR/Visual:**
- pdf2image v1.17.0 - PDF to image conversion (commented code)
- OpenCV (not found) - Computer vision library, not installed

## Configuration

**Environment:**
- Python path: Explicit virtual environment activation required
- Credentials: `~/.claude/.google/client_secret.json` - Google OAuth credentials
- Token storage: `~/.claude/.google/token.pickle` - OAuth token persistence

**Build:**
- No build configuration files present
- Direct script execution: `python ballot_ocr.py`

## Platform Requirements

**Development:**
- macOS (Darwin 24.6.0)
- Python 3.14.2 with virtual environment
- Internet connection for API access

**Production:**
- Same as development (no containerization)
- Google OAuth credentials setup
- Tesseract installation with Thai language data

---

*Stack analysis: 2026-02-16*
```