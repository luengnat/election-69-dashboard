# Thai Election Ballot OCR

## Vision

A verification platform that extracts vote counts from handwritten Thai ballot images using AI Vision OCR and validates them against official Election Commission (ECT/กกต.) data to detect discrepancies in Thailand's electoral process.

## Problem Statement

Thailand's election ballot counting forms are handwritten, making them difficult to audit. Manual verification is time-consuming and error-prone. This platform automates the extraction and validation of vote counts from ballot images.

## Target Users

- Election observers and watchdog organizations
- Civic tech initiatives monitoring electoral integrity
- Researchers analyzing election data

## Core Features

1. **AI Vision OCR Extraction** - Extract vote counts from handwritten Thai ballot forms
2. **Form Type Detection** - Automatically identify 6 different Thai election form types
3. **Multi-Model Support** - Use multiple AI models (OpenRouter, Claude Vision) for extraction
4. **Validation Layer** - Cross-check extracted data using:
   - Numeric vs Thai text validation
   - Sum validation (vote counts must equal valid votes)
   - ECT API reference data comparison
5. **Discrepancy Detection** - Flag inconsistencies between reported and extracted data

## Success Metrics

- OCR accuracy >95% for handwritten vote counts
- Province name extraction accuracy >99%
- Form type detection accuracy >99%
- Processing time <5 seconds per form

## Constraints

- Must work with scanned/photographed ballot images
- Must handle Thai numerals (๑๒๓๔๕๖๗๘๙๐) and Arabic numerals
- Must support 6 different form types (constituency and party-list variants)

## Current State

- Working OCR extraction with OpenRouter (Gemma 3 12B IT)
- Claude Vision fallback implemented
- ECT API integration for reference data validation
- Prompts optimized for Thai ballot forms
- Test images available in test_images/

## Technical Context

See `.planning/codebase/` for detailed analysis of existing code.
