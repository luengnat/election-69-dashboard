# Requirements

## Phase 1: Core OCR Extraction

### Must Have
- [ ] **OCR Accuracy Improvement** - Achieve >95% accuracy for handwritten vote counts
- [ ] **Form Type Detection** - Reliably detect all 6 form types (ส.ส. 5/16, 5/17, 5/18 and their บช variants)
- [ ] **Province Extraction** - Extract province name with >99% accuracy
- [ **Vote Count Extraction** - Extract all vote counts from constituency forms
- [ ] **Party Vote Extraction** - Extract party votes from party-list forms (57 parties)
- [ ] **Validation** - Cross-validate numeric vs Thai text, sum validation

### Should Have
- [ ] **Multi-model Ensemble** - Use multiple AI models and compare results
- [ ] **Confidence Scoring** - Report confidence level for each extraction
- [ ] **Batch Processing** - Process multiple images/PDFs in one run

### Could Have
- [ ] **Web Interface** - Simple UI for uploading and processing forms
- [ ] **API Endpoint** - REST API for programmatic access

## Phase 2: ECT Integration

### Must Have
- [ ] **Candidate Matching** - Match extracted votes to ECT candidate data
- [ ] **Party Matching** - Match party votes to ECT party data
- [ ] **Discrepancy Reporting** - Flag differences between extracted and ECT data

### Should Have
- [ ] **Historical Comparison** - Compare with previous election results
- [ ] **Geographic Analysis** - Analyze results by province/district

## Phase 3: Reporting & Export

### Must Have
- [ ] **JSON Export** - Structured output format
- [ ] **CSV Export** - Spreadsheet-compatible output
- [ ] **Discrepancy Report** - Human-readable report of issues found

### Should Have
- [ ] **PDF Report** - Formatted report with charts
- [ ] **Dashboard** - Visual summary of processed forms

## Non-Functional Requirements

- **Performance**: Process a form in <5 seconds
- **Reliability**: Handle rate limiting gracefully with fallbacks
- **Maintainability**: Clear code structure with documentation
- **Extensibility**: Easy to add new form types or AI models
