# Phase 1: OCR Accuracy & Core Extraction

**Status:** PLANNING
**Created:** 2026-02-16

## Goal

Achieve reliable extraction of vote counts from handwritten Thai ballot images with >95% accuracy.

## Context

### Current State
- Working OCR extraction with OpenRouter (Gemma 3 12B IT) and Claude Vision fallback
- ECT API integration for validation
- Detailed prompts for constituency and party-list forms
- Test images available

### Known Issues
1. AI Vision models give inconsistent results for same image
2. OpenRouter free tier has rate limiting
3. Party-list form extraction not fully tested
4. Handwritten number recognition accuracy varies

## Tasks

### 1.1. Test Suite with Ground Truth
**Priority:** HIGH
**Effort:** Medium

Create test cases with known correct values to measure accuracy.

**Implementation:**
- Create `tests/ground_truth.json` with expected values for test images
- Add accuracy measurement script
- Track precision/recall metrics

**Acceptance Criteria:**
- [ ] Ground truth file created for all test images
- [ ] Accuracy script reports metrics per image

---

### 1.2. Multi-Model Ensemble
**Priority:** HIGH
**Effort:** Medium

Use multiple AI models and compare results to improve accuracy.

**Implementation:**
- Add support for additional OpenRouter models
- Implement result comparison logic
- Flag discrepancies between models

**Acceptance Criteria:**
- [ ] At least 2 models can be used
- [ ] Results compared and discrepancies logged

---

### 1.3. Fix Party-List Extraction
**Priority:** HIGH
**Effort:** Low

Ensure party-list forms extract all 57 parties correctly.

**Implementation:**
- Test combined prompt on party-list images
- Verify party_votes dictionary populated correctly
- Handle multi-page party-list forms

**Acceptance Criteria:**
- [ ] Party-list form extraction works
- [ ] party_votes contains all visible parties

---

### 1.4. Confidence Scoring
**Priority:** MEDIUM
**Effort:** Medium

Add confidence scores to extraction results.

**Implementation:**
- Check if numeric matches Thai text (high confidence)
- Check if sum validation passes (medium confidence)
- Flag low-confidence extractions

**Acceptance Criteria:**
- [ ] Each extraction has confidence level
- [ ] Low-confidence results flagged

---

### 1.5. Batch Processing
**Priority:** MEDIUM
**Effort:** Low

Process multiple images in one run.

**Implementation:**
- Accept directory as input
- Process all images sequentially
- Aggregate results in single output

**Acceptance Criteria:**
- [ ] Can process directory of images
- [ ] Single output file with all results

---

## Success Criteria

- [ ] OCR accuracy >95% for handwritten vote counts
- [ ] Province extraction accuracy >99%
- [ ] Form type detection accuracy >99%
- [ ] All 6 form types correctly processed
- [ ] Sum validation passing for 90%+ of test images

## Dependencies

- OpenRouter API key (provided)
- Anthropic API key (for Claude Vision fallback)
- Test images in test_images/

## Risks

1. **Rate limiting** - OpenRouter free tier limits may slow testing
2. **Model inconsistency** - Different models may give different results
3. **Image quality** - Poor quality images may affect accuracy

## Notes

- Start with constituency forms (simpler)
- Use high_res_page-1.png as primary test image
- Ground truth: province=แพร่, form=ส.ส. 5/16
