#!/usr/bin/env python3
"""Browse Google Drive tabs programmatically via Chrome DevTools Protocol.

This script uses an already-running Chrome instance with:
  --remote-debugging-port=9222

Typical flow:
  1) python drive_cdp_browser.py targets
  2) python drive_cdp_browser.py list
  3) python drive_cdp_browser.py open --row 1
  4) python drive_cdp_browser.py list
  5) python drive_cdp_browser.py gemini
"""

from __future__ import annotations

import argparse
import asyncio
import concurrent.futures
import json
import re
import threading
import time
import urllib.parse
import urllib.request
from typing import Any

from drive_mapping import upsert_mapping_entry

DEFAULT_DEVTOOLS_URL = "http://127.0.0.1:9222/json"
DEFAULT_MAPPING_FILE = "drive_file_mapping.json"
PUBLIC_FOLDER_URL = "https://drive.google.com/embeddedfolderview?id={id}#list"
PUBLIC_ITEM_RE = re.compile(
    r'<a href="(https://drive\.google\.com/.*?)".*?<div class="flip-entry-title">(.*?)</div>.*?<div class="flip-entry-last-modified"><div>(.*?)</div>',
    re.DOTALL | re.IGNORECASE,
)


def _fetch_targets(devtools_url: str) -> list[dict[str, Any]]:
    with urllib.request.urlopen(devtools_url, timeout=3) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if not isinstance(data, list):
        return []
    return [x for x in data if isinstance(x, dict)]


def _open_url_in_new_tab(devtools_url: str, target_url: str) -> dict[str, Any] | None:
    """Open URL in a new Chrome tab through DevTools /json/new endpoint."""
    base = devtools_url.rsplit("/json", 1)[0]
    encoded = urllib.parse.quote(target_url, safe=":/?=&-_")
    endpoint = f"{base}/json/new?{encoded}"
    req = urllib.request.Request(endpoint, method="PUT")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _close_target(devtools_url: str, target_id: str) -> bool:
    base = devtools_url.rsplit("/json", 1)[0]
    endpoint = f"{base}/json/close/{target_id}"
    try:
        with urllib.request.urlopen(endpoint, timeout=5):
            return True
    except Exception:
        return False


def _pick_target(targets: list[dict[str, Any]], target_id: str | None = None) -> dict[str, Any] | None:
    if target_id:
        for t in targets:
            if t.get("id") == target_id:
                return t
        return None

    # Prefer Drive file preview tabs, then folder tabs.
    for t in targets:
        if t.get("type") != "page":
            continue
        url = str(t.get("url", ""))
        if "drive.google.com/file/d/" in url:
            return t
    for t in targets:
        if t.get("type") != "page":
            continue
        url = str(t.get("url", ""))
        if "drive.google.com/drive/folders/" in url:
            return t
    for t in targets:
        if t.get("type") != "page":
            continue
        url = str(t.get("url", ""))
        if "drive.google.com/" in url:
            return t
    return None


class CdpPage:
    def __init__(self, ws_url: str):
        self.ws_url = ws_url
        self._sock = None
        self._msg_id = 0

    async def __aenter__(self):
        import websockets

        self._sock = await websockets.connect(self.ws_url, max_size=20_000_000)
        await self.send("Runtime.enable")
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self._sock:
            await self._sock.close()

    async def send(self, method: str, params: dict | None = None) -> dict:
        self._msg_id += 1
        msg_id = self._msg_id
        payload = {"id": msg_id, "method": method, "params": params or {}}
        await self._sock.send(json.dumps(payload))
        while True:
            obj = json.loads(await self._sock.recv())
            if obj.get("id") == msg_id:
                return obj

    async def eval(self, expression: str):
        res = await self.send("Runtime.evaluate", {"expression": expression, "returnByValue": True})
        return res.get("result", {}).get("result", {}).get("value")


def _extract_first_json_object(text: str) -> str:
    """Extract the best valid JSON object from text, skipping invalid/noisy ones."""
    if not text:
        return ""
    raw = text.strip()

    # First try fenced JSON blocks
    fence = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", raw, flags=re.IGNORECASE)
    if fence:
        cand = fence.group(1).strip()
        if _is_valid_gemini_json(cand):
            return cand

    # Find all JSON objects and return the best one
    candidates = []
    pos = 0
    while pos < len(raw):
        start = raw.find("{", pos)
        if start < 0:
            break
        depth = 0
        in_str = False
        esc = False
        end_pos = None
        for i in range(start, len(raw)):
            ch = raw[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end_pos = i
                    break
        if end_pos is None:
            break
        cand = raw[start : end_pos + 1]
        try:
            obj = json.loads(cand)
            if isinstance(obj, dict):
                candidates.append((cand, obj))
        except Exception:
            pass
        pos = end_pos + 1

    # Return the best candidate (prefer larger objects with numeric values)
    best = ""
    best_score = 0
    for cand, obj in candidates:
        if not _is_valid_gemini_json(cand):
            continue
        # Score: prefer objects with more keys and numeric values
        score = len(obj)
        for v in obj.values():
            if isinstance(v, (int, float)):
                score += 10
            elif isinstance(v, str) and any(c.isdigit() for c in v):
                score += 5
        if score > best_score:
            best_score = score
            best = cand

    return best


def _json_needs_retry(parsed_json_text: str) -> bool:
    """Heuristic guardrail for low-quality Gemini JSON results."""
    if not parsed_json_text:
        return True
    try:
        obj = json.loads(parsed_json_text)
    except Exception:
        return True
    if not isinstance(obj, dict):
        return True

    check = obj.get("check")
    if isinstance(check, dict):
        sev = check.get("sum_equals_valid")
        if sev is False:
            return True

    votes = obj.get("votes")
    if isinstance(votes, dict):
        # Party/candidate keys should be numeric in our pipeline.
        if any(not str(k).isdigit() for k in votes.keys()):
            return True
        valid = obj.get("valid")
        if isinstance(valid, (int, float)):
            try:
                total = sum(int(v) for v in votes.values())
                if int(valid) != int(total):
                    return True
            except Exception:
                return True

    return False


async def _list_rows(ws_url: str) -> dict[str, Any]:
    async with CdpPage(ws_url) as page:
        url = await page.eval("location.href")
        title = await page.eval("document.title")
        rows = await page.eval(
            """(() => {
              return [...document.querySelectorAll('tr[role="row"]')].slice(0, 300).map((r, idx) => {
                const id = r.getAttribute('data-id') || '';
                const name = (r.querySelector('strong.DNoYtb')?.innerText || r.querySelector('.DNoYtb')?.innerText || '').trim();
                const aria = (r.querySelector('.JxSEve[aria-label]')?.getAttribute('aria-label') || '').trim();
                const low = aria.toLowerCase();
                const isFolder = low.includes('folder');
                const isFile = !isFolder && (!!name || !!id);
                return {row: idx + 1, id, name, aria, is_folder: isFolder, is_file: isFile};
              }).filter(x => x.id && x.name);
            })()"""
        )
        if not isinstance(rows, list):
            rows = []
        return {"url": url or "", "title": title or "", "rows": rows}


async def _navigate(ws_url: str, *, row: int | None = None, item_id: str | None = None, as_file: bool = False) -> str:
    async with CdpPage(ws_url) as page:
        chosen_id = item_id
        is_folder = False
        if row is not None:
            rows = await page.eval(
                """(() => {
                  return [...document.querySelectorAll('tr[role="row"]')].map((r, idx) => {
                    const id = r.getAttribute('data-id') || '';
                    const name = (r.querySelector('strong.DNoYtb')?.innerText || r.querySelector('.DNoYtb')?.innerText || '').trim();
                    const aria = (r.querySelector('.JxSEve[aria-label]')?.getAttribute('aria-label') || '').trim().toLowerCase();
                    return {row: idx + 1, id, name, is_folder: aria.includes('folder')};
                  }).filter(x => x.id && x.name);
                })()"""
            )
            if not isinstance(rows, list) or row < 1 or row > len(rows):
                raise RuntimeError(f"Row {row} is out of range")
            chosen = rows[row - 1]
            chosen_id = str(chosen.get("id", ""))
            is_folder = bool(chosen.get("is_folder"))

        if not chosen_id:
            raise RuntimeError("No item selected. Provide --row or --id")

        if as_file:
            target_url = f"https://drive.google.com/file/d/{chosen_id}/view"
        else:
            target_url = f"https://drive.google.com/drive/folders/{chosen_id}" if is_folder else f"https://drive.google.com/file/d/{chosen_id}/view"

        await page.eval(f'location.href = "{target_url}"')
        await asyncio.sleep(2.5)
        return str(await page.eval("location.href") or target_url)


async def _goto_url(ws_url: str, target_url: str, sleep_s: float = 2.0) -> str:
    async with CdpPage(ws_url) as page:
        await page.eval(f'location.href = "{target_url}"')
        await asyncio.sleep(sleep_s)
        return str(await page.eval("location.href") or target_url)


def _extract_gemini_summary_text(page_text: str) -> str:
    if not page_text:
        return ""
    marker = "Summary"
    start = page_text.find(marker)
    if start < 0:
        return ""
    tail = page_text[start + len(marker):].strip()
    stops = [
        "\nShow more",
        "\nList the main points for this file",
        "\nAsk a question about this file",
        "\nAsk Gemini",
        "\nGood suggestion",
        "\nBad suggestion",
    ]
    end = len(tail)
    for s in stops:
        pos = tail.find(s)
        if pos >= 0:
            end = min(end, pos)
    return tail[:end].strip()


async def _open_gemini_panel(page: CdpPage) -> None:
    """Try to open Gemini side panel in Drive viewer."""
    click_expr = """(() => {
      const norm = (s) => (s || '').trim().toLowerCase();
      const visible = (el) => {
        if (!el) return false;
        const r = el.getBoundingClientRect();
        return r.width > 0 && r.height > 0;
      };
      const candidates = [...document.querySelectorAll('button,[role="button"],div[role="button"]')].filter(visible);
      const target = candidates.find((el) => {
        const t = norm(el.innerText);
        const a = norm(el.getAttribute('aria-label'));
        const l = norm(el.getAttribute('data-tooltip') || el.getAttribute('title'));
        const k = `${t} ${a} ${l}`;
        // Support EN/TH variants and icon-only labels.
        return k.includes('ask gemini')
          || k.includes('gemini')
          || k.includes('ถาม')
          || k.includes('ดาว');
      });
      if (target) {
        target.click();
        return true;
      }
      return false;
    })()"""
    for _ in range(6):
        opened = bool(await page.eval(click_expr))
        if opened:
            await asyncio.sleep(1.0)
            return
        await asyncio.sleep(0.5)


async def _close_question_view(page: CdpPage) -> bool:
    """
    Dismiss the question/composer view so Gemini summary can appear.
    Returns True if a close action was triggered.
    """
    close_expr = """(() => {
      const body = document.body;
      if (!body) return false;
      const hasQuestionText = /ask a question about this file/i.test(body.innerText || '');
      if (!hasQuestionText) return false;

      // Prefer close control near Gemini panel content.
      const candidates = [...document.querySelectorAll('button,[role="button"]')];
      const target = candidates.find((el) => {
        const t = (el.innerText || '').trim().toLowerCase();
        const a = (el.getAttribute('aria-label') || '').trim().toLowerCase();
        return t === 'close' || a === 'close' || a.includes('close');
      });
      if (target) {
        target.click();
        return true;
      }
      return false;
    })()"""
    clicked = bool(await page.eval(close_expr))
    if clicked:
        await asyncio.sleep(0.8)
    return clicked


async def _close_gemini_side_panel(page: CdpPage) -> bool:
    """
    Close Gemini side panel if open, so file overview region can populate.
    """
    expr = """(() => {
      const body = document.body;
      if (!body) return false;
      const text = (body.innerText || '').toLowerCase();
      const hasGeminiPanel = text.includes('gemini in workspace can make mistakes')
        || text.includes('ask a question about this file')
        || text.includes('ask gemini');
      if (!hasGeminiPanel) return false;

      const candidates = [...document.querySelectorAll('button,[role="button"]')];
      // Click the most likely close action (prefer exact "Close").
      const target = candidates.find((el) => {
        const t = (el.innerText || '').trim().toLowerCase();
        const a = (el.getAttribute('aria-label') || '').trim().toLowerCase();
        return t === 'close' || a === 'close';
      }) || candidates.find((el) => {
        const a = (el.getAttribute('aria-label') || '').trim().toLowerCase();
        return a.includes('close');
      });
      if (target) {
        target.click();
        return true;
      }
      return false;
    })()"""
    clicked = bool(await page.eval(expr))
    if clicked:
        await asyncio.sleep(0.8)
    return clicked


async def _trigger_summary_prompt(page: CdpPage) -> bool:
    """Click suggestion prompt to force summary generation if available."""
    expr = """(() => {
      const candidates = [...document.querySelectorAll('button,[role="button"],div[role="button"]')];
      const target = candidates.find((el) => {
        const t = (el.innerText || '').trim().toLowerCase();
        return t.includes('list the main points for this file') || t.includes('summarize this file');
      });
      if (target) {
        target.click();
        return true;
      }
      return false;
    })()"""
    ok = bool(await page.eval(expr))
    if ok:
        await asyncio.sleep(1.0)
    return ok


async def _ask_gemini_question(page: CdpPage, prompt: str) -> bool:
    prompt_json = json.dumps(prompt)
    expr = """(() => {
      const q = __PROMPT_JSON__;
      const norm = (s) => (s || '').trim().toLowerCase();
      const visible = (el) => {
        if (!el) return false;
        const r = el.getBoundingClientRect();
        return r.width > 0 && r.height > 0;
      };
      let input = null;
      const candidates = [
        ...document.querySelectorAll('textarea'),
        ...document.querySelectorAll('[contenteditable="true"]'),
        ...document.querySelectorAll('div[role="textbox"]'),
        ...document.querySelectorAll('input[type="text"]')
      ].filter(visible);
      input = candidates.find((el) => {
        const a = norm(el.getAttribute('aria-label'));
        const p = norm(el.getAttribute('placeholder'));
        return a.includes('ask')
          || a.includes('question')
          || a.includes('gemini')
          || a.includes('ถาม')
          || a.includes('คำถาม')
          || p.includes('ask')
          || p.includes('question')
          || p.includes('ถาม')
          || p.includes('คำถาม');
      }) || candidates[0] || null;
      if (!input) return false;

      if (input.tagName === 'TEXTAREA' || input.tagName === 'INPUT') {
        input.focus();
        input.value = q;
        input.dispatchEvent(new Event('input', { bubbles: true }));
        input.dispatchEvent(new Event('change', { bubbles: true }));
      } else {
        input.focus();
        input.textContent = q;
        input.dispatchEvent(new InputEvent('input', { bubbles: true, data: q, inputType: 'insertText' }));
      }

      const buttons = [...document.querySelectorAll('button,[role="button"]')].filter(visible);
      const sendBtn = buttons.find((el) => {
        const t = norm(el.innerText);
        const a = norm(el.getAttribute('aria-label'));
        return a.includes('send')
          || a.includes('submit')
          || a.includes('ส่ง')
          || a.includes('ถาม')
          || t === 'submit'
          || t === 'send'
          || t === 'ส่ง'
          || t === 'ถาม'
          || t.includes('ask')
          || t.includes('gemini');
      });
      let sent = false;
      if (sendBtn) {
        sendBtn.click();
        sent = true;
      }
      const evDown = new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true });
      const evPress = new KeyboardEvent('keypress', { key: 'Enter', code: 'Enter', bubbles: true });
      const evUp = new KeyboardEvent('keyup', { key: 'Enter', code: 'Enter', bubbles: true });
      input.dispatchEvent(evDown);
      input.dispatchEvent(evPress);
      input.dispatchEvent(evUp);
      return sent || true;
    })()"""
    expr = expr.replace("__PROMPT_JSON__", prompt_json)
    ok = bool(await page.eval(expr))
    if ok:
        await asyncio.sleep(1.0)
    return ok


async def _gemini_has_retry(page: CdpPage) -> bool:
    """Check if Gemini response is complete (Retry/View more visible) or failed (Something went wrong)."""
    expr = """(() => {
      const t = (document.body?.innerText || '').toLowerCase();
      // Success indicators: Retry button appears after response
      const hasRetry = t.includes('retry') || t.includes('view more') || t.includes('show fewer');
      // Error indicators: Gemini failed
      const hasError = t.includes('something went wrong') || t.includes('try again') && !t.includes('try again.');
      // Loading indicator: still generating
      const isLoading = t.includes('generating') || t.includes('thinking');
      return hasRetry || hasError;
    })()"""
    return bool(await page.eval(expr))


async def _gemini_has_error(page: CdpPage) -> bool:
    """Check if Gemini returned an error."""
    expr = """(() => {
      const t = (document.body?.innerText || '').toLowerCase();
      return t.includes('something went wrong') || (t.includes('try again') && t.includes('went wrong'));
    })()"""
    return bool(await page.eval(expr))


async def _click_try_again(page: CdpPage) -> bool:
    """Click 'Try again' button when Gemini errors."""
    expr = """(() => {
      const buttons = [...document.querySelectorAll('button,[role="button"],div[role="button"]')];
      const tryAgain = buttons.find(el => {
        const t = (el.innerText || '').trim().toLowerCase();
        const a = (el.getAttribute('aria-label') || '').trim().toLowerCase();
        return t === 'try again' || a.includes('try again');
      });
      if (tryAgain) {
        tryAgain.click();
        return true;
      }
      return false;
    })()"""
    clicked = bool(await page.eval(expr))
    if clicked:
        await asyncio.sleep(1.0)
    return clicked


async def _extract_gemini_response_json(page: CdpPage) -> str:
    """Try to extract JSON specifically from Gemini response area, not UI elements."""
    expr = """(() => {
      // Find Gemini response container - typically after "View" and before "Gemini in Workspace"
      const body = document.body?.innerText || '';
      const lines = body.split('\\n');

      // Look for JSON-like content between response markers
      let inResponse = false;
      let responseText = '';

      for (const line of lines) {
        const trimmed = line.trim();
        // Skip UI elements
        if (trimmed.includes('File') && trimmed.includes('View') && trimmed.includes('Tools')) continue;
        if (trimmed.includes('Ask Gemini')) continue;
        if (trimmed.includes('More options')) continue;
        if (trimmed === 'Gemini' || trimmed === 'View' || trimmed === 'Close') continue;
        if (trimmed.includes('Gemini in Workspace')) break;

        // Start capturing after we see the question or Edit text
        if (trimmed.includes('Edit text') || trimmed.startsWith('{') || trimmed.startsWith('[')) {
          inResponse = true;
        }

        if (inResponse) {
          responseText += line + '\\n';
        }
      }

      // Extract first JSON object from response
      const start = responseText.indexOf('{');
      if (start < 0) return '';
      let depth = 0;
      let inStr = false;
      let escaped = false;

      for (let i = start; i < responseText.length; i++) {
        const ch = responseText[i];
        if (inStr) {
          if (escaped) escaped = false;
          else if (ch === '\\\\') escaped = true;
          else if (ch === '"') inStr = false;
          continue;
        }
        if (ch === '"') { inStr = true; continue; }
        if (ch === '{') depth++;
        else if (ch === '}') {
          depth--;
          if (depth === 0) {
            return responseText.slice(start, i + 1);
          }
        }
      }
      return '';
    })()"""
    result = await page.eval(expr)
    return str(result) if result else ""


def _is_valid_gemini_json(json_text: str) -> bool:
    """Check if extracted JSON looks like a valid Gemini response, not UI noise."""
    if not json_text:
        return False
    try:
        obj = json.loads(json_text)
        if not isinstance(obj, dict):
            return False

        # Reject tiny objects that look like UI noise
        if len(obj) <= 3 and len(json_text) < 150:
            # Check if it's just noise like {"party_number": "ด", ...}
            keys = list(obj.keys())
            values = list(obj.values())

            # Reject if any key is too short (< 3 chars)
            if any(len(str(k)) < 3 for k in keys):
                return False

            # Reject if values look like UI noise:
            # - Single character values (e.g., "ด")
            # - Non-numeric, single-word Thai strings that aren't vote counts
            for v in values:
                v_str = str(v).strip()
                if len(v_str) <= 2:
                    # Single or double char values are noise
                    return False
                # Check if it's just a Thai word without numbers (likely party name metadata)
                # Valid vote data should have numbers
                if not any(c.isdigit() for c in v_str):
                    # No digits in value - could be noise
                    # But allow if object is large enough (detailed response)
                    if len(obj) <= 2:
                        return False

        return True
    except Exception:
        return False


async def _gemini_has_prompt_echo(page: CdpPage, probe: str) -> bool:
    expr = f"""(() => {{
      const t = (document.body?.innerText || '');
      return t.includes({json.dumps(probe)});
    }})()"""
    return bool(await page.eval(expr))


async def _ask_gemini_json(
    ws_url: str,
    prompt: str,
    wait_seconds: int = 20,
    max_chars: int = 120000,
) -> tuple[str, str, str, str]:
    """Ask Gemini a question and extract JSON response.

    Returns (url, title, json_text, raw_text).
    json_text is the extracted JSON object, or empty string if not found.
    raw_text is the full page text for debugging.
    """
    # Simpler fallback prompts if main prompt fails
    simple_prompts = [
        "List the vote counts as key:value pairs, one per line",
        "What are the main numbers in this document?",
        "Summarize this document briefly"
    ]

    async with CdpPage(ws_url) as page:
        for _ in range(20):
            url = str(await page.eval("location.href") or "")
            if "drive.google.com/" in url:
                break
            await asyncio.sleep(0.4)

        for _ in range(20):
            state = str(await page.eval("document.readyState") or "")
            if state == "complete":
                break
            await asyncio.sleep(0.4)

        # Ensure Gemini panel is open and question UI available.
        prompt_probe = prompt[:24]
        await _open_gemini_panel(page)
        await asyncio.sleep(1.5)

        # Check if Gemini has an error state from previous attempt
        if await _gemini_has_error(page):
            await _close_gemini_side_panel(page)
            await asyncio.sleep(0.5)
            await _open_gemini_panel(page)
            await asyncio.sleep(1.0)

        # Try main prompt, then simpler fallbacks if errors occur
        prompts_to_try = [prompt] + simple_prompts
        last_text = ""
        best_json = ""

        for attempt_idx, current_prompt in enumerate(prompts_to_try):
            current_probe = current_prompt[:24]

            # Avoid duplicate sends in the same tab/session:
            already_has_prompt = await _gemini_has_prompt_echo(page, current_probe)
            already_done = already_has_prompt and await _gemini_has_retry(page)

            if not already_done:
                # If error from previous attempt, try clicking "Try again" first
                if await _gemini_has_error(page):
                    await _click_try_again(page)
                    await asyncio.sleep(1.0)
                    # Clear the prompt area and send new one
                    await _ask_gemini_question(page, current_prompt)
                else:
                    await _ask_gemini_question(page, current_prompt)
                await asyncio.sleep(2.0)

            deadline = time.time() + max(3, int(wait_seconds))
            error_detected = False

            while time.time() < deadline:
                raw_text = str(await page.eval(f"document.body ? document.body.innerText.slice(0, {max_chars}) : ''") or "")
                if raw_text:
                    last_text = raw_text

                    # Check for error state
                    if await _gemini_has_error(page):
                        error_detected = True
                        break

                    # Try to extract JSON from Gemini response area specifically
                    gemini_json = await _extract_gemini_response_json(page)
                    if gemini_json and _is_valid_gemini_json(gemini_json):
                        best_json = gemini_json
                        await asyncio.sleep(1.0)
                        if await _gemini_has_retry(page):
                            break
                    else:
                        # Fallback: extract from full page
                        js = _extract_first_json_object(raw_text)
                        if js and _is_valid_gemini_json(js):
                            best_json = js

                    # Stop if response is complete
                    if await _gemini_has_retry(page):
                        break
                elif await _gemini_has_retry(page):
                    break
                await asyncio.sleep(1.0)

            # If we got valid JSON, we're done
            if best_json and _is_valid_gemini_json(best_json):
                break
            # If no error but also no JSON, still done (got text response)
            if not error_detected:
                break
            # Otherwise, try simpler prompt
            print(f"Retry {attempt_idx + 1}/{len(prompts_to_try)}: trying simpler prompt...")

        url = str(await page.eval("location.href") or "")
        title = str(await page.eval("document.title") or "")
        return url, title, best_json, last_text


def _looks_like_ui_only(raw_text: str) -> bool:
    text = (raw_text or "").strip()
    if not text:
        return True
    lowered = text.lower()
    ui_tokens = [
        "file\nview\ntools\nhelp",
        "ask gemini",
        "download",
        "hide file header",
        "hide thumbnails",
        "hide navigation pane",
        "more options",
    ]
    if len(text) < 220 and sum(1 for t in ui_tokens if t in lowered) >= 2:
        return True
    return False


async def _read_gemini(
    ws_url: str,
    max_chars: int = 60000,
    wait_overview_seconds: int = 25,
    require_overview: bool = False,
) -> tuple[str, str, str, str]:
    async with CdpPage(ws_url) as page:
        # Wait until tab navigates to a Drive page (new tabs can start at about:blank).
        url = ""
        for _ in range(20):
            url = str(await page.eval("location.href") or "")
            if "drive.google.com/" in url:
                break
            await asyncio.sleep(0.5)

        # Then wait for viewer to stabilize.
        for _ in range(20):
            state = str(await page.eval("document.readyState") or "")
            url = str(await page.eval("location.href") or "")
            if state == "complete" and "drive.google.com/" in url:
                break
            await asyncio.sleep(0.5)

        title = str(await page.eval("document.title") or "")

        # Prefer closing Gemini side panel first (lets overview section populate).
        await _close_gemini_side_panel(page)
        await _close_question_view(page)

        deadline = time.time() + max(3, int(wait_overview_seconds))
        best_raw = ""
        best_summary = ""
        tick = 0
        fallback_triggered = False
        while True:
            tick += 1
            if tick % 4 == 0:
                await _close_gemini_side_panel(page)
                await _close_question_view(page)
            if tick == 6 and not fallback_triggered:
                # Fallback: briefly open Gemini and prompt summary if still blank.
                await _open_gemini_panel(page)
                await _close_question_view(page)
                await _trigger_summary_prompt(page)
                await _close_gemini_side_panel(page)
                fallback_triggered = True
            raw_text = str(await page.eval(f"document.body ? document.body.innerText.slice(0, {max_chars}) : ''") or "")
            summary = _extract_gemini_summary_text(raw_text)
            if raw_text and (not _looks_like_ui_only(raw_text)):
                best_raw = raw_text
            if summary and len(summary.strip()) >= 60:
                best_summary = summary.strip()
                best_raw = raw_text
                break
            if time.time() >= deadline:
                break
            await asyncio.sleep(1.0)

        if require_overview and not best_summary:
            # Keep last visible content for diagnostics even if summary is missing.
            raw_text = str(await page.eval(f"document.body ? document.body.innerText.slice(0, {max_chars}) : ''") or "")
            return url, title, "", raw_text

        if best_summary:
            return url, title, best_summary, best_raw or raw_text

        # Fallback to latest text if summary never appeared.
        raw_text = str(await page.eval(f"document.body ? document.body.innerText.slice(0, {max_chars}) : ''") or "")
        return url, title, "", best_raw or raw_text


async def _list_file_rows(ws_url: str) -> list[dict[str, Any]]:
    rows_data = await _list_rows(ws_url)
    rows = rows_data.get("rows", [])
    if not isinstance(rows, list):
        return []
    return [r for r in rows if isinstance(r, dict) and r.get("is_file")]


def _parse_rows_arg(rows_raw: str | None) -> list[int]:
    if not rows_raw:
        return []
    out: list[int] = []
    for token in rows_raw.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            n = int(token)
        except Exception:
            continue
        if n > 0:
            out.append(n)
    return sorted(set(out))


def _drive_file_targets(targets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for t in targets:
        if t.get("type") != "page":
            continue
        url = str(t.get("url", ""))
        if "drive.google.com/file/d/" in url and t.get("webSocketDebuggerUrl"):
            out.append(t)
    return out


async def _record_target_to_mapping(
    ws_url: str,
    *,
    mapping_file: str,
    local_path: str | None = None,
    folder_path: list[str] | None = None,
    wait_overview_seconds: int = 25,
    require_overview: bool = False,
) -> dict[str, Any]:
    url, title, summary, raw_text = await _read_gemini(
        ws_url,
        wait_overview_seconds=wait_overview_seconds,
        require_overview=require_overview,
    )
    drive_id = _extract_drive_file_id(url)
    if not drive_id:
        return {"ok": False, "reason": "not_file_tab", "url": url, "title": title}
    name = _display_name_from_title(title, drive_id)
    entry = upsert_mapping_entry(
        drive_id=drive_id,
        drive_url=url,
        name=name,
        local_path=local_path,
        folder_path=folder_path if folder_path else None,
        gemini_summary=summary,
        gemini_raw_overview=raw_text,
        mapping_path=mapping_file,
    )
    return {"ok": True, "drive_id": drive_id, "name": name, "url": url, "entry": entry}


def _fetch_file_overview_via_tab(
    devtools_url: str,
    file_meta: dict[str, Any],
    wait_overview_seconds: int = 25,
    require_overview: bool = True,
    retries: int = 2,
) -> dict[str, Any]:
    """Open one file in new tab, fetch raw overview text, then close tab."""
    attempts = max(1, int(retries) + 1)
    last_error: dict[str, Any] = {"ok": False, "reason": "unknown", "file": file_meta}
    for attempt in range(1, attempts + 1):
        tab = _open_url_in_new_tab(devtools_url, str(file_meta.get("drive_url", "")))
        if not tab:
            last_error = {"ok": False, "reason": "open_failed", "file": file_meta, "attempt": attempt}
            continue
        tid = str(tab.get("id", ""))
        ws = str(tab.get("webSocketDebuggerUrl", ""))
        if not tid or not ws:
            if tid:
                _close_target(devtools_url, tid)
            last_error = {"ok": False, "reason": "missing_ws", "file": file_meta, "attempt": attempt}
            continue
        try:
            url, title, summary, raw_text = asyncio.run(
                _read_gemini(
                    ws,
                    wait_overview_seconds=wait_overview_seconds,
                    require_overview=require_overview,
                )
            )
            drive_id = _extract_drive_file_id(url) or str(file_meta.get("drive_id", ""))
            if not drive_id:
                last_error = {"ok": False, "reason": "not_file_tab", "file": file_meta, "url": url, "attempt": attempt}
                continue
            if require_overview and not summary:
                last_error = {
                    "ok": False,
                    "reason": "overview_timeout",
                    "file": file_meta,
                    "url": url,
                    "raw_text": raw_text,
                    "attempt": attempt,
                }
                continue
            name = _display_name_from_title(title, drive_id)
            return {
                "ok": True,
                "file": file_meta,
                "drive_id": drive_id,
                "drive_url": url or str(file_meta.get("drive_url", "")),
                "name": name,
                "summary": summary,
                "raw_text": raw_text,
                "attempt": attempt,
            }
        except Exception as exc:
            last_error = {"ok": False, "reason": f"read_error:{exc}", "file": file_meta, "attempt": attempt}
        finally:
            _close_target(devtools_url, tid)
        # Small delay before retrying timeout/failure paths.
        time.sleep(0.8)
    return last_error


async def _crawl_collect_files(
    ws_url: str,
    folder_id: str,
    breadcrumb: list[str],
    visited: set[str],
    out_files: list[dict[str, Any]],
    max_files: int = 0,
    on_file=None,
) -> None:
    if folder_id in visited:
        return
    visited.add(folder_id)
    await _goto_url(ws_url, f"https://drive.google.com/drive/folders/{folder_id}", sleep_s=2.0)
    print(f"Scanning folder: {folder_id} ({'/'.join(breadcrumb) if breadcrumb else 'root'})")
    listed = await _list_rows(ws_url)
    rows = listed.get("rows", [])
    if not isinstance(rows, list):
        return

    files: list[dict[str, Any]] = []
    folders: list[dict[str, Any]] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        if r.get("is_folder"):
            folders.append(r)
        elif r.get("is_file"):
            files.append(r)

    for f in files:
        fid = str(f.get("id", "")).strip()
        fname = str(f.get("name", "")).strip()
        if not fid or not fname:
            continue
        out_files.append(
            {
                "drive_id": fid,
                "name": fname,
                "folder_path": list(breadcrumb),
                "drive_url": f"https://drive.google.com/file/d/{fid}/view",
            }
        )
        if on_file is not None:
            try:
                on_file(out_files)
            except Exception:
                pass
        if max_files and len(out_files) >= max_files:
            return

    for d in folders:
        did = str(d.get("id", "")).strip()
        dname = str(d.get("name", "")).strip()
        if not did or not dname:
            continue
        if max_files and len(out_files) >= max_files:
            return
        await _crawl_collect_files(
            ws_url=ws_url,
            folder_id=did,
            breadcrumb=[*breadcrumb, dname],
            visited=visited,
            out_files=out_files,
            max_files=max_files,
            on_file=on_file,
        )


def _extract_folder_id(url: str) -> str:
    match = re.search(r"/drive/folders/([0-9A-Za-z_-]{10,})", url or "")
    return match.group(1) if match else ""


def _extract_drive_file_id(url: str) -> str:
    match = re.search(r"/file/d/([0-9A-Za-z_-]{10,})", url or "")
    return match.group(1) if match else ""


def _url_to_drive_id(url: str) -> str:
    patterns = [
        r"/file/d/([0-9A-Za-z_-]{10,})",
        r"/folders/([0-9A-Za-z_-]{10,})",
        r"[?&]id=([0-9A-Za-z_-]{10,})",
    ]
    for p in patterns:
        m = re.search(p, url or "", flags=re.IGNORECASE)
        if m:
            return m.group(1)
    return ""


def _is_folder_url(url: str) -> bool:
    return "/folders/" in (url or "").lower()


def _is_file_url(url: str) -> bool:
    u = (url or "").lower()
    return "/file/" in u or "/document/d/" in u or "/presentation/d/" in u or "/spreadsheets/d/" in u


def _discover_files_public(root_folder_id: str, limit: int = 0) -> list[dict[str, Any]]:
    """
    Programmatic Drive discovery without browser traversal.
    Works for publicly listed/shared folders via embeddedfolderview.
    """
    out_files: list[dict[str, Any]] = []
    visited: set[str] = set()
    stack: list[tuple[str, list[str]]] = [(root_folder_id, [])]
    while stack:
        folder_id, breadcrumb = stack.pop()
        if folder_id in visited:
            continue
        visited.add(folder_id)
        print(f"Public-scan folder: {folder_id} ({'/'.join(breadcrumb) if breadcrumb else 'root'})")
        url = PUBLIC_FOLDER_URL.format(id=folder_id)
        try:
            with urllib.request.urlopen(url, timeout=15) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
        except Exception:
            continue
        matches = re.findall(PUBLIC_ITEM_RE, html)
        for item_url, item_name, _modified in matches:
            did = _url_to_drive_id(item_url)
            if not did:
                continue
            clean_name = str(item_name).strip()
            if _is_folder_url(item_url):
                stack.append((did, [*breadcrumb, clean_name]))
            elif _is_file_url(item_url):
                out_files.append(
                    {
                        "drive_id": did,
                        "name": clean_name,
                        "folder_path": list(breadcrumb),
                        "drive_url": f"https://drive.google.com/file/d/{did}/view",
                    }
                )
                if len(out_files) % 100 == 0:
                    print(f"Public-scan progress: {len(out_files)} files discovered")
                if limit and len(out_files) >= limit:
                    return out_files
    return out_files


def _display_name_from_title(title: str, drive_id: str) -> str:
    clean = (title or "").strip()
    suffix = " - Google Drive"
    if clean.endswith(suffix):
        clean = clean[: -len(suffix)].strip()
    return clean or drive_id


def _parse_folder_path(folder_path_raw: str | None) -> list[str]:
    if not folder_path_raw:
        return []
    raw = folder_path_raw.strip()
    if not raw:
        return []
    if "/" in raw:
        parts = [p.strip() for p in raw.split("/")]
    else:
        parts = [p.strip() for p in raw.split(",")]
    return [p for p in parts if p]


def _print_targets(targets: list[dict[str, Any]]) -> None:
    for t in targets:
        if t.get("type") != "page":
            continue
        print(f"{t.get('id')}\t{t.get('title','')}\t{t.get('url','')}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Programmatic Google Drive browser via Chrome DevTools")
    parser.add_argument(
        "command",
        choices=["targets", "list", "open", "gemini", "ask-json", "record", "open-many", "record-many", "crawl-gemini"],
        help="Action",
    )
    parser.add_argument("--devtools-url", default=DEFAULT_DEVTOOLS_URL, help="Chrome /json endpoint")
    parser.add_argument("--target-id", default=None, help="Specific DevTools target id")
    parser.add_argument("--row", type=int, default=None, help="1-based row index to open")
    parser.add_argument("--id", dest="item_id", default=None, help="Drive item id to open")
    parser.add_argument("--file", action="store_true", help="Treat --id as file id")
    parser.add_argument("--rows", default=None, help="Comma-separated row list, e.g. 1,3,5")
    parser.add_argument("--limit", type=int, default=0, help="Max number of items for batch commands")
    parser.add_argument("--workers", type=int, default=3, help="Parallel browser workers for crawl-gemini")
    parser.add_argument("--wait-overview-seconds", type=int, default=25, help="Seconds to wait for Gemini overview per file")
    parser.add_argument("--wait-answer-seconds", type=int, default=22, help="Seconds to wait for Gemini answer when using ask-json")
    parser.add_argument(
        "--question",
        default=(
            'ตอบเป็น JSON เท่านั้น: {"province":"...","district_number":0,"form_type":"constituency|party_list","total":0,"valid":0,"invalid":0,"blank":0,'
            '"votes":{"1":0,"2":0},"notes":"..."} โดยห้ามมีข้อความอื่นนอกจาก JSON'
        ),
        help="Question prompt for ask-json command",
    )
    parser.add_argument("--overview-retries", type=int, default=2, help="Retries per file when overview is missing")
    parser.add_argument("--require-overview", dest="require_overview", action="store_true", help="Fail file if overview did not populate")
    parser.add_argument("--allow-ui-fallback", dest="require_overview", action="store_false", help="Allow saving UI-only fallback text")
    parser.set_defaults(require_overview=True)
    parser.add_argument(
        "--discovery-mode",
        choices=["browser", "public"],
        default="public",
        help="How to discover files for crawl-gemini",
    )
    parser.add_argument("--mapping-file", default=DEFAULT_MAPPING_FILE, help="Path to mapping JSON")
    parser.add_argument("--output-file", default="drive_ai_overview_raw.jsonl", help="Output file for raw extracted overviews")
    parser.add_argument("--state-file", default="drive_ai_overview_state.json", help="Resume state file for crawl-gemini")
    parser.add_argument("--root-folder-id", default=None, help="Explicit Drive root folder id for crawl-gemini")
    parser.add_argument("--resume", dest="resume", action="store_true", help="Resume from state/output (default)")
    parser.add_argument("--no-resume", dest="resume", action="store_false", help="Ignore previous state/output and restart")
    parser.set_defaults(resume=True)
    parser.add_argument("--local-path", default=None, help="Local file path for this Drive file")
    parser.add_argument(
        "--folder-path",
        default=None,
        help="Optional folder breadcrumb path, e.g. 'Phrae/เขตเลือกตั้งที่ 1/อำเภอสูงเม่น'",
    )
    args = parser.parse_args()

    try:
        targets = _fetch_targets(args.devtools_url)
    except Exception as exc:
        print(f"ERROR: cannot fetch DevTools targets: {exc}")
        return 1

    if args.command == "targets":
        _print_targets(targets)
        return 0

    target = _pick_target(targets, target_id=args.target_id)
    if not target:
        print("ERROR: no suitable Drive tab target found")
        return 1
    ws_url = str(target.get("webSocketDebuggerUrl", ""))
    if not ws_url:
        print("ERROR: selected target has no websocket URL")
        return 1

    if args.command == "list":
        data = asyncio.run(_list_rows(ws_url))
        print(f"URL: {data['url']}")
        print(f"TITLE: {data['title']}")
        rows = data["rows"]
        if not rows:
            print("No folder rows found on current page.")
            return 0
        for r in rows:
            kind = "DIR" if r.get("is_folder") else "FILE"
            print(f"[{r['row']:03}] {kind} id={r['id']} name={r['name']}")
        return 0

    if args.command == "open":
        try:
            new_url = asyncio.run(_navigate(ws_url, row=args.row, item_id=args.item_id, as_file=args.file))
        except Exception as exc:
            print(f"ERROR: {exc}")
            return 1
        print(f"Opened: {new_url}")
        return 0

    if args.command == "gemini":
        url, title, summary, raw_text = asyncio.run(
            _read_gemini(
                ws_url,
                wait_overview_seconds=args.wait_overview_seconds,
                require_overview=False,
            )
        )
        print(f"URL: {url}")
        print(f"TITLE: {title}")
        print("---")
        print(raw_text if raw_text else summary)
        return 0

    if args.command == "ask-json":
        url, title, parsed_json_text, raw_text = asyncio.run(
            _ask_gemini_json(
                ws_url,
                prompt=args.question,
                wait_seconds=args.wait_answer_seconds,
            )
        )
        # Auto-retry once with minimal Thai prompt when first result is weak.
        if _json_needs_retry(parsed_json_text):
            retry_url, retry_title, retry_json, retry_raw = asyncio.run(
                _ask_gemini_json(
                    ws_url,
                    prompt=".อ่านทีละบรรทัด",
                    wait_seconds=args.wait_answer_seconds,
                )
            )
            if not _json_needs_retry(retry_json):
                url, title, parsed_json_text, raw_text = retry_url, retry_title, retry_json, retry_raw
        print(f"URL: {url}")
        print(f"TITLE: {title}")
        print("---")
        print(parsed_json_text if parsed_json_text else raw_text)
        return 0

    if args.command == "record":
        url, title, summary, raw_text = asyncio.run(
            _read_gemini(
                ws_url,
                wait_overview_seconds=args.wait_overview_seconds,
                require_overview=args.require_overview,
            )
        )
        drive_id = _extract_drive_file_id(url)
        if not drive_id:
            print("ERROR: current tab is not a Drive file page (/file/d/<id>/view).")
            return 1
        if args.require_overview and not summary:
            print("ERROR: Gemini overview did not populate before timeout.")
            return 1
        name = _display_name_from_title(title, drive_id)
        folder_path = _parse_folder_path(args.folder_path)
        entry = upsert_mapping_entry(
            drive_id=drive_id,
            drive_url=url,
            name=name,
            local_path=args.local_path,
            folder_path=folder_path if folder_path else None,
            gemini_summary=summary,
            gemini_raw_overview=raw_text,
            mapping_path=args.mapping_file,
        )
        print(f"Recorded: {drive_id}")
        print(f"Mapping: {args.mapping_file}")
        print(json.dumps(entry, ensure_ascii=False, indent=2))
        return 0

    if args.command == "open-many":
        # Needs a folder listing page target.
        file_rows = asyncio.run(_list_file_rows(ws_url))
        if not file_rows:
            print("No file rows found on current page. Open a Drive folder page first.")
            return 1
        wanted_rows = _parse_rows_arg(args.rows)
        selected: list[dict[str, Any]] = []
        if wanted_rows:
            rows_by_idx = {int(r["row"]): r for r in file_rows if "row" in r}
            for idx in wanted_rows:
                row = rows_by_idx.get(idx)
                if row:
                    selected.append(row)
        else:
            selected = list(file_rows)
        if args.limit and args.limit > 0:
            selected = selected[: args.limit]
        if not selected:
            print("No matching file rows selected.")
            return 1
        opened = 0
        for r in selected:
            fid = str(r.get("id", ""))
            name = str(r.get("name", ""))
            if not fid:
                continue
            url = f"https://drive.google.com/file/d/{fid}/view"
            new_tab = _open_url_in_new_tab(args.devtools_url, url)
            if new_tab:
                opened += 1
                print(f"Opened tab: id={new_tab.get('id','?')} file_id={fid} name={name}")
            else:
                print(f"Failed to open tab for file_id={fid} name={name}")
        print(f"Opened {opened}/{len(selected)} tabs.")
        return 0 if opened > 0 else 1

    if args.command == "record-many":
        all_targets = _fetch_targets(args.devtools_url)
        file_targets = _drive_file_targets(all_targets)
        if not file_targets:
            print("No open Drive file tabs found.")
            return 1
        if args.limit and args.limit > 0:
            file_targets = file_targets[: args.limit]

        async def run_batch():
            results = []
            for t in file_targets:
                ws = str(t.get("webSocketDebuggerUrl", ""))
                if not ws:
                    continue
                result = await _record_target_to_mapping(
                    ws,
                    mapping_file=args.mapping_file,
                    local_path=None,  # batch mode: unknown local mapping per tab
                    folder_path=_parse_folder_path(args.folder_path),
                    wait_overview_seconds=args.wait_overview_seconds,
                    require_overview=args.require_overview,
                )
                results.append(result)
            return results

        results = asyncio.run(run_batch())
        ok = 0
        for r in results:
            if r.get("ok"):
                ok += 1
                print(f"Recorded: {r.get('drive_id')} {r.get('name')}")
            else:
                print(f"Skipped: {r.get('reason')} {r.get('url')}")
        print(f"Recorded {ok}/{len(results)} open file tabs into {args.mapping_file}")
        return 0 if ok > 0 else 1

    if args.command == "crawl-gemini":
        root_folder_id = (args.root_folder_id or "").strip()
        if not root_folder_id:
            root_url = str(target.get("url", ""))
            root_folder_id = _extract_folder_id(root_url)
        if not root_folder_id:
            print("ERROR: no root folder id found. Open a folder tab or pass --root-folder-id.")
            return 1

        state_path = args.state_file
        found_files: list[dict[str, Any]] = []
        next_index = 0
        if args.resume:
            try:
                with open(state_path, "r", encoding="utf-8") as sf:
                    state = json.load(sf)
                if (
                    isinstance(state, dict)
                    and str(state.get("root_folder_id", "")) == root_folder_id
                    and isinstance(state.get("files"), list)
                ):
                    found_files = [x for x in state.get("files", []) if isinstance(x, dict)]
                    next_index = int(state.get("next_index", 0) or 0)
                    print(f"Loaded state: {len(found_files)} files, next_index={next_index}")
            except Exception:
                pass

        if not found_files:
            def _save_discovery_state(current_files: list[dict[str, Any]]) -> None:
                with open(state_path, "w", encoding="utf-8") as sf:
                    json.dump(
                        {
                            "root_folder_id": root_folder_id,
                            "files": current_files,
                            "next_index": 0,
                            "updated_at_epoch": int(time.time()),
                        },
                        sf,
                        ensure_ascii=False,
                        indent=2,
                    )

            print(f"Crawling folders from root={root_folder_id} (mode={args.discovery_mode}) ...")
            if args.discovery_mode == "public":
                found_files = _discover_files_public(
                    root_folder_id,
                    limit=args.limit if args.limit and args.limit > 0 else 0,
                )
                _save_discovery_state(found_files)
            else:
                worker_tab = _open_url_in_new_tab(args.devtools_url, f"https://drive.google.com/drive/folders/{root_folder_id}")
                if not worker_tab:
                    print("ERROR: cannot open worker tab for browser crawl")
                    return 1
                worker_id = str(worker_tab.get("id", ""))
                worker_ws = str(worker_tab.get("webSocketDebuggerUrl", ""))
                if not worker_id or not worker_ws:
                    print("ERROR: worker tab missing id/websocket")
                    return 1
                try:
                    asyncio.run(
                        _crawl_collect_files(
                            ws_url=worker_ws,
                            folder_id=root_folder_id,
                            breadcrumb=[],
                            visited=set(),
                            out_files=found_files,
                            max_files=args.limit if args.limit and args.limit > 0 else 0,
                            on_file=lambda rows: _save_discovery_state(rows),
                        )
                    )
                finally:
                    _close_target(args.devtools_url, worker_id)
                _save_discovery_state(found_files)

        print(f"Found {len(found_files)} file(s).")
        if not found_files:
            return 1

        # Build done set for resumable dedupe.
        done_ids: set[str] = set()
        if args.resume:
            try:
                with open(args.output_file, "r", encoding="utf-8") as f_in:
                    for line in f_in:
                        line = line.strip()
                        if not line:
                            continue
                        obj = json.loads(line)
                        did = str(obj.get("drive_id", "")).strip()
                        raw = str(obj.get("raw_ai_overview", "") or "").strip()
                        if did and raw:
                            done_ids.add(did)
            except Exception:
                pass
            try:
                with open(args.mapping_file, "r", encoding="utf-8") as mf:
                    mapping = json.load(mf)
                files_map = mapping.get("files", {}) if isinstance(mapping, dict) else {}
                if isinstance(files_map, dict):
                    for did, entry in files_map.items():
                        if not isinstance(entry, dict):
                            continue
                        if str(entry.get("gemini_raw_overview", "")).strip():
                            done_ids.add(str(did))
            except Exception:
                pass

        start_i = max(0, next_index)
        if args.resume and start_i >= len(found_files):
            # Full pass already completed once; rescan from start to backfill missing/empty items.
            start_i = 0
        queue: list[tuple[int, dict[str, Any]]] = []
        skipped_done = 0
        skipped_indices: set[int] = set()
        for i in range(start_i, len(found_files)):
            f = found_files[i]
            did = str(f.get("drive_id", "")).strip()
            if args.resume and did and did in done_ids:
                skipped_done += 1
                skipped_indices.add(i)
                continue
            queue.append((i, f))

        contiguous_done: set[int] = set(skipped_indices)
        progress_next = start_i
        while progress_next in contiguous_done:
            progress_next += 1

        with open(state_path, "w", encoding="utf-8") as sf:
            json.dump(
                {
                    "root_folder_id": root_folder_id,
                    "files": found_files,
                    "next_index": progress_next,
                    "updated_at_epoch": int(time.time()),
                },
                sf,
                ensure_ascii=False,
                indent=2,
            )

        if not queue:
            print("Nothing new to extract (all files already done).")
            print(f"State saved at {state_path}")
            return 0

        saved = 0
        failed = 0
        progress_done = 0
        lock = threading.Lock()
        started = time.time()

        def _worker(task: tuple[int, dict[str, Any]]) -> tuple[int, dict[str, Any], dict[str, Any]]:
            idx, file_item = task
            result = _fetch_file_overview_via_tab(
                args.devtools_url,
                file_item,
                wait_overview_seconds=args.wait_overview_seconds,
                require_overview=args.require_overview,
                retries=args.overview_retries,
            )
            return idx, file_item, result

        with open(args.output_file, "a", encoding="utf-8") as out:
            max_workers = max(1, int(args.workers or 1))
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
                futures = [ex.submit(_worker, task) for task in queue]
                for fut in concurrent.futures.as_completed(futures):
                    idx, f, result = fut.result()
                    with lock:
                        progress_done += 1
                        progress_next = max(progress_next, idx + 1)
                        if result.get("ok"):
                            raw = str(result.get("raw_text", "") or "")
                            summary = str(result.get("summary", "") or "")
                            drive_id = str(result.get("drive_id", "") or f.get("drive_id", ""))
                            drive_url = str(result.get("drive_url", "") or f.get("drive_url", ""))
                            name = str(result.get("name", "") or f.get("name", ""))
                            entry = upsert_mapping_entry(
                                drive_id=drive_id,
                                drive_url=drive_url,
                                name=name,
                                local_path=None,
                                folder_path=list(f.get("folder_path", [])),
                                gemini_summary=summary,
                                gemini_raw_overview=raw,
                                mapping_path=args.mapping_file,
                            )
                            out.write(
                                json.dumps(
                                    {
                                        "drive_id": drive_id,
                                        "drive_url": drive_url,
                                        "name": name,
                                        "folder_path": f.get("folder_path", []),
                                        "raw_ai_overview": str(entry.get("gemini_raw_overview", "") or ""),
                                    },
                                    ensure_ascii=False,
                                )
                                + "\n"
                            )
                            saved += 1
                            done_ids.add(drive_id)
                            contiguous_done.add(idx)
                            print(
                                f"[{progress_done}/{len(queue)} | idx={idx+1}/{len(found_files)}] "
                                f"saved: {drive_id} {name}"
                            )
                        else:
                            failed += 1
                            print(
                                f"[{progress_done}/{len(queue)} | idx={idx+1}/{len(found_files)}] "
                                f"failed: {f.get('drive_id')} {f.get('name')} ({result.get('reason')})"
                            )

                        while progress_next in contiguous_done:
                            progress_next += 1

                        with open(state_path, "w", encoding="utf-8") as sf:
                            json.dump(
                                {
                                    "root_folder_id": root_folder_id,
                                    "files": found_files,
                                    "next_index": progress_next,
                                    "updated_at_epoch": int(time.time()),
                                },
                                sf,
                                ensure_ascii=False,
                                indent=2,
                            )

        elapsed = time.time() - started
        print(
            f"Done. Saved {saved}/{len(queue)} queued files to {args.output_file} "
            f"in {elapsed:.1f}s (failed={failed}, already_done_skipped={skipped_done})"
        )
        print(f"Mapping updated at {args.mapping_file}")
        print(f"State saved at {state_path}")
        return 0 if saved > 0 else 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
