# Party Name Verification Notes

## 2026-02-27: นครสวรรค์ เขต 5 Party List Verification

### User Complaint
User reported: "นครสวรรค์เขต 5 บัญชีรายชื่อ ลำดับที่พรรคประชาชนเขียนผิดเป็นพรรคพลังประชารัฐ"

### Verification Method
- Used Gemini via CDP browser to extract data from Google Drive
- File: `23. นครสวรรค์ เขต 5 (บช).pdf`
- Drive ID: `1vifvpiF4lzLzS_kiWkYuYhZDQrqIy5wo`

### Result: BUG FOUND AND FIXED ✓

**Problem:** Party 46's votes (ประชาชน - 23,122) were incorrectly assigned to party 43.

| Party | Before (Wrong) | After (Correct) |
|-------|----------------|-----------------|
| 43 (พลังประชารัฐ) | 23,122 | 255 |
| 46 (ประชาชน) | 316 | 23,122 |

**Fix applied:** Updated `docs/data/district_dashboard_data.json`

### Gemini Confirmation
```
ประชาชน = Party 46 with 23,122 votes ✓
พลังประชารัฐ = Party 43 with 255 votes ✓
```

## 2026-02-27: มหาสารคาม เขต 3, 4 Party List Verification

### User Complaint
User reported: "มหาสารคามเขต 3, 4 บัญชีรายชื่อ ลำดับพรรคผิดสลับกันหมดเลย"

### Result: DATA IS CORRECT ✓

Verified via Gemini extraction:
- **มหาสารคาม เขต 3**: Party 46 (ประชาชน) = 17,656 ✓, Party 37 (ภูมิใจไทย) = 17,959 ✓
- **มหาสารคาม เขต 4**: Party 46 (ประชาชน) = 19,132 ✓, Party 37 (ภูมิใจไทย) = 14,921 ✓

## 2026-02-27: นราธิวาส เขต 2 Vote Discrepancy

### User Complaint
Vote discrepancy: 43,544 vs 43,594 for กล้าธรรม

### Result: DATA IS CORRECT ✓
System shows 43,594 votes for candidate 2 (กล้าธรรม), which matches the ballot paper.
The 43,544 value was from a different/incorrect source.

### Gemini Confirmation
```
Candidate 2 (กล้าธรรม) = 43,594 votes ✓
```

## 2026-02-27: มหาสารคาม เขต 3 Constituency OCR Error Fix

### Issue
Sum of candidate votes (79,786) did not match valid_votes (84,786) - a difference of 5,000 votes.

### Root Cause
OCR misread Thai numeral "๓๙" (39) as "๓๔" (34) for candidate 6's vote count.

| Field | Before (Wrong) | After (Correct) |
|-------|----------------|-----------------|
| Candidate 6 (ภูมิใจไทย) | 34,612 | 39,612 |

**Fix applied:** Updated `docs/data/district_dashboard_data.json`

### Verification
- Sum of votes now: 84,786 ✓
- Valid votes: 84,786 ✓
- Delta: 0 ✓

