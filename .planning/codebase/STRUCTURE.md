# Codebase Structure

**Analysis Date:** 2024-02-16

## Directory Layout

```
/Users/nat/dev/election/
├── ballot_ocr.py         # Main ballot processing script
├── ect_api.py           # ECT API client for validation
├── gdrivedl.py          # Google Drive downloader
├── drive_auth.py        # Google Drive OAuth authentication
├── tesseract_ocr.py     # Tesseract OCR utilities
├── FORM_CATEGORIZATION.md  # Documented form types
├── data/               # Raw ballot data storage
│   └── phrae/          # Province-level data
│       └── เขตเลือกตั้งที่ 1 จังหวัดแพร่/  # District-level data
├── test_images/        # Sample ballot images for testing
└── test_result*.json   # Processing output files
```

## Directory Purposes

**Root Level:**
- Purpose: Contains all scripts and documentation
- Contains: Python processing modules, markdown documentation, test results
- Key files: `ballot_ocr.py` (main entry), `ect_api.py` (validation)

**data/**:
- Purpose: Stores downloaded ballot PDFs and raw data
- Contains: Province and district organized folders with Thai names
- Key files: Thai-named directories with ballot form PDFs

**test_images/**:
- Purpose: Sample PNG images for development and testing
- Contains: High-resolution and standard resolution ballot images
- Key files: `high_res_page-1.png`, `bch_page-1.png` through `bch_page-4.png`

## Key File Locations

**Entry Points:**
- `/Users/nat/dev/election/ballot_ocr.py`: Main ballot processing pipeline
- `/Users/nat/dev/election/tesseract_ocr.py`: Basic OCR testing utility
- `/Users/nat/dev/election/gdrivedl.py`: Google Drive image downloader

**Configuration:**
- `/Users/nat/dev/election/FORM_CATEGORIZATION.md`: Documented form types and categorization
- `/Users/nat/dev/election/data/`: Directory structure for raw data organization

**Core Logic:**
- `/Users/nat/dev/election/ballot_ocr.py`: Complete OCR pipeline with validation
- `/Users/nat/dev/election/ect_api.py`: External API integration for validation

**Testing:**
- `/Users/nat/dev/election/test_images/`: Sample images for development
- `test_result*.json`: Output files from processing runs

## Naming Conventions

**Files:**
- `snake_case.py` for Python scripts
- `kebab-case.md` for documentation
- `test_result_<version>.json` for experimental outputs

**Functions:**
- `snake_case` for function names
- Mixed case for classes (FormType, Province, Party)

**Variables:**
- `snake_case` for local variables
- `ALL_CAPS` for constants and mappings (THAI_DIGITS, ECT_BASE_URL)

**Directories:**
- Thai names for actual ballot data (เขตเลือกตั้งที่ 1 จังหวัดแพร่)
- English names for development folders (test_images, data)

## Where to Add New Code

**New Form Type Support:**
- Primary code: `/Users/nat/dev/election/ballot_ocr.py` (update FormType enum and extraction logic)
- Tests: Add to test_images/ and create new test_result JSON

**New Validation Rules:**
- Primary code: `/Users/nat/dev/election/ballot_ocr.py` (add validation methods)
- Documentation: Update FORM_CATEGORIZATION.md if needed

**New External Data Sources:**
- Primary code: `/Users/nat/dev/election/ect_api.py` (extend for additional APIs)
- Configuration: Add constants and endpoints at module level

**New OCR Techniques:**
- Primary code: `/Users/nat/dev/election/ballot_ocr.py` or create new module
- Testing: Add to test_images/ with known expected outputs

**Utilities:**
- Shared helpers: Create at root level for standalone functionality
- Image processing: Could extend `tesseract_ocr.py` or create new module

## Special Directories

**data/เขตเลือกตั้งที่ 1 จังหวัดแพร่/**:
- Purpose: Stores actual ballot form PDFs from ECT
- Generated: Yes (downloaded from Google Drive)
- Committed: No (listed in .gitignore via .DS_Store entries)

**test_images/**:
- Purpose: Development and testing sample images
- Generated: No (manually curated)
- Committed: Yes (small sample set)

---

*Structure analysis: 2024-02-16*
```