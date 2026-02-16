# Phase 2: ECT Integration & Matching

**Status:** PLANNING
**Created:** 2026-02-16

## Goal

Match extracted vote data against official ECT (Election Commission of Thailand) reference data and detect discrepancies.

## Context

### Current State
- Phase 1 complete with working OCR extraction
- ECT API integration exists in `ect_api.py`
- Provinces, parties, and constituencies already loaded from ECT
- Extraction includes province, constituency, and vote counts

### Existing ECT Integration
The `ect_api.py` module already provides:
- `ect_data.get_province(name)` - Get province by Thai name
- `ect_data.get_party(number)` - Get party by ballot number
- `ect_data.get_constituency(cons_id)` - Get constituency by ID
- `ect_data.validate_province_name(thai_name)` - Validate province name
- 77 provinces, 57 parties, 401 constituencies loaded

## Tasks

### 2.1. Candidate Data Integration
**Priority:** HIGH
**Effort:** Medium

Load candidate data from ECT API to enable matching.

**Implementation:**
- Research ECT API endpoints for candidate data
- Add candidate loading to `ect_api.py`
- Create Candidate dataclass with position, name, party

**Acceptance Criteria:**
- [ ] Candidate data loaded from ECT API
- [ ] Candidates indexed by province, constituency, position

---

### 2.2. Candidate Matching by Position
**Priority:** HIGH
**Effort:** Medium

Match extracted votes to ECT candidates.

**Implementation:**
- For constituency forms: match by province + constituency + position
- Lookup candidate name from ECT data
- Include candidate info in extraction results

**Acceptance Criteria:**
- [ ] Extracted votes matched to candidate names
- [ ] Candidate party affiliation included
- [ ] Missing candidates flagged

---

### 2.3. Party Matching Enhancement
**Priority:** HIGH
**Effort:** Low

Enhance party matching for party-list forms.

**Implementation:**
- Party numbers already extracted
- Add party name and abbreviation to results
- Validate party numbers are in range 1-57

**Acceptance Criteria:**
- [ ] Party names included in results
- [ ] Invalid party numbers flagged

---

### 2.4. Discrepancy Detection
**Priority:** HIGH
**Effort:** Medium

Compare extracted data with ECT official results.

**Implementation:**
- Fetch official results from ECT API
- Compare extracted votes vs official votes
- Calculate variance percentage
- Flag significant discrepancies (>5% variance)

**Acceptance Criteria:**
- [ ] Official results fetched for comparison
- [ ] Variance calculated for each candidate/party
- [ ] Discrepancies flagged with severity levels

---

### 2.5. Comparison Reports
**Priority:** MEDIUM
**Effort:** Medium

Generate human-readable comparison reports.

**Implementation:**
- Create report template
- Include extraction summary
- Show discrepancies with explanations
- Add confidence indicators

**Acceptance Criteria:**
- [ ] Report shows side-by-side comparison
- [ ] Discrepancies highlighted
- [ ] Report saved as markdown/text

---

## Success Criteria

- [ ] Extracted votes correctly matched to ECT candidates
- [ ] Discrepancies flagged with clear explanations
- [ ] API errors handled gracefully
- [ ] Comparison report generated

## Dependencies

- ECT API endpoints (partially implemented)
- Phase 1 extraction working
- OpenRouter API key for extraction

## Risks

1. **ECT API availability** - Official API may have rate limits or downtime
2. **Candidate data format** - May need transformation to match our schema
3. **Official results timing** - Results may not be available for all forms

## Notes

- ECT API base: `https://static-ectreport69.ect.go.th/data/data/`
- Start with candidate matching, then add discrepancy detection
- Consider caching ECT data to reduce API calls
