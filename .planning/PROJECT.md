# Thai Election Ballot OCR

## What This Is

A verification platform that extracts vote counts from handwritten Thai ballot images using AI Vision OCR and validates them against official Election Commission (ECT/กกต.) data to detect discrepancies in Thailand's electoral process.

## Core Value

Automated ballot verification with 100% OCR accuracy on test images and ECT data cross-validation.

---

## Requirements

### Validated

- ✓ OCR Accuracy >95% — v1.0 (achieved 100% on test images)
- ✓ Form Type Detection — v1.0 (ส.ส. 5/16 and บช variants)
- ✓ Province Extraction >99% — v1.0 (100% accuracy)
- ✓ Vote Count Extraction — v1.0 (constituency and party-list)
- ✓ Confidence Scoring — v1.0 (3 levels: high/medium/low)
- ✓ Batch Processing — v1.0 (directory processing)
- ✓ Candidate Matching — v1.0 (3,491 candidates from ECT)
- ✓ Discrepancy Detection — v1.0 (severity-based)
- ✓ PDF Export — v1.0 (charts, constituency reports)

### Active

(To be defined for next milestone)

### Out of Scope

- Mobile app — web-first approach
- Real-time dashboard — batch processing sufficient for current use case
- Multi-model ensemble — single model achieved sufficient accuracy

---

## Context

**Shipped v1.0** with 4,966 LOC Python.

**Tech Stack:** Python 3, OpenRouter API (Gemma 3 12B IT), Claude Vision fallback, ECT API, reportlab

**Key Decisions:**

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Single model with fallback | Multi-model not needed | ✓ Good |
| reportlab for PDFs | No extra dependencies | ✓ Good |
| IQR method for outliers | Statistical validity | ✓ Good |
| Quality ratings (4 levels) | Clear quality assessment | ✓ Good |

**Known Technical Debt:**
- Executive Summary PDF (Phase 4.5) not implemented
- Web interface not implemented

---

## Target Users

- Election observers and watchdog organizations
- Civic tech initiatives monitoring electoral integrity
- Researchers analyzing election data

## Constraints

- Must work with scanned/photographed ballot images
- Must handle Thai numerals (๑๒๓๔๕๖๗๘๙๐) and Arabic numerals
- Must support 6 different form types (constituency and party-list variants)

---

*Last updated: 2026-02-16 after v1.0 milestone*
