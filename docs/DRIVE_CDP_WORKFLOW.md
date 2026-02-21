# Google Drive CDP Workflow (Folder Browsing + Gemini Context)

This guide explains how to browse Google Drive folder levels programmatically, extract file-level Gemini context, and persist a Drive-to-local mapping for ground truth.

## What this uses

- Script: `/Users/nat/dev/election/drive_cdp_browser.py`
- Mapping helper: `/Users/nat/dev/election/drive_mapping.py`
- Chrome remote debugging endpoint: `http://127.0.0.1:9222/json`
- Existing authenticated Chrome session (you stay logged in via normal browser)

## 1) Prerequisites

1. Open Chrome with remote debugging enabled:

```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 \
  --user-data-dir=/tmp/chrome-cdp
```

2. In that Chrome window, log in to Google and open your Drive folder/file.

3. Install project dependencies:

```bash
cd /Users/nat/dev/election
./venv/bin/pip install -r requirements.txt
```

## 2) Verify CDP connection

```bash
cd /Users/nat/dev/election
./venv/bin/python drive_cdp_browser.py targets
```

Expected: rows containing Drive tab ids, titles, and URLs.

## 3) Browse folder level programmatically

### Show current folder/file rows

```bash
./venv/bin/python drive_cdp_browser.py list
```

Output format:
- `DIR` rows are folders
- `FILE` rows are files
- Each row includes a `row` index and Drive `id`

Example:

```text
[001] DIR  id=... name=อำเภอวังชิ้น
[002] DIR  id=... name=อำเภอสูงเม่น
[003] FILE id=... name=สส.5_18.pdf
```

### Open by row index

```bash
./venv/bin/python drive_cdp_browser.py open --row 1
```

### Open by item id

- Auto-detect folder/file from current listing context:

```bash
./venv/bin/python drive_cdp_browser.py open --id <DRIVE_ITEM_ID>
```

- Force open as file preview:

```bash
./venv/bin/python drive_cdp_browser.py open --id <FILE_ID> --file
```

### Typical drill-down sequence

```bash
./venv/bin/python drive_cdp_browser.py list
./venv/bin/python drive_cdp_browser.py open --row 1
./venv/bin/python drive_cdp_browser.py list
./venv/bin/python drive_cdp_browser.py open --row 2
./venv/bin/python drive_cdp_browser.py list
```

Repeat until you reach the target file row.

## 4) Extract Gemini context from current file tab

When the current tab is a Drive file preview page:

```bash
./venv/bin/python drive_cdp_browser.py gemini
```

Behavior:
- If a Gemini `Summary` block is present, script prints that summary.
- If no summary block is found, script prints visible page text fallback.

## 5) Record mapping (Drive ID -> local path + Gemini context)

Create/update an entry in `drive_file_mapping.json` from the current file tab:

```bash
./venv/bin/python drive_cdp_browser.py record \
  --local-path "/Users/nat/dev/election/ballots/Phrae/.../สส.5_18.pdf" \
  --folder-path "Phrae/เขตเลือกตั้งที่ 1/อำเภอสูงเม่น/หน่วยเลือกตั้งที่ 7"
```

Notes:
- `--local-path` is optional but recommended for matching with local OCR inputs.
- `--folder-path` is optional (breadcrumb hint).
- Use `--mapping-file /path/to/custom.json` to write elsewhere.

Generated default file:
- `/Users/nat/dev/election/drive_file_mapping.json`

## 5.1) Full auto-collection (resumable, hybrid mode)

This mode is optimized for scale:
- Discovery: programmatic (`embeddedfolderview`) without browser traversal.
- Extraction: parallel browser tabs for Gemini/AI overview capture.
- Resume: state + dedupe against existing JSONL/mapping.

Run:

```bash
cd /Users/nat/dev/election
./venv/bin/python -u drive_cdp_browser.py crawl-gemini \
  --root-folder-id 1wD2ICNJHLhW0UaisZpW8ie49RC8Ba50v \
  --discovery-mode public \
  --workers 4 \
  --mapping-file /Users/nat/dev/election/drive_file_mapping.json \
  --output-file /Users/nat/dev/election/drive_ai_overview_raw.jsonl \
  --state-file /Users/nat/dev/election/drive_ai_overview_state.json
```

Resume behavior:
- Default is resumable (`--resume`).
- To restart fresh for same files, pass `--no-resume`.

Schema shape:

```json
{
  "version": 1,
  "files": {
    "<DRIVE_FILE_ID>": {
      "drive_id": "1abc...",
      "drive_url": "https://drive.google.com/file/d/1abc.../view",
      "name": "สส5_18.pdf",
      "local_path": "/abs/path/to/file.pdf",
      "folder_path": ["Phrae", "เขตเลือกตั้งที่ 1", "อำเภอสูงเม่น"],
      "gemini_summary": "...",
      "gemini_fetched_at": "2026-02-19T10:30:00Z"
    }
  }
}
```

## 6) Programmatic lookup helper

Use `/Users/nat/dev/election/drive_mapping.py` in other modules:

```python
from drive_mapping import find_by_drive_id, find_by_local_path

entry1 = find_by_drive_id("1abc...")
entry2 = find_by_local_path("/Users/nat/dev/election/ballots/.../สส.5_18.pdf")
```

This is intended to be the 4th ground truth source (Drive/Gemini) alongside human input, Vote62, and ECT.

## 6.1) Official District-Level Extraction (Fast Pass + Retry)

For district-level official PDFs (province -> `แบบแบ่งเขต` / `แบบบัญชีรายชื่อ`):

1. Build full manifest (all provinces, both election types):

```bash
cd /Users/nat/dev/election
python /Users/nat/dev/election/official_district_files_manifest.json
```

2. Build mapping for scraper input:

```bash
# Generated in current workflow:
# /Users/nat/dev/election/official_manifest_all_mapping.json
```

3. Run fast pass first (accept misses), then retry only failed files:

```bash
PROMPT=$(cat /Users/nat/dev/election/official_district_extract_prompt_v3_fast.txt)
./venv/bin/python -u /Users/nat/dev/election/scrape_drive_pdf_summaries.py \
  --mapping-file /Users/nat/dev/election/official_manifest_remaining_mapping.json \
  --out-file /Users/nat/dev/election/official_manifest_part2_raw.jsonl \
  --state-file /Users/nat/dev/election/official_manifest_part2_state.json \
  --workers 4 \
  --wait-seconds 14 \
  --retries 1 \
  --retry-wait-increment 6 \
  --pre-ask-delay-seconds 5 \
  --gemini-prompt "$PROMPT" \
  --no-resume
```

Recommended strategy:
- Pass 1: prioritize speed (`workers` high, short wait)
- Pass 2: rerun only failures/missing JSON with slower settings
- Keep final merge keyed by `drive_id` + parsed district metadata

## 6.2) Tab Warm-Up Before Asking Gemini

New option in scraper:

```bash
--pre-ask-delay-seconds <N>
```

Use this when Gemini panel is flaky:
- Opens tab
- Waits `N` seconds
- Then asks Gemini prompt

This improves response reliability when opening many tabs in parallel.

## 6.3) Numeric Output Policy (Arabic Digits Only)

To prevent mixed Thai/Arabic numerals in extracted JSON:

- Prompt rule: require ASCII digits (`0-9`) for all numeric fields.
- Post-process normalization: `/Users/nat/dev/election/normalize_gemini_numbers_to_arabic.py`

Example:

```bash
python /Users/nat/dev/election/normalize_gemini_numbers_to_arabic.py \
  --in-file /Users/nat/dev/election/official_manifest_part2_raw.jsonl \
  --out-file /Users/nat/dev/election/official_manifest_part2_normalized.jsonl
```

## 7) Direct Gemini JSON extraction (recommended over overview scraping)

Use Gemini API directly with the strict multi-form instruction prompt.

Prereq:
- Set `GEMINI_API_KEY`
- Have `/Users/nat/dev/election/drive_file_mapping.json` populated

Run:

```bash
cd /Users/nat/dev/election
export GEMINI_API_KEY=\"<your_key>\"
./venv/bin/python gemini_drive_json_extract.py \
  --mapping-file /Users/nat/dev/election/drive_file_mapping.json \
  --summary-jsonl /Users/nat/dev/election/drive_pdf_summary_only_v3.jsonl \
  --prompt-template /Users/nat/dev/election/prompts/gemini_ballot_json_extraction.md \
  --out-dir /Users/nat/dev/election/gemini_extractions \
  --state-file /Users/nat/dev/election/gemini_extractions_state.json \
  --model gemini-2.0-flash
```

`--summary-jsonl` is used to infer per-file form type hints from the PDF summarizer output, so Gemini gets form-specific extraction focus while still returning strict JSON.

Artifacts:
- `/Users/nat/dev/election/gemini_extractions/<drive_id>.raw.txt` (raw model text)
- `/Users/nat/dev/election/gemini_extractions/<drive_id>.json` (parsed JSON, if valid)
- `/Users/nat/dev/election/gemini_extractions/<drive_id>.prompt.txt` (effective prompt with form-specific focus)
- `/Users/nat/dev/election/gemini_extractions_state.json` (resume state)

## 8) Use with verifier app

The verifier UI also supports this source:

- File: `/Users/nat/dev/election/verify_ground_truth_app.py`
- Panel: `Drive Gemini Context`
- Button: `Fetch from Open Chrome Drive Tab`

Run verifier:

```bash
./venv/bin/python /Users/nat/dev/election/verify_ground_truth_app.py
```

Then click the fetch button to populate Gemini context in-app.

## Troubleshooting

### `ERROR: cannot fetch DevTools targets`

- Chrome not started with `--remote-debugging-port=9222`
- Port is blocked/used by another process

### `ERROR: no suitable Drive tab target found`

- Open a Drive page in the debug-enabled Chrome window
- If multiple tabs exist, pass a specific tab id:

```bash
./venv/bin/python drive_cdp_browser.py list --target-id <TARGET_ID>
```

### `No folder rows found on current page`

- You are likely on a file preview page. Use `gemini` or navigate back to a folder page.

### `done_ids` increases but output JSONL lines do not

- This can happen with aggressive concurrency and panel timeouts.
- Mitigation:
  - reduce workers
  - increase `--wait-seconds`
  - add `--pre-ask-delay-seconds 3-5`
  - run fast pass + retry failed-only queue

### `Missing dependency: install 'websockets'`

- Install requirements again:

```bash
./venv/bin/pip install -r requirements.txt
```
