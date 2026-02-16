# Phase 7: Metadata Inference - Research

**Researched:** 2026-02-16
**Domain:** Path-based metadata extraction, Unicode normalization, Thai text parsing
**Confidence:** HIGH (based on existing codebase patterns and Python standard library)

## Summary

Phase 7 implements automatic extraction of province and constituency metadata from file paths to reduce OCR burden. The system parses Google Drive folder structures and file names using regex patterns, validates extracted data against the ECT province list, and falls back to OCR extraction when path parsing fails.

Key findings:
1. **Existing implementation exists** in `download_ballots.py:extract_metadata_from_path()` - this function already parses Thai path patterns but needs enhancement
2. **Unicode normalization is critical** - the codebase already uses `unicodedata.normalize("NFKD", ...)` in `gdrivedl.py` for Thai filename sanitization
3. **ECT validation already implemented** - `ect_api.py:validate_province_name()` strips the Thai "province" prefix and validates against the 77 official provinces
4. **Path patterns are documented** - the Google Drive folder structure follows a predictable pattern with Thai folder names

**Primary recommendation:** Extend the existing `extract_metadata_from_path()` function into a dedicated `MetadataParser` class that handles Unicode NFC normalization, province name validation, and OCR fallback integration with the batch processor.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `re` | stdlib | Regex parsing for Thai patterns | Python standard library, already used in `download_ballots.py` |
| `unicodedata` | stdlib | Unicode NFC normalization for Thai characters | Already used in `gdrivedl.py`, handles Thai combining marks |
| `pathlib.Path` | stdlib | Cross-platform path handling | Better than string concatenation for Unicode paths |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `ect_api.ECTData` | existing | Province validation against official ECT list | Always - validate every extracted province name |
| `ballot_ocr.extract_ballot_data_with_ai` | existing | OCR fallback when path parsing fails | When path metadata extraction returns None/invalid |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `unicodedata.normalize("NFC", ...)` | `unicodedata.normalize("NFKD", ...)` | NFKD decomposes more aggressively but changes string length. NFC is standard for comparison. Keep NFKD for filename sanitization only. |
| Custom regex patterns | `pythainlp` library | pythainlp adds a dependency for simple pattern matching. Regex is sufficient for extracting `เขตเลือกตั้งที่ X` patterns. |

**No new packages required** - all functionality uses existing dependencies.

## Architecture Patterns

### Recommended Project Structure
```
/Users/nat/dev/election/
├── metadata_parser.py       # NEW: PathMetadataParser class
├── download_ballots.py      # Existing: extract_metadata_from_path() - refactor into new module
├── ect_api.py               # Existing: ECTData.validate_province_name()
├── ballot_ocr.py            # Existing: BallotData dataclass
└── batch_processor.py       # Existing: BatchProcessor - add metadata pre-fill hook
```

### Pattern 1: PathMetadataParser Class
**What:** Centralized metadata extraction with validation and fallback
**When to use:** When processing any ballot image path
**Example:**
```python
# Source: Based on existing download_ballots.py:extract_metadata_from_path()
import re
import unicodedata
from pathlib import Path
from dataclasses import dataclass
from typing import Optional
from ect_api import ect_data

@dataclass
class InferredMetadata:
    """Metadata extracted from file path."""
    province: Optional[str] = None
    constituency_number: Optional[int] = None
    district: Optional[str] = None
    subdistrict: Optional[str] = None
    polling_unit: Optional[int] = None
    form_type: Optional[str] = None  # 'constituency' or 'party_list'
    source: str = "path"  # 'path' or 'ocr' (fallback source indicator)
    confidence: float = 0.0  # 0.0 to 1.0

class PathMetadataParser:
    """
    Extract province/constituency metadata from Thai ballot file paths.

    Path structure example:
    ballots/Phrae/เขตเลือกตั้งที่ 1 จังหวัดแพร่/อําเภอสูงเม่น/ตําบลดอนมูล/หน่วยเลือกตั้งที่1/สส5ทับ18.pdf

    Integration:
    - Use before OCR to pre-fill BallotData fields
    - Validate province with ect_data.validate_province_name()
    - Fall back to OCR extraction if path parsing fails
    """

    # Regex patterns for Thai metadata extraction
    CONSTITUENCY_PATTERN = re.compile(r'เขตเลือกตั้งที่\s*(\d+)')
    DISTRICT_PATTERN = re.compile(r'อําเภอ([^/]+)')
    SUBDISTRICT_PATTERN = re.compile(r'ตําบล([^/]+)')
    POLLING_UNIT_PATTERN = re.compile(r'หน่วยเลือกตั้งที่\s*(\d+)')
    PROVINCE_IN_PATH_PATTERN = re.compile(r'จังหวัด([^/]+)')

    def __init__(self):
        """Initialize parser with ECT data reference."""
        ect_data.load()  # Ensure province list is loaded

    def normalize_thai(self, text: str) -> str:
        """Apply NFC normalization for consistent Thai character comparison."""
        return unicodedata.normalize('NFC', text)

    def parse_path(self, file_path: str) -> InferredMetadata:
        """Extract metadata from a ballot file path."""
        metadata = InferredMetadata()

        # Normalize the path for consistent parsing
        normalized_path = self.normalize_thai(file_path)

        # Extract constituency number
        cons_match = self.CONSTITUENCY_PATTERN.search(normalized_path)
        if cons_match:
            metadata.constituency_number = int(cons_match.group(1))

        # Extract province from path (จังหวัด prefix)
        prov_match = self.PROVINCE_IN_PATH_PATTERN.search(normalized_path)
        if prov_match:
            potential_province = prov_match.group(1).strip()
            # Validate against ECT list
            is_valid, canonical = ect_data.validate_province_name(potential_province)
            if is_valid and canonical:
                metadata.province = canonical
                metadata.confidence += 0.3

        # Extract district (อําเภอ)
        dist_match = self.DISTRICT_PATTERN.search(normalized_path)
        if dist_match:
            metadata.district = dist_match.group(1).strip()

        # Extract subdistrict (ตําบล)
        subdist_match = self.SUBDISTRICT_PATTERN.search(normalized_path)
        if subdist_match:
            metadata.subdistrict = subdist_match.group(1).strip()

        # Extract polling unit
        unit_match = self.POLLING_UNIT_PATTERN.search(normalized_path)
        if unit_match:
            metadata.polling_unit = int(unit_match.group(1))

        # Extract form type from filename
        filename = Path(file_path).name
        if '(บช)' in filename:
            metadata.form_type = 'party_list'
        elif '5ทับ18' in filename or '5/18' in filename:
            metadata.form_type = 'constituency'

        # Calculate confidence based on fields extracted
        if metadata.province:
            metadata.confidence += 0.3
        if metadata.constituency_number:
            metadata.confidence += 0.2
        if metadata.district:
            metadata.confidence += 0.1

        return metadata

    def extract_province_from_parent_dir(self, file_path: str) -> Optional[str]:
        """
        Extract province from immediate parent directory name.
        Google Drive folders are named after provinces (e.g., "Phrae" or "แพร่").
        """
        parent_dir = Path(file_path).parent.name
        normalized = self.normalize_thai(parent_dir)

        # Try direct match against ECT province list
        is_valid, canonical = ect_data.validate_province_name(normalized)
        if is_valid and canonical:
            return canonical

        return None
```

### Pattern 2: Integration with BatchProcessor
**What:** Pre-fill BallotData from path before OCR
**When to use:** In batch processing pipeline
**Example:**
```python
# Integration in batch_processor.py process_single method
def process_single(self, image_path: str) -> Optional[BallotData]:
    """Process a single ballot image with metadata pre-fill and retry logic."""

    # Phase 7: Pre-extract metadata from path
    path_metadata = self.metadata_parser.parse_path(image_path)

    with self.rate_limiter:
        ballot_data = extract_ballot_data_with_ai(image_path)

        if ballot_data:
            # Pre-fill from path if OCR missed these fields
            if not ballot_data.province and path_metadata.province:
                ballot_data.province = path_metadata.province
            if not ballot_data.constituency_number and path_metadata.constituency_number:
                ballot_data.constituency_number = path_metadata.constituency_number
            if not ballot_data.district and path_metadata.district:
                ballot_data.district = path_metadata.district

            # Track metadata source for auditing
            ballot_data.confidence_details["metadata_source"] = {
                "province": "path" if path_metadata.province else "ocr",
                "constituency": "path" if path_metadata.constituency_number else "ocr"
            }

        return ballot_data
```

### Anti-Patterns to Avoid
- **Anti-pattern:** Trusting path metadata without validation. **Why it's bad:** Path naming is inconsistent - users may use wrong province names. **What to do instead:** Always validate against `ect_data.validate_province_name()`
- **Anti-pattern:** Using string concatenation for paths with Thai characters. **Why it's bad:** Encoding issues across platforms (Windows vs Unix). **What to do instead:** Use `pathlib.Path` which handles encoding properly
- **Anti-pattern:** Overwriting OCR-extracted province with path-extracted one. **Why it's bad:** OCR reads the actual form which is authoritative. **What to do instead:** Only pre-fill when OCR returns empty/None, log mismatches

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Unicode normalization | Custom string replacement | `unicodedata.normalize('NFC', text)` | Handles all edge cases with Thai combining marks |
| Province validation | Custom province list | `ect_data.validate_province_name()` | Already has 77 official provinces with Thai/English mapping |
| Path parsing | String split/index | `pathlib.Path` with regex | Handles cross-platform path separators and encoding |
| Thai number conversion | Custom parser | `ballot_ocr.convert_thai_numerals()` | Already exists - handles Thai numerals to Arabic |

**Key insight:** The codebase already has most required functionality. Phase 7 is primarily about wiring existing functions together and adding fallback logic.

## Common Pitfalls

### Pitfall 1: Unicode Normalization Mismatch
**What goes wrong:** Thai characters can be represented in multiple Unicode forms (composed vs decomposed). Path strings from different sources may use different forms, causing comparison failures.
**Why it happens:** Unicode allows combining characters (base + tone mark) and precomposed characters (single code point). Different systems use different forms.
**How to avoid:** Always apply `unicodedata.normalize('NFC', text)` before comparison. NFC (Canonical Composition) is the standard for comparison.
**Warning signs:** `UnicodeEncodeError` in logs, province names not matching ECT list when they "should", string equality checks failing unexpectedly

### Pitfall 2: Overriding OCR with Path Data
**What goes wrong:** If path says Province A but form actually says Province B (e.g., file was moved), blindly using path data assigns votes to wrong jurisdiction.
**Why it happens:** Developers assume paths are authoritative, but users can rename files incorrectly.
**How to avoid:** Only use path metadata to PRE-FILL (when OCR returns empty). If OCR returns a different value, log the mismatch and trust OCR.
**Warning signs:** Province mismatch between path and OCR in logs, unexpected constituency assignments

### Pitfall 3: Missing Fallback to OCR
**What goes wrong:** If path parsing fails completely (unrecognized naming pattern), the ballot is processed with no province/constituency data, leading to validation failures.
**Why it happens:** Regex patterns are strict and may not match all user naming conventions.
**How to avoid:** Always let OCR run and extract data. Path metadata is an optimization, not a replacement.
**Warning signs:** Ballots with empty province field, ECT validation failures, low confidence scores

### Pitfall 4: Thai Tone Mark Stripping
**What goes wrong:** When normalizing or comparing Thai text, tone marks (่ ้ ๊ ๋) can be lost or mishandled, changing province names.
**Why it happens:** NFKD normalization decomposes characters, potentially separating base from tone marks.
**How to avoid:** Use NFC (not NFKD) for province name comparison. NFKD is for filename sanitization only.
**Warning signs:** Province "ลพบุรี" not matching "ลพบุรี" (different tone mark encoding), validation failures on valid provinces

## Code Examples

### Extracting Province from Google Drive Path
```python
# Source: Based on existing download_ballots.py patterns and ect_api.py
import re
import unicodedata
from pathlib import Path
from typing import Optional, Tuple

def extract_and_validate_province(file_path: str) -> Tuple[Optional[str], float]:
    """
    Extract province from file path and validate against ECT list.

    Returns:
        Tuple of (canonical_province_name, confidence_score)
        (None, 0.0) if extraction fails or validation fails
    """
    from ect_api import ect_data

    normalized_path = unicodedata.normalize('NFC', file_path)

    # Pattern 1: "จังหวัดแพร่" in path
    prov_match = re.search(r'จังหวัด([^/]+)', normalized_path)
    if prov_match:
        potential = prov_match.group(1).strip()
        is_valid, canonical = ect_data.validate_province_name(potential)
        if is_valid:
            return canonical, 0.8

    # Pattern 2: Parent directory is province name (English or Thai)
    parent = Path(file_path).parent.name
    parent = unicodedata.normalize('NFC', parent)

    # Try direct lookup
    is_valid, canonical = ect_data.validate_province_name(parent)
    if is_valid:
        return canonical, 0.7

    return None, 0.0
```

### Integrating with Existing BallotData
```python
# Source: Based on ballot_ocr.py BallotData dataclass
def merge_path_and_ocr_metadata(
    path_metadata: InferredMetadata,
    ballot_data: "BallotData"
) -> "BallotData":
    """
    Merge path-extracted metadata with OCR results.
    OCR results are authoritative - path data only fills gaps.
    """
    # Only fill from path if OCR didn't extract
    if not ballot_data.province and path_metadata.province:
        ballot_data.province = path_metadata.province

    if not ballot_data.constituency_number and path_metadata.constituency_number:
        ballot_data.constituency_number = path_metadata.constituency_number

    if not ballot_data.district and path_metadata.district:
        ballot_data.district = path_metadata.district

    if not ballot_data.polling_unit and path_metadata.polling_unit:
        ballot_data.polling_unit = path_metadata.polling_unit

    # Log any mismatches for auditing
    if ballot_data.province and path_metadata.province:
        if ballot_data.province != path_metadata.province:
            print(f"WARNING: Province mismatch - path={path_metadata.province}, ocr={ballot_data.province}")

    return ballot_data
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| String concatenation for paths | `pathlib.Path` | Phase 5 (batch_processor.py) | Cross-platform Unicode handling |
| No Unicode normalization | `unicodedata.normalize('NFC', ...)` | Existing (gdrivedl.py) | Consistent Thai character comparison |
| Manual province list | ECT API for validation | v1.0 | 77 provinces always current |

**Deprecated/outdated:**
- `os.path` string operations: Use `pathlib.Path` instead for Unicode safety
- NFKD normalization for comparison: Use NFC for comparison, NFKD only for filename sanitization

## Open Questions

1. **Should we cache parsed metadata?**
   - What we know: BatchProcessor processes same directories repeatedly
   - What's unclear: Memory vs re-parsing tradeoff
   - Recommendation: No caching needed - path parsing is fast (microseconds). Focus caching on ECT API calls instead.

2. **How to handle province name in both Thai and English?**
   - What we know: Paths may use "Phrae" or "แพร่" interchangeably
   - What's unclear: Which to store in BallotData
   - Recommendation: Always store Thai name (canonical from ECT) in BallotData. The `ect_api.py` already handles Thai-English mapping.

3. **Should mismatch logging be structured or plain text?**
   - What we know: Current code uses print() for warnings
   - What's unclear: Integration with existing confidence_details dict
   - Recommendation: Add to `confidence_details["metadata_source"]` with path vs OCR source tracking

## Sources

### Primary (HIGH confidence)
- `/Users/nat/dev/election/download_ballots.py:27-66` - Existing `extract_metadata_from_path()` implementation
- `/Users/nat/dev/election/ect_api.py:198-211` - `validate_province_name()` implementation with "จังหวัด" prefix stripping
- `/Users/nat/dev/election/gdrivedl.py:90-91` - Unicode normalization pattern (`unicodedata.normalize("NFKD", ...)`)
- `/Users/nat/dev/election/batch_processor.py` - Integration point for metadata pre-fill

### Secondary (MEDIUM confidence)
- `/Users/nat/dev/election/ballot_ocr.py` - BallotData dataclass structure and OCR extraction patterns
- `/Users/nat/dev/election/province_folders.py` - Province name mapping (Thai/English)
- `/Users/nat/dev/election/.planning/research/PITFALLS.md:118-153` - Pitfall 4: Path-Based Metadata Inference Failures

### Tertiary (LOW confidence)
- [Python unicodedata documentation](https://docs.python.org/3/library/unicodedata.html) - Standard library reference (verified against existing code usage)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - All required libraries already exist in codebase
- Architecture: HIGH - Existing `extract_metadata_from_path()` provides proven pattern
- Pitfalls: HIGH - Documented in PITFALLS.md with prevention strategies

**Research date:** 2026-02-16
**Valid until:** 30 days (stable Python standard library, existing codebase patterns)
