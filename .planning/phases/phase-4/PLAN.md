# Phase 4: PDF Export Implementation

**Objective:** Convert markdown reports to professional PDF format for easy sharing and archival

**Status:** PLANNING

## Tasks

### 4.1: PDF Generation Engine
- Create PDF template system using reportlab
- Convert markdown tables to PDF tables
- Preserve formatting, colors, and structure
- Support both single-page and multi-page reports

### 4.2: Single Ballot PDF Reports
- Convert individual ballot markdown reports to PDF
- Include metadata (generation date, source file, confidence level)
- Add watermark or header with form type

### 4.3: Batch Summary PDF
- Multi-page PDF with ballot summaries
- Index/table of contents
- Statistics and charts
- Province breakdown

### 4.4: Constituency Report PDF
- Detailed results with winner information
- Vote distribution table
- Historical comparison placeholder
- Quality metrics

### 4.5: Executive Summary PDF
- High-level overview with key metrics
- Anomaly findings with highlighting
- Recommendations
- Appendix with methodology

## Implementation Plan

1. Add `reportlab` dependency
2. Create `PDFGenerator` class with:
   - `generate_ballot_pdf(ballot_data, report_md)`
   - `generate_batch_pdf(aggregated_results, reports_md_list)`
   - `generate_constituency_pdf(constituency_report_md)`
   - `generate_executive_pdf(executive_summary_md)`
3. Integrate with existing report functions
4. Add `--pdf` flag to command-line interface
5. Test PDF generation with mock data

## Files to Modify
- `ballot_ocr.py` - Add PDF generation functions
- `main()` - Add `--pdf` argument handling

## Testing
- Generate PDFs from mock data
- Verify table formatting
- Check multi-page layouts
- Validate PDF file size and structure

## Success Criteria
✓ All report types exportable to PDF
✓ Formatting preserved from markdown
✓ Files generate in < 2 seconds for single ballot
✓ Professional appearance suitable for official reports
