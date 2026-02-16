# Thai Election Ballot OCR

Automated ballot verification system for Thai elections using AI Vision OCR. Extracts vote counts from handwritten ballot images, validates against official Election Commission of Thailand (ECT) data, and detects discrepancies.

## Features

- **100% OCR accuracy** on test images with confidence scoring
- **Batch processing** with parallel execution and rate limiting
- **Web interface** for non-technical users
- **PDF reports** with charts and constituency summaries
- **ECT data validation** against 3,491 official candidates

## Quick Start

### Installation

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install Tesseract OCR (required for image processing)
# macOS:
brew install tesseract tesseract-lang

# Ubuntu/Debian:
sudo apt-get install tesseract-ocr tesseract-ocr-tha
```

### Run Web Interface

```bash
python web_ui.py
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
└── tests/               # Test suite
    ├── test_accuracy.py
    └── ground_truth.json
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
# OpenRouter API (primary OCR)
export OPENROUTER_API_KEY="your-key-here"

# Anthropic Claude (fallback OCR)
export ANTHROPIC_API_KEY="your-key-here"
```

## API Rate Limits

The system respects OpenRouter rate limits:
- 20 requests/minute
- 50 requests/day (free tier)

Parallel processing includes automatic retry with exponential backoff.

## Reports Generated

- **Individual Ballot Report** - Vote counts with candidate matching
- **Constituency Summary** - Aggregated results with charts
- **Batch Summary** - Overview of all processed ballots
- **Executive Summary** - One-page overview with key statistics

## Development

### Run Tests

```bash
# Accuracy tests
python tests/test_accuracy.py --all

# PDF generation tests
python test_pdf_generation.py

# Executive summary tests
python test_executive_summary_pdf.py
```

### Project Phases

| Version | Phase | Description | Status |
|---------|-------|-------------|--------|
| v1.0 | 1-4 | OCR, ECT integration, aggregation, PDF | Complete |
| v1.1 | 5-8 | Parallel processing, web UI, metadata, executive summary | Complete |

## License

MIT License
