# Fix LM Studio Backend for Ballot OCR

**Area:** ocr
**Created:** 2026-02-20
**Files:** model_backends.py, ballot_extraction.py

## Problem

LM Studio backend is not extracting vote counts correctly when run through ballot_ocr.py:
- Direct backend test works: extracts province "แพร่" and vote counts {1:657, 2:657, 3:657}
- Running ballot_ocr.py shows: province "เชียงใหม่" with no vote counts
- Model glm-ocr returns valid data but parsing/formatting issues

## Solution

1. Debug why ballot_ocr.py shows different results than direct backend test
2. Fix lenient JSON parser to handle malformed JSON from glm-ocr
3. Verify end-to-end extraction works correctly
