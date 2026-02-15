# Coding Conventions

**Analysis Date:** 2026-02-16

## Naming Patterns

**Files:**
- All lowercase with underscores: `ballot_ocr.py`, `ect_api.py`, `gdrivedl.py`
- No mixed case (camelCase) in filenames
- Descriptive names that reflect functionality

**Functions:**
- All lowercase with underscores: `extract_ballot_data_with_ai`, `validate_vote_entry`, `thai_text_to_number`
- Private functions start with underscore: `_get_modified`, `_set_modified`
- Public functions are descriptive and action-oriented

**Classes:**
- PascalCase: `FormType`, `BallotData`, `Province`, `Party`, `Constituency`, `ECTData`
- Dataclasses are used for structured data with clear field types

**Variables:**
- All lowercase with underscores: `form_type`, `vote_counts`, `province_name`
- Constants are uppercase: `THAI_DIGITS`, `ECT_BASE_URL`, `CHUNKSIZE`
- Loop variables are concise: `p` for province, `c` for constituency

**Dataclass Fields:**
- Snake case: `form_type`, `vote_counts`, `province_name`, `constituency_number`
- Type annotations consistently used

## Code Style

**Formatting:**
- No formal linter configuration detected
- 4-space indentation for Python code
- Blank lines between class definitions and major function blocks
- Maximum line length varies - some lines exceed typical 79-88 character limits

**Docstrings:**
- Module-level docstrings at top of files
- Function docstrings use triple quotes with brief description
- Complex functions include detailed explanations of parameters and return values
- No standardized docstring format (PEP 257 not strictly followed)

**Type Hints:**
- Partial type annotation usage
- `from typing import Optional`, `from dataclasses import dataclass, field`
- Some functions lack type hints, especially in utility functions
- Union types not commonly used where appropriate

## Import Organization

**Order:**
1. Standard library imports
2. Third-party imports
3. Local imports

**Examples:**
```python
# Standard library
import os
import sys
import json
import subprocess
import base64
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum

# Third-party imports
import pytesseract
from PIL import Image
import requests
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow

# Local imports
try:
    from ect_api import ect_data
    ECT_AVAILABLE = True
except ImportError:
    ECT_AVAILABLE = False
```

**Path Aliases:**
- No relative imports detected
- All imports use full module paths

## Error Handling

**Patterns:**
- try/except blocks with specific exceptions where possible
- Error messages are descriptive and printed to console
- Graceful degradation with fallback mechanisms (e.g., OpenRouter → Claude Vision)

**Examples:**
```python
try:
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2048,
        messages=[...],
    )
    response_text = message.content[0].text.strip()
    return json.loads(response_text)
except Exception as e:
    print(f"Error detecting form type: {e}")
    return FormType.S5_17, str(e)
```

## Logging

**Approach:**
- Simple print() statements for output
- No formal logging framework
- Progress indicators and status messages
- Error messages when failures occur

**Patterns:**
```python
print(f"Processing: {image_path}")
print(f"  Validated {validated_count}/{len(vote_details)} entries")
print(f"  WARNING: Sum != Valid votes! Sum: {calculated_sum}, Valid: {reported_valid}")
```

## Comments

**When to Comment:**
- Complex algorithms (Thai number parsing)
- API integration explanations
- Data transformation logic
- Configuration details

**JSDoc/TSDoc:**
- Not used in this codebase
- Function documentation in docstrings instead

## Function Design

**Size:**
- Functions range from 5-150 lines
- Large functions (e.g., `extract_with_claude_vision`) broken down into logical sections
- No strict size enforcement

**Parameters:**
- Reasonable number of parameters (typically 2-5)
- Default values used where appropriate
- Type hints for better clarity

**Return Values:**
- Consistent return types
- Optional returns indicated with `Optional[Type]`
- Multiple values returned as tuples where appropriate

## Module Design

**Exports:**
- Main module exports classes and functions directly
- No explicit `__all__` declarations
- Utility functions are module-scoped

**Barrel Files:**
- Not used - each module is self-contained

**Structure:**
```
ballot_ocr.py  # Main OCR functionality
ect_api.py      # ECT API client
tesseract_ocr.py # OCR text extraction
gdrivedl.py     # Google Drive downloader
drive_auth.py   # Google Drive authentication
```

---

*Convention analysis: 2026-02-16*