# Thai Election Ballot Form Categorization

## Form Types (6 Total)

| # | Form Code | Thai Name | Category | Description |
|---|-----------|-----------|----------|-------------|
| 1 | ส.ส. 5/16 | รายงานผลการนับคะแนนบัตรเลือกตั้งที่ออกเสียงลงคะแนนก่อนวันเลือกตั้ง ในเขตเลือกตั้งแบบแบ่งเขตเลือกตั้ง | Constituency | Early voting |
| 2 | ส.ส. 5/16 (บช) | รายงานผลการนับคะแนนบัตรเลือกตั้งที่ออกเสียงลงคะแนนก่อนวันเลือกตั้ง ในเขตเลือกตั้งแบบบัญชีรายชื่อ | Party-list | Early voting |
| 3 | ส.ส. 5/17 | รายงานผลการนับคะแนนบัตรเลือกตั้งนอกเขตเลือกตั้งและนอกราชอาณาจักร แบบแบ่งเขตเลือกตั้ง | Constituency | Out-of-district/overseas |
| 4 | ส.ส. 5/17 (บช) | รายงานผลการนับคะแนนบัตรเลือกตั้งนอกเขตเลือกตั้งและนอกราชอาณาจักร แบบบัญชีรายชื่อ | Party-list | Out-of-district/overseas |
| 5 | ส.ส. 5/18 | รายงานผลการนับคะแนน สส. แบบแบ่งเขตเลือกตั้ง (รายหน่วย) | Constituency | By polling unit |
| 6 | ส.ส. 5/18 (บช) | รายงานผลการนับคะแนน สส. แบบบัญชีรายชื่อ (รายหน่วย) | Party-list | By polling unit |

## Key Differences

| Aspect | Constituency (แบ่งเขต) | Party-list (บช) |
|--------|------------------------|-----------------|
| Candidates/Parties | ~6 candidates | Up to 57 parties |
| Pages per form | 1-2 pages | 4+ pages |
| Vote columns | Numeric + Thai text | Numeric + Thai text |

## Test Images Categorization

| File | Detected Form Type | Category | Province | Notes |
|------|-------------------|----------|----------|-------|
| `high_res_page-1.png` | ส.ส. 5/17 | Constituency | ลำพูน | 11 candidates detected |
| `bch_page-1.png` | ส.ส. 5/16 (บช) | Party-list | นนทบุรี | 30 parties, sum mismatch detected |
| `bch_page-2.png` | TBD | Party-list | TBD | Parties 11-20 |
| `bch_page-3.png` | TBD | Party-list | TBD | Parties 21-30 |
| `bch_page-4.png` | TBD | Party-list | TBD | Parties 31-57 |

## Validation Methods

1. **Numeric vs Thai Text**: Each vote count has two representations
   - Example: `154` = `หนึ่งร้อยห้าสิบสี่`
   - Cross-validate to catch OCR errors

2. **Sum Validation**: Individual vote counts should sum to total
   - Detected mismatch in `bch_page-1.png`: 234 (calculated) vs 225 (reported)

3. **ECT Reference Data**: Validate against official Election Commission data
   - 77 provinces validated
   - 57 parties with numbers and names
   - 401 constituencies

## Downloaded PDFs Structure

Path: `เขตเลือกตั้งที่ 1 จังหวัดแพร่/ล่วงหน้านอกเขตและนอกราชอาณาจักร/`

Each set (ชุดที่ 1-14) contains:
- `สส.5ทับ17ชุดที่X.pdf` - Constituency form (ส.ส. 5/17)
- `สส.5ทับ17(บช)ชุดที่X.pdf` - Party-list form (ส.ส. 5/17 (บช))

## Usage

```bash
# Process a single image
python ballot_ocr.py test_images/bch_page-1.png -o result.json

# Process a PDF (auto-converts to images)
python ballot_ocr.py path/to/ballot.pdf -o result.json

# With ECT verification
python ballot_ocr.py test_images/high_res_page-1.png --verify -o result.json
```
