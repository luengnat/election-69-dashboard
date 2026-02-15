# Phase 3: Results Aggregation & Analysis

**Status:** PLANNING
**Created:** 2026-02-16

## Goal

Combine extracted ballot data from multiple polling stations into meaningful aggregate results and provide statistical analysis at the constituency and province level.

## Context

### Current State
- Phase 2 complete with full ballot verification and reporting
- Each ballot is verified individually
- Single and batch reports generated for raw results
- No aggregation across multiple polling stations yet

### What We Have
- Individual ballot data with candidate/party matching
- Discrepancy detection at ballot level
- Confidence scoring for each extraction
- Access to 401 constituencies and voting data

## Problem Solved by Phase 3

Currently:
- ✓ Can extract and verify individual ballots
- ✗ Cannot combine results from multiple polling stations
- ✗ No constituency-level totals
- ✗ Cannot identify trends or anomalies across ballots
- ✗ No statistical analysis of aggregated results

## Tasks

### 3.1. Aggregation Engine
**Priority:** HIGH
**Effort:** High

Build system to combine votes from multiple ballots.

**Implementation:**
- Create `AggregatedResults` dataclass for constituency totals
- Group ballots by province + constituency
- Sum votes across all polling stations for each candidate/party
- Track number of polling stations/units that reported
- Calculate aggregated confidence scores

**Acceptance Criteria:**
- [ ] Group ballots by constituency
- [ ] Sum candidate/party votes correctly
- [ ] Handle multi-page party-list forms correctly
- [ ] Track polling station counts
- [ ] Calculate combined confidence metric

---

### 3.2. Constituency-Level Results
**Priority:** HIGH
**Effort:** Medium

Generate constituency summary with final vote totals.

**Implementation:**
- For each constituency: total votes by candidate/party
- Determine winners (highest votes per position)
- Calculate vote percentages and margins
- Include voting turnout metrics
- Compare against ECT expectations if available

**Acceptance Criteria:**
- [ ] Constituency totals accurate
- [ ] Winners identified correctly
- [ ] Vote percentages calculated
- [ ] Turnout metrics included
- [ ] Results verified against input sum

---

### 3.3. Discrepancy Aggregation
**Priority:** HIGH
**Effort:** Medium

Analyze discrepancies across aggregated results.

**Implementation:**
- Calculate aggregate discrepancy rate per constituency
- Identify problematic candidates (high variance)
- Flag constituencies with excessive discrepancies
- Generate discrepancy summary by type
- Recommend re-verification for high-discrepancy areas

**Acceptance Criteria:**
- [ ] Aggregate discrepancy rates calculated
- [ ] Problem areas identified
- [ ] Severity levels assigned to constituencies
- [ ] Recommendations for review generated

---

### 3.4. Statistical Analysis
**Priority:** MEDIUM
**Effort:** High

Analyze patterns and anomalies in aggregated results.

**Implementation:**
- Calculate vote distribution statistics per candidate
- Identify outlier polling stations
- Detect unusual patterns (e.g., all votes for one candidate)
- Compare against expected distributions
- Flag anomalies for investigation

**Acceptance Criteria:**
- [ ] Basic statistics calculated (mean, median, std dev)
- [ ] Outliers identified using statistical methods
- [ ] Anomaly detection working
- [ ] Pattern analysis working
- [ ] Results actionable

---

### 3.5. Aggregate Reports
**Priority:** MEDIUM
**Effort:** Medium

Generate comprehensive reports for aggregated results.

**Implementation:**
- Constituency-level report template
- Province-level summary report
- Regional analysis (if applicable)
- Charts and visualizations in markdown
- Executive summary with key findings

**Acceptance Criteria:**
- [ ] Constituency reports generated
- [ ] Province summary reports created
- [ ] Key statistics highlighted
- [ ] Anomalies noted
- [ ] Reports saved successfully

---

## Success Criteria

- [ ] Multiple ballots aggregated correctly by constituency
- [ ] Final vote totals accurate and verified
- [ ] Discrepancies analyzed at aggregate level
- [ ] Statistical analysis identifies patterns
- [ ] Comprehensive reports generated
- [ ] 98%+ accuracy on aggregation (verified against manual totals)

## Dependencies

- Phase 2 complete (ballot-level verification)
- Individual ballot JSON results
- ECT API access for validation

## Data Structures

### AggregatedResults (new)
```python
@dataclass
class AggregatedResults:
    province: str
    constituency: str
    constituency_no: int
    
    # Vote aggregation
    candidate_totals: dict[int, int]  # position -> total votes
    party_totals: dict[int, int]      # party # -> total votes
    
    # Polling information
    polling_units_reporting: int
    total_polling_units: int
    valid_votes_total: int
    invalid_votes_total: int
    blank_votes_total: int
    overall_total: int
    
    # Quality metrics
    aggregated_confidence: float
    ballots_processed: int
    ballots_with_discrepancies: int
    
    # Analysis
    winners: list[dict]  # top candidates/parties
    turnout_rate: float
    discrepancy_rate: float
```

## Timeline Estimate

- 3.1 Aggregation: 4-6 hours (core logic complex)
- 3.2 Constituency Results: 2-3 hours (straightforward)
- 3.3 Discrepancy Analysis: 2-3 hours (building on existing)
- 3.4 Statistical Analysis: 4-6 hours (statistical methods)
- 3.5 Reports: 2-3 hours (templating)

**Total:** ~16-21 hours of development

## Risks

1. **Data Integrity** - Aggregating from multiple sources must be 100% accurate
2. **Edge Cases** - Handling partial data (incomplete polling stations)
3. **Performance** - Aggregating thousands of ballots may be slow
4. **Statistical Validity** - Small sample sizes may skew analysis

## Notes

- Ensure all aggregations are verifiable (can trace back to source ballots)
- Consider caching aggregation results for performance
- Implement extensive validation of aggregated totals
- Statistical analysis should be conservative (avoid false positives)
- Reports should clearly indicate confidence levels
