# Unit-Level Focus: 15 Districts

Last updated: 2026-02-22

## Summary

Current status for all 15 target districts is:

- `unit_level_status = pending-no-unit-level-rows-in-dashboard-data`

Meaning:

- District-level totals exist and are being tracked.
- Unit-level (`หน่วย`) rows are not yet integrated into dashboard data.

## Target List (with source file links)

| Province | District | Hint | Constituency File | Party-list File |
|---|---:|---:|---|---|
| เชียงใหม่ | 1 | 68.83% | [open](https://drive.google.com/file/d/1NfltwwsfkpUzTIus-V2VMhCpOtuNiCQg/view) | [open](https://drive.google.com/file/d/1YBTUUvGdAbBV0Nq4mwyvWrabD6be7uYe/view) |
| สมุทรปราการ | 4 | 66.86% | [open](https://drive.google.com/file/d/163vUrbLbBeG5Mqw8VJLMAR5GiW4tyvbG/view) | [open](https://drive.google.com/file/d/1jNUBveZJQy_YulqGCYEKylCnEOrnVazl/view) |
| สุโขทัย | 2 | 64.82% | [open](https://drive.google.com/file/d/1Ixhj1lsXlNi7jIb7jHsDbRy7ckjiQ0p-/view) | [open](https://drive.google.com/file/d/1iFTKazTPrIDzlIjZjADZpVMri6xxpg0K/view) |
| มหาสารคาม | 1 | 64.81% | [open](https://drive.google.com/file/d/1IO2mowaFL3d6-WQaaQwpNDIx1pQujQQQ/view) | [open](https://drive.google.com/file/d/1iIVxHpNhMJITJYTfyIyOLvF_WU2o33AF/view) |
| ระยอง | 1 | 64.00% | [open](https://drive.google.com/file/d/1egHzkfNT5KM524XgS80PCqOzfamz6_3g/view) | [open](https://drive.google.com/file/d/1RxBl92eWFsLYeYnuNys7UwGRub9ODkE3/view) |
| เชียงราย | 6 | 53.75% | [open](https://drive.google.com/file/d/1eYovEvqkmUziQeMYO3Ce370rkRbnK1ck/view) | [open](https://drive.google.com/file/d/1JRMFDXP32gdC5_vUSbC12xESm6NkclUt/view) |
| สกลนคร | 1 | 51.50% | [open](https://drive.google.com/file/d/1mafFv4NdqwuM4gsqnHBcrYXgi438Fiak/view) | [open](https://drive.google.com/file/d/1kIm0liXTa7mJ1XM8TzzFkPE7mYqvtBqX/view) |
| ขอนแก่น | 2 | 47.43% | [open](https://drive.google.com/file/d/1o7M5eV-xVDybAPMEGW8zB2fNpetFFjEj/view) | [open](https://drive.google.com/file/d/1pbqyfJc3osHAzdyz40u7ORu-ck8aPzJe/view) |
| สงขลา | 2 | 47.42% | [open](https://drive.google.com/file/d/1Nh8zcREMw2k0XXfgUaPdavBZt0wlGXuu/view) | [open](https://drive.google.com/file/d/1r95PtNsL8GoURxEzyjRLM75O19CDovW9/view) |
| นครราชสีมา | 2 | 47.42% | [open](https://drive.google.com/file/d/1ec3vCReFnYuwI7VXcn4CMfRmA9DNKSbC/view) | [open](https://drive.google.com/file/d/1gWjLeskpwPHfxYgpkfOxDr-DTymNtGxR/view) |
| นราธิวาส | 3 | 43.35% | [open](https://drive.google.com/file/d/19SEQ3JlF1d9-5azJeDhp09KnWrKG-c90/view) | [open](https://drive.google.com/file/d/1Fft1UDsEkrl-QwQiKSjE4OfMc04ONMrp/view) |
| นครราชสีมา | 1 | 39.41% | [open](https://drive.google.com/file/d/15ZGFtRWsjCMd5zInmWlMBH6irip22Cpj/view) | [open](https://drive.google.com/file/d/1N194FsykU8B2aO3OQlxq1SPyQd_ISMfi/view) |
| อุดรธานี | 1 | 28.18% | [open](https://drive.google.com/file/d/1p3E2sb1lKmg-YI-pUNsb7fZcpoPVu327/view) | [open](https://drive.google.com/file/d/19QW8kw-c0-FGTJEDGWGcVZ8oneek1Wu4/view) |
| ราชบุรี | 4 | 27.67% | [open](https://drive.google.com/file/d/1DtCvEB76l9hvEVVfNJms6UrhCTwE5bp6/view) | [open](https://drive.google.com/file/d/13Qt2g2m3-VCpoPwhOkmVZVh1hF-Auxm-/view) |
| ศรีสะเกษ | 1 | 17.54% | [open](https://drive.google.com/file/d/14TXAj8mlYfj2zdCWQEuVs1kGLmw06_O5/view) | [open](https://drive.google.com/file/d/1S9e09zh-G6MWcgjyIX5TZf6hRA_lfKQ-/view) |

## Existing Files

- `homework_15_unit_progress.json`
- `homework_15_unit_progress.csv`
- `analyze_15_unit_vs_district.py`

## Recommended Next Execution Step

Generate unit-level aggregation from Vote62 and compare against current district-level read/ECT:

```bash
./venv/bin/python analyze_15_unit_vs_district.py
```

Expected outputs:

- `analysis_15_unit_vs_district_summary.json`
- `analysis_15_unit_vs_district_summary.csv`
- `analysis_15_unit_vs_district_units.json`
- `analysis_15_unit_vs_district_units.csv`

## Acceptance Criteria (for this 15-district homework)

- Unit rows exist for all 15 districts in `analysis_15_unit_vs_district_units.*`.
- Summary shows `vote62_agg_valid_votes` for both `constituency` and `party_list` where available.
- Delta columns (`vote62 vs read`, `vote62 vs ECT`) are computable and reviewed per district.

