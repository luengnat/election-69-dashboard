# Source Comparison Plan (ECT + Vote62 + killernay)

## 1) Canonical key
Use one canonical key everywhere:
- `province_th`
- `district_number` (constituency)
- `election_type`: `constituency` or `party_list`
- optional `unit_number` for unit-level checks

At district level, the key is `(province_th, district_number, election_type)`.

## 2) What each source is best for
- `ECT static`: official district aggregate (highest authority for district totals).
- `killernay`: OCR-derived district table; good independent cross-check.
- `Vote62`: unit-level station data; best for unit validation and bottom-up district aggregation.

## 3) Metrics to compute per key
- `coverage`: source has record for this key or not.
- `exact_match_valid`: extracted `valid_votes` == reference `valid_votes`.
- `delta_valid`: extracted - reference.
- `exact_match_invalid` and `delta_invalid` when available.
- `vote_vector_match` for candidate/party rows when available.

## 4) Trust policy
- District totals: trust order `ECT > Vote62-aggregated > killernay > Gemini summary`.
- Unit totals: trust order `Vote62 > human review > Gemini summary`.
- If `abs(delta_valid) > 0`, mark `needs_review`.
- If OCR text is weak and mismatch exists, auto-prioritize for retry.

## 5) Practical comparison pipeline
1. Normalize extracted records from Drive/Gemini into canonical keys.
2. Join with ECT by `(province, district, election_type)`.
3. Join with killernay by same key.
4. Build optional Vote62 district aggregates by summing units.
5. Output unified table with deltas + confidence flags.

## 6) Current quick result (B set)
From `official_manifest_part2B_vs_killernay_report.json`:
- Parsed comparable rows: `16`
- Exact matches: `14`
- Accuracy on comparable rows: `87.5%`
- Current mismatches: 2 rows (both party-list; one obvious extraction error)

