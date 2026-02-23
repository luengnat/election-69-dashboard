# Data Contracts

## Primary Row Contract (`district_dashboard_data.json`)

Path:
- `docs/data/district_dashboard_data.json`

Top-level:
- `items`: array of row objects (typically 800 rows = 400 districts x 2 form types)

Per-row required identity fields:
- `province`
- `district_number`
- `form_type` (`constituency` or `party_list`)
- `district_key`
- `district_form_key`

Read/extracted totals:
- `valid_votes_extracted`
- `invalid_votes`
- `blank_votes`
- `votes` (object keyed by candidate/party number)

Source comparison section:
- `sources.ect`
- `sources.vote62`
- `sources.killernay`
- each source may include `valid_votes`, `invalid_votes`, `blank_votes`, `votes`

## Consistency Rules

### Rule A: Vote Sum Consistency
If `votes` is present and numeric:
- `sum(votes) == valid_votes_extracted` (expected)

### Rule B: Total Ballot Consistency
If all three values exist:
- `total_used = valid_votes_extracted + invalid_votes + blank_votes`

### Rule C: District Pair Completeness
Expected two rows per district:
- one `constituency`
- one `party_list`

### Rule D: Winner Labeling
- `constituency`: show `candidate_number + candidate_name (+party)`
- `party_list`: show party name (not raw number-only label in final UI)

## Poll Station Aggregate Contract

Path:
- `docs/data/poll_station_agg.json`

Top-level:
- `items`: array keyed by district

Per-row fields:
- `province`
- `district_number`
- `district_key`
- `poll_station_count`
- `eligible_total`
- `registered_outside_district`
- `registered_outside_country`
- `registered_outside_total`

## Section 3 Aggregate Contract

Path:
- `docs/data/killernay_section3_agg.json`

Per-row fields:
- `province`
- `district_number`
- `form_type`
- `district_key`
- `district_form_key`
- `votes_in_station_3_1`
- `advance_in_district_3_2`
- `outside_and_overseas_3_3`
- `total_used_3_4`
- `eligible_1_1`
- `came_1_2`

## Export Contract (for external comparison sheets)

Recommended export columns:
- identity: `province`, `district_number`, `form_type`
- read totals: `total_100_read`, `valid_100_read`, `invalid_100_read`, `blank_100_read`
- quality: `sum_votes_100_read`, `sum_minus_valid`
- references: `ect_valid_94`, `killernay_valid`, `drive_id`, `drive_url`
