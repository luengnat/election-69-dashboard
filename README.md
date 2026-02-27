# Thai Election Ballot OCR

Automated ballot verification system for Thai elections using AI Vision OCR. Extracts vote counts from handwritten ballot images, validates against official Election Commission of Thailand (ECT) data, and detects discrepancies.

## Features

- **High-Accuracy OCR**:
  - **Adaptive Preprocessing**: Automatically handles noisy/skewed images.
  - **Advanced Vision**: Deskewing and line removal for structural correction.
  - **Ensemble Support**: Tesseract, PaddleOCR, TrOCR, Claude, and OpenRouter.
- **Performance**:
  - **Result Caching**: SQLite-based caching for instant re-runs.
  - **Parallel Processing**: Thread-pooled execution with rate limiting.
- **Web Interface**:
  - **Review Queue**: Manual verification for low-confidence results.
  - **Bulk Operations**: ZIP file upload and processing.
  - **Secure**: Basic authentication support.
- **Verification**:
  - **ECT Integration**: Validates against 3,491 official candidates.
  - **Logic Checks**: Sum validation and anomaly detection.
- **Reporting**:
  - **PDF Exports**: Executive summary, constituency reports, and batch summaries.
  - **Data Exports**: JSON and CSV formats.

## Quick Start

### Option 1: Docker (Recommended)

```bash
# Clone and configure
git clone https://github.com/yourusername/election.git
cd election

# Set environment variables
cp .env.example .env
# Edit .env with your API keys (optional for local OCR)

# Run with Docker Compose
docker-compose up -d

# Open http://localhost:7860
```

### Option 2: Native Installation

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install Tesseract OCR (required fallback)
# macOS:
brew install tesseract tesseract-lang poppler
# Ubuntu/Debian:
sudo apt-get install tesseract-ocr tesseract-ocr-tha poppler-utils libgl1
```

## Usage

### Web Interface

```bash
# Run locally
python web_ui.py

# With authentication
WEB_UI_USERNAME=admin WEB_UI_PASSWORD=secret python web_ui.py
```

Open http://localhost:7860. You can:
1.  **Upload**: Select images or ZIP files (up to 500/batch).
2.  **Process**: Watch real-time progress.
3.  **Review**: Verify low-confidence results in the "Review" tab.
4.  **Export**: Download PDF reports or raw data.

### Command Line

```bash
# Process a directory (using installed CLI)
ballot-ocr process ballots/ --parallel --output results.json

# Or using Python module
python -m ballot_ocr.cli process ballots/ --parallel

# Legacy entry point (still works)
python main.py ballots/ --parallel --output results.json

# Process with specific options
python main.py ballots/ --no-cache --verify --reports

# Download ballots from Google Drive
python scripts/drive/download_ballots.py --province "กรุงเทพมหานคร" --output ./ballots/
```

### As a Python Package

```python
# Modern import (recommended)
from ballot_ocr import BallotData, extract_ballot_data_with_ai, config

# Extract ballot data from an image
result = extract_ballot_data_with_ai("ballot.jpg")
print(f"Form: {result.form_type}, Total votes: {result.total_votes}")

# Backward compatible imports (still work)
from ballot_types import BallotData, FormType
from config import config
```

### Google Drive Folder Browsing (CDP)

For programmatic folder-level browsing in an authenticated Chrome session, and extracting file-level Gemini context without OCR, use:

- `/Users/nat/dev/election/drive_cdp_browser.py`
- Mapping helper: `/Users/nat/dev/election/drive_mapping.py`
- Handoff guide: `/Users/nat/dev/election/docs/DRIVE_CDP_WORKFLOW.md`

## Current State

For the latest operational snapshot (dashboard behavior, validation status, known caveats, and re-validation commands), see:

- `docs/CURRENT_STATE.md`

## Documentation Map

Use these docs as the project handoff backbone:

- `docs/PROJECT_OVERVIEW.md` - what the system does and major workflows
- `docs/DATA_CONTRACTS.md` - canonical data model and consistency rules
- `docs/OPERATIONS_RUNBOOK.md` - run/validate/publish operational steps
- `docs/REPO_CLEANUP_PLAN.md` - repository cleanup direction and conventions

## Project Structure

```
election/
├── src/ballot_ocr/          # Python package (installable)
│   ├── core/                # Types and configuration
│   ├── cli/                 # Command-line interface
│   └── __init__.py          # Public API exports
├── scripts/                 # Standalone scripts
│   ├── analysis/            # Analysis and audit scripts
│   ├── conversion/          # Data conversion scripts
│   └── drive/               # Google Drive utilities
├── tests/                   # Test suite
├── docs/                    # Documentation
├── data/                    # Persistent data files
├── archive/                 # Archived processing artifacts
│   └── json_data/           # Historical JSON outputs
├── main.py                  # Main entry point (legacy)
├── web_ui.py               # Gradio web interface
├── cli.py                   # CLI shim (backward compat)
└── ballot_*.py             # Core modules (backward compat shims)
```

## Configuration

Set these environment variables in `.env`:

```bash
# OCR Backends (comma-separated, priority order)
EXTRACTION_BACKENDS="ollama,openrouter,anthropic,tesseract,paddle"

# Local Ollama (for custom local vision OCR)
OLLAMA_BASE_URL="http://127.0.0.1:11434"
OLLAMA_MODEL="minicpm-v:latest"
# Optional runtime tuning (useful on macOS if Metal crashes)
# OLLAMA_NUM_GPU="0"       # force CPU
# OLLAMA_NUM_THREAD="8"

# API Keys (if using cloud backends)
OPENROUTER_API_KEY="your-key"
ANTHROPIC_API_KEY="your-key"

# Web UI Security
WEB_UI_USERNAME="admin"
WEB_UI_PASSWORD="password"

# Processing
MAX_WORKERS=5
RATE_LIMIT=2.0
```

## Benchmarks

Accuracy on test dataset (clean scans):

| Backend Strategy | Ballot Accuracy | Field Accuracy | Notes |
|------------------|-----------------|----------------|-------|
| Tesseract Only | 100% | 100% | Baseline with adaptive preprocessing |
| Weighted Ensemble | 100% | 100% | Falls back gracefully if advanced models missing |

*Note: PaddleOCR backend is recommended for complex table layouts and provides the highest robustness against rotation and grid lines when installed.*

## Advanced Features

### Adaptive Preprocessing
The system analyzes each image (resolution, contrast, noise) and applies optimal filters:
- **Deskewing**: Corrects rotation using projection profiles.
- **Line Removal**: Removes table grids to isolate handwriting.
- **Padding**: Adds borders to prevent text cutoff.

### Caching
Results are cached in `.serena/cache/ocr_results.db`. To force reprocessing:
- **CLI**: Use `--no-cache`.
- **Web UI**: Check "Force Reprocess".

### PaddleOCR (Optional)
For higher accuracy on local machines, install PaddleOCR:
```bash
pip install paddlepaddle paddleocr
```
Then verify it's active in the startup logs.

## Project Structure

```
.
├── ballot_ocr.py        # CLI entry point
├── batch_processor.py   # Parallel processing engine
├── web_ui.py            # Gradio interface
├── ballot_extraction.py # Main OCR logic
├── adaptive_ocr.py      # Image preprocessing & analysis
├── model_backends.py    # OCR engine wrappers (Tesseract, Paddle, etc.)
├── ocr_cache.py         # SQLite result cache
├── crop_utils.py        # Zone-based cropping templates
├── ect_api.py           # Election Commission data integration
└── ...
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

[MIT License](LICENSE)
