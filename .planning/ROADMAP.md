# Roadmap

## Overview

Thai Election Ballot OCR - A verification platform for extracting and validating vote counts from handwritten Thai ballot images.

---

## Phase 1: OCR Accuracy & Core Extraction

**Goal:** Achieve reliable extraction of vote counts from ballot images

### Tasks
1.1. Improve OCR prompt engineering for handwritten Thai numbers
1.2. Test and compare multiple AI models (Gemma 3, Claude Vision, others)
1.3. Implement confidence scoring for extractions
1.4. Fix party-list form extraction
1.5. Add batch processing capability
1.6. Create comprehensive test suite with ground truth data

### Success Criteria
- [ ] OCR accuracy >95% for handwritten vote counts
- [ ] Province extraction accuracy >99%
- [ ] Form type detection accuracy >99%
- [ ] All 6 form types correctly processed
- [ ] Sum validation passing for 90%+ of test images

### Estimated Effort
3-5 development sessions

---

## Phase 2: ECT Integration & Matching

**Goal:** Match extracted data against official ECT reference data

### Tasks
2.1. Enhance ECT API integration with error handling
2.2. Implement candidate matching by position
2.3. Implement party matching by number
2.4. Create discrepancy detection logic
2.5. Build comparison reports

### Success Criteria
- [ ] Extracted votes correctly matched to ECT candidates
- [ ] Discrepancies flagged with clear explanations
- [ ] API errors handled gracefully

### Estimated Effort
2-3 development sessions

---

## Phase 3: Reporting & Export

**Goal:** Provide useful output formats for analysis

### Tasks
3.1. Implement JSON export with full data
3.2. Implement CSV export for spreadsheet analysis
3.3. Create human-readable discrepancy reports
3.4. Add summary statistics

### Success Criteria
- [ ] JSON export matches specified schema
- [ ] CSV opens correctly in spreadsheet applications
- [ ] Reports highlight key discrepancies

### Estimated Effort
1-2 development sessions

---

## Phase 4: Polish & Documentation (Optional)

**Goal:** Production-ready system

### Tasks
4.1. Add comprehensive error handling
4.2. Write user documentation
4.3. Create example workflows
4.4. Performance optimization

### Success Criteria
- [ ] System runs without manual intervention
- [ ] Documentation covers all features
- [ ] Example data processing works end-to-end

### Estimated Effort
1-2 development sessions

---

## Current Status

**Active Phase:** None (initialization complete)

**Next Action:** Run `/gsd:plan-phase 1` to begin Phase 1 planning
