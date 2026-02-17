# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2026-02-17

### Added
- **Parallel Processing**: ThreadPoolExecutor with rate limiting (2 req/sec), tenacity retry logic, memory cleanup for large batches
- **Web Interface**: Gradio-based UI with real-time progress tracking, bilingual (Thai/English) labels
- **Metadata Inference**: PathMetadataParser with NFC normalization, ECT province validation, OCR fallback
- **Executive Summary**: One-page PDF with top 5 parties chart, color-coded discrepancy summary
- PDF/JSON/CSV export from web UI
- Progress callbacks for batch processing
- `.gitignore` for generated files

### Security
- Input validation for file uploads (type, size limits)
- Batch size limit (500 files max)
- Sanitized filenames for safe path handling
- Web UI defaults to localhost (127.0.0.1)
- API timeout (60s) to prevent hanging
- Subprocess input validation

### Changed
- Updated requirements.txt with all dependencies
- Improved error handling with structured errors

### Fixed
- NameError when reportlab `inch` used in function default parameter

## [1.0.0] - 2026-02-16

### Added
- **OCR Extraction**: 100% accuracy on test images with confidence scoring
- **ECT Integration**: 3,491 candidates from official API, vote matching, discrepancy detection
- **Aggregation Engine**: Statistical analysis with IQR-based outlier detection
- **PDF Export**: Charts, constituency reports, batch summaries
- Batch processing capabilities
- Candidate matching against ECT database
- Discrepancy detection with severity-based warnings
- Thai numeral and text parsing
- Form type detection (ส.ส. 5/16, 5/17, 5/18 with variants)

### Supported Form Types
- ส.ส. 5/16 - Early voting, constituency
- ส.ส. 5/16 (บช) - Early voting, party-list
- ส.ส. 5/17 - Out-of-district, constituency
- ส.ส. 5/17 (บช) - Out-of-district, party-list
- ส.ส. 5/18 - By unit, constituency
- ส.ส. 5/18 (บช) - By unit, party-list

[1.1.0]: https://github.com/.../compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/.../releases/tag/v1.0.0
