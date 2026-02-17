# Thai Election Ballot OCR

Automated ballot verification system for Thai elections using AI Vision OCR. Extracts vote counts from handwritten ballot images, validates against official Election Commission of Thailand (ECT) data, and detects discrepancies.

## Features

- **100% OCR accuracy** on test images with confidence scoring
- **Batch processing** with parallel execution and rate limiting
- **Web interface** for non-technical users
- **PDF reports** with charts and constituency summaries
- **ECT data validation** against 3,491 official candidates
- **Docker support** for easy deployment

## Quick Start

### Option 1: Docker (Recommended)

```bash
# Clone and configure
git clone https://github.com/yourusername/election.git
cd election

# Set environment variables
cp .env.example .env
# Edit .env with your API keys

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

# Install Tesseract OCR (required for PDF processing)
# macOS:
brew install tesseract tesseract-lang poppler

# Ubuntu/Debian:
sudo apt-get install tesseract-ocr tesseract-ocr-tha poppler-utils
```

### Run Web Interface

```bash
# Local only (default, secure)
python web_ui.py

# Allow external access (use with caution)
WEB_UI_HOST=0.0.0.0 python web_ui.py
```

Open http://localhost:7860 in your browser to:
- Upload ballot images
- Process in parallel with progress tracking
- View extracted vote counts
- Download PDF/JSON/CSV reports

### Command Line Usage

```bash
# Process a single ballot
python ballot_ocr.py --image path/to/ballot.jpg

# Batch processing
python batch_processor.py --input ./ballots/ --output ./results/ --parallel

# Download ballots from Google Drive
python download_ballots.py --province "กรุงเทพมหานคร" --output ./ballots/
```

## Project Structure

```
.
├── ballot_ocr.py        # Core OCR extraction and PDF generation
├── batch_processor.py   # Parallel batch processing with rate limiting
├── web_ui.py            # Gradio web interface
├── ect_api.py           # ECT data integration
├── metadata_parser.py   # Path-based metadata extraction
├── download_ballots.py  # Google Drive ballot downloader
├── province_folders.py  # Province folder URLs
├── tests/               # Test suite
│   ├── test_unit.py     # Unit tests
│   ├── test_accuracy.py # Accuracy tests
│   └── ground_truth.json
├── Dockerfile           # Docker image
├── docker-compose.yml   # Docker Compose config
└── Makefile            # Common tasks
```

## Common Tasks (Makefile)

```bash
make install     # Install dependencies
make test        # Run all tests
make lint        # Run linters
make run         # Start web UI (localhost)
make ci          # Run CI checks (lint + test)
make clean       # Remove generated files
```

## Ballot Form Types Supported

- **ส.ส. 5/16** - Early voting, constituency
- **ส.ส. 5/16 (บช)** - Early voting, party-list
- **ส.ส. 5/17** - Out-of-district, constituency
- **ส.ส. 5/17 (บช)** - Out-of-district, party-list
- **ส.ส. 5/18** - By unit, constituency
- **ส.ส. 5/18 (บช)** - By unit, party-list

## Configuration

Set environment variables for API access:

```bash
# Required: OpenRouter API (primary OCR)
export OPENROUTER_API_KEY="your-key-here"

# Optional: Anthropic Claude (fallback OCR)
export ANTHROPIC_API_KEY="your-key-here"

# Optional: Web UI configuration
export WEB_UI_HOST=127.0.0.1  # Default: localhost only
export WEB_UI_PORT=7860       # Default port
```

See `.env.example` for all configuration options.

## API Rate Limits

The system respects OpenRouter rate limits:
- 20 requests/minute
- 50 requests/day (free tier)

Parallel processing includes automatic retry with exponential backoff.

## Security

- **Default**: Web UI binds to localhost only (127.0.0.1)
- **File validation**: Max 10MB per file, 500 files per batch
- **Input sanitization**: All paths and filenames sanitized
- **API keys**: Never committed, loaded from environment

See [SECURITY.md](SECURITY.md) for full security policy.

## Reports Generated

- **Individual Ballot Report** - Vote counts with candidate matching
- **Constituency Summary** - Aggregated results with charts
- **Batch Summary** - Overview of all processed ballots
- **Executive Summary** - One-page overview with key statistics

## Development

### Setup

```bash
make dev  # Install deps + dev tools
```

### Run Tests

```bash
make test        # Run all tests
make test-accuracy  # Run accuracy tests (requires API keys)
```

### Pre-commit Hooks

```bash
pip install pre-commit
pre-commit install
```

### Project Phases

| Version | Phase | Description | Status |
|---------|-------|-------------|--------|
| v1.0 | 1-4 | OCR, ECT integration, aggregation, PDF | Complete |
| v1.1 | 5-8 | Parallel processing, web UI, metadata, executive summary | Complete |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

[MIT License](LICENSE)

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for version history.
