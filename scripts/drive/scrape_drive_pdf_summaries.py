#!/usr/bin/env python3
"""Scrape only Drive PDFs that already have Gemini Summary visible in UI.

Reads drive_file_mapping.json -> opens each file tab -> captures page text ->
extracts Summary block if present. Files without Summary are skipped.
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
from pathlib import Path
from typing import Any, Optional


DEFAULT_MAPPING = "drive_file_mapping.json"
DEFAULT_OUT = "drive_pdf_summary_only.jsonl"
DEFAULT_STATE = "drive_pdf_summary_only_state.json"
THAI_TO_ARABIC = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")
_OPEN_TAB_LOCK = threading.Lock()
_LAST_OPEN_AT_BY_DEVTOOLS: dict[str, float] = {}


def _load_json(path: str, fallback: Any) -> Any:
    p = Path(path)
    if not p.exists():
        return fallback
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def _save_json(path: str, obj: Any) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _open_url_in_new_tab(
    devtools_url: str,
    target_url: str,
    min_interval_seconds: float = 0.0,
) -> Optional[dict[str, Any]]:
    # Global rate limit per DevTools endpoint to avoid opening too many tabs at once.
    if min_interval_seconds > 0:
        with _OPEN_TAB_LOCK:
            now = time.time()
            last = _LAST_OPEN_AT_BY_DEVTOOLS.get(devtools_url, 0.0)
            wait_for = (last + float(min_interval_seconds)) - now
            if wait_for > 0:
                time.sleep(wait_for)
            _LAST_OPEN_AT_BY_DEVTOOLS[devtools_url] = time.time()
    base = devtools_url.rsplit("/json", 1)[0]
    encoded = urllib.parse.quote(target_url, safe=":/?=&-_")
    endpoint = f"{base}/json/new?{encoded}"
    req = urllib.request.Request(endpoint, method="PUT")
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _close_target(devtools_url: str, target_id: str) -> bool:
    base = devtools_url.rsplit("/json", 1)[0]
    endpoint = f"{base}/json/close/{target_id}"
    try:
        with urllib.request.urlopen(endpoint, timeout=8):
            return True
    except Exception:
        return False


def _extract_summary_block(text: str) -> str:
    if not text:
        return ""
    marker = "Summary"
    i = text.find(marker)
    if i < 0:
        return ""
    tail = text[i + len(marker) :].strip()
    stops = [
        "\nShow more",
        "\nShow less",
        "\nList the main points for this file",
        "\nAsk a question about this file",
        "\nAsk Gemini",
        "\nGood suggestion",
        "\nBad suggestion",
    ]
    end = len(tail)
    for s in stops:
        j = tail.find(s)
        if j >= 0:
            end = min(end, j)
    out = tail[:end].strip()
    if len(out) >= 30:
        return out

    # Fallback: Gemini chat response block (without explicit "Summary" heading)
    alt = text
    marker2 = "More options\nClose\n"
    j = alt.find(marker2)
    if j >= 0:
        tail2 = alt[j + len(marker2) :].strip()
        stops2 = [
            "\nShow more",
            "\nShow less",
            "\nList the main points for this file",
            "\nAsk a question about this file",
            "\nAsk Gemini",
            "\nGood suggestion",
            "\nBad suggestion",
            "\nPage 1 of ",
            "\nDisplaying ",
        ]
        end2 = len(tail2)
        for s in stops2:
            k = tail2.find(s)
            if k >= 0:
                end2 = min(end2, k)
        out2 = tail2[:end2].strip()
    if len(out2) >= 30:
        return out2
    return ""


def _extract_panel_answer_block(text: str) -> str:
    """Extract generic Gemini panel response text (summary or Q&A answer)."""
    if not text:
        return ""
    marker = "More options\nClose\n"
    i = text.find(marker)
    if i < 0:
        return _extract_summary_block(text)
    tail = text[i + len(marker) :].strip()
    stops = [
        "\nShow more",
        "\nShow less",
        "\nList the main points for this file",
        "\nAsk a question about this file",
        "\nAsk Gemini",
        "\nGood suggestion",
        "\nBad suggestion",
        "\nPage 1 of ",
        "\nDisplaying ",
    ]
    end = len(tail)
    for s in stops:
        j = tail.find(s)
        if j >= 0:
            end = min(end, j)
    out = tail[:end].strip()
    return out if len(out) >= 20 else ""


def _extract_answer_after_prompt(raw_text: str, prompt: str) -> str:
    """Best-effort extraction of assistant answer that appears after a user prompt."""
    if not raw_text:
        return ""
    p = (prompt or "").strip()
    if not p:
        return ""
    i = raw_text.rfind(p)
    if i < 0:
        return ""
    tail = raw_text[i + len(p) :].strip()
    if not tail:
        return ""
    stops = [
        "\nAsk Gemini",
        "\nGood suggestion",
        "\nBad suggestion",
        "\nPage 1 of ",
        "\nDisplaying ",
    ]
    end = len(tail)
    for s in stops:
        j = tail.find(s)
        if j >= 0:
            end = min(end, j)
    out = tail[:end].strip()
    return out if len(out) >= 20 else ""


def _looks_like_viewer_only_text(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return True
    # Common PDF viewer-only captures when Gemini answer was not captured.
    viewer_markers = [
        "page 1 of",
        "page 2 of",
        "displaying ",
        "download",
        "print",
        "zoom in",
        "zoom out",
    ]
    score = sum(1 for m in viewer_markers if m in t)
    has_answer_cue = (
        ("more options" in t and "close" in t)
        or ("summary" in t and len(t) > 250)
        or ("{" in t and "}" in t)
    )
    return score >= 2 and not has_answer_cue


def _extract_json_object_text(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw)
    # Direct object
    if raw.startswith("{") and raw.endswith("}"):
        try:
            json.loads(raw)
            return raw
        except Exception:
            pass
    # Find largest brace object span
    i = raw.find("{")
    j = raw.rfind("}")
    if i >= 0 and j > i:
        cand = raw[i : j + 1]
        try:
            json.loads(cand)
            return cand
        except Exception:
            return ""
    return ""


def _extract_location_hints(
    *,
    summary_text: str,
    name: str,
    folder_path: list[str] | None,
    province_fallback: str = "",
    district_fallback: int = 0,
) -> dict[str, Any]:
    folder_text = " / ".join(folder_path or [])
    merged = "\n".join([summary_text or "", name or "", folder_text]).translate(THAI_TO_ARABIC)

    unit_number = None
    committee_number = None
    district_number = district_fallback if district_fallback > 0 else None
    province = province_fallback or None

    m_dist = re.search(r"(?:เขตเลือกตั้งที่|constituency)\s*(?:no\.?|number)?\s*([0-9]{1,3})", merged, re.IGNORECASE)
    if m_dist:
        district_number = int(m_dist.group(1))

    m_unit = re.search(
        r"(?:หน่วยเลือกตั้งที่|หน่วยที่|หน่วย)\s*\(?\s*([0-9]{1,4})\s*\)?|(?:polling\s*unit|unit)\s*(?:no\.?|number)?\s*\(?\s*([0-9]{1,4})\s*\)?",
        merged,
        re.IGNORECASE,
    )
    if m_unit:
        g = m_unit.group(1) or m_unit.group(2)
        if g:
            unit_number = int(g)

    m_set = re.search(r"(?:ชุดที่|set|committee\s*set)\s*(?:no\.?|number)?\s*\(?\s*([0-9]{1,4})\s*\)?", merged, re.IGNORECASE)
    if m_set:
        committee_number = int(m_set.group(1))

    m_prov = re.search(r"(?:จังหวัด|province)\s*[:\-]?\s*([A-Za-zก-๙]+)", summary_text or "", re.IGNORECASE)
    if m_prov:
        cand = m_prov.group(1).strip()
        if cand:
            province = cand

    form_type_hint = None
    n = merged.lower().replace("ทับ", "/").replace("_", "/").replace("-", "/").replace(" ", "")
    if "5/16" in n:
        form_type_hint = "ส.ส. 5/16"
    elif "5/17" in n:
        form_type_hint = "ส.ส. 5/17"
    elif "5/18" in n:
        form_type_hint = "ส.ส. 5/18"
    if form_type_hint and re.search(r"\(บช\)|\bbch\b|บัญชีรายชื่อ|party\s*list", merged, re.IGNORECASE):
        form_type_hint = f"{form_type_hint} (บช)"

    # 5/17 typically uses committee set instead of polling unit.
    if form_type_hint in {"ส.ส. 5/17", "ส.ส. 5/17 (บช)"}:
        unit_number = None

    return {
        "province_hint": province,
        "district_number_hint": district_number,
        "unit_number_hint": unit_number,
        "committee_number_hint": committee_number,
        "form_type_hint": form_type_hint,
        "location_number_hint": committee_number if form_type_hint in {"ส.ส. 5/17", "ส.ส. 5/17 (บช)"} else unit_number,
        "location_kind_hint": "committee_number" if form_type_hint in {"ส.ส. 5/17", "ส.ส. 5/17 (บช)"} else "unit_number",
    }


async def _read_page_text(
    ws_url: str,
    max_chars: int = 70000,
    wait_seconds: int = 10,
    gemini_prompt: str = "",
    pre_ask_delay_seconds: int = 0,
) -> str:
    import websockets

    async with websockets.connect(ws_url, max_size=20_000_000) as sock:
        msg_id = 0

        async def send(method: str, params: Optional[dict] = None) -> dict:
            nonlocal msg_id
            msg_id += 1
            payload = {"id": msg_id, "method": method, "params": params or {}}
            await sock.send(json.dumps(payload))
            while True:
                raw = await asyncio.wait_for(sock.recv(), timeout=15.0)
                obj = json.loads(raw)
                if obj.get("id") == msg_id:
                    return obj

        await send("Runtime.enable")
        if not gemini_prompt:
            # Summary mode: hide Gemini side panel and prefer summary block capture.
            for _ in range(3):
                await send(
                    "Runtime.evaluate",
                    {
                        "expression": """(() => {
                      const all = [...document.querySelectorAll('button,[role="button"],div[role="button"]')];
                      const byLabel = all.find((e) => {
                        const t = (e.innerText || '').toLowerCase();
                        const a = (e.getAttribute('aria-label') || '').toLowerCase();
                        return (
                          a.includes('hide side panel') ||
                          a.includes('close side panel') ||
                          a.includes('hide panel') ||
                          a.includes('close panel') ||
                          t.includes('hide side panel') ||
                          t.includes('close panel')
                        );
                      });
                      if (byLabel) { byLabel.click(); return 'by_label'; }

                      const candidates = all.filter((e) => {
                        const r = e.getBoundingClientRect();
                        if (!r || r.width < 14 || r.height < 14) return false;
                        if (r.top < 0 || r.top > 180) return false;
                        if (r.right < window.innerWidth * 0.55) return false;
                        const s = window.getComputedStyle(e);
                        if (!s || s.visibility === 'hidden' || s.display === 'none') return false;
                        const a = (e.getAttribute('aria-label') || '').toLowerCase();
                        if (a.includes('google account') || a.includes('apps') || a.includes('help')) return false;
                        return true;
                      }).sort((a, b) => b.getBoundingClientRect().right - a.getBoundingClientRect().right);

                      if (candidates.length >= 2) {
                        candidates[1].click();
                        return 'second_right';
                      }
                      if (candidates.length === 1) {
                        candidates[0].click();
                        return 'rightmost';
                      }
                      return '';
                    })()""",
                        "returnByValue": True,
                    },
                )
                await asyncio.sleep(0.7)

            # Also toggle Ask Gemini button once to ensure Summary state refreshes.
            await send(
                "Runtime.evaluate",
                {
                    "expression": """(() => {
                  const btn = [...document.querySelectorAll('button,[role="button"],div[role="button"]')].find((e) => {
                    const t = (e.innerText || '').toLowerCase();
                    const a = (e.getAttribute('aria-label') || '').toLowerCase();
                    return t.includes('ask gemini') || a.includes('ask gemini');
                  });
                  if (btn) { btn.click(); return true; }
                  return false;
                })()""",
                    "returnByValue": True,
                },
            )
            await asyncio.sleep(0.8)

        async def click_show_more_once() -> bool:
            res = await send(
                "Runtime.evaluate",
                {
                    "expression": """(() => {
                      const btn = [...document.querySelectorAll('button,[role="button"],div[role="button"]')].find((e) => {
                        const t = (e.innerText || '').trim().toLowerCase();
                        const a = (e.getAttribute('aria-label') || '').trim().toLowerCase();
                        return (
                          t === 'show more' ||
                          a === 'show more' ||
                          t.includes('show more') ||
                          a.includes('show more') ||
                          t.includes('แสดงเพิ่มเติม') ||
                          a.includes('แสดงเพิ่มเติม')
                        );
                      });
                      if (!btn) return false;
                      btn.click();
                      return true;
                    })()""",
                    "returnByValue": True,
                },
            )
            return bool(res.get("result", {}).get("result", {}).get("value", False))

        async def click_second_top_right_icon_once() -> bool:
            # User workflow: activate Gemini by clicking the 2nd icon from top-right toolbar.
            res = await send(
                "Runtime.evaluate",
                {
                    "expression": """(() => {
                      const buttons = [...document.querySelectorAll('button,[role="button"],div[role="button"]')];
                      const candidates = buttons.filter((el) => {
                        const rect = el.getBoundingClientRect();
                        if (!rect || rect.width <= 0 || rect.height <= 0) return false;
                        const topBand = rect.top >= 0 && rect.top <= 160;
                        const rightBand = rect.left >= (window.innerWidth - 260);
                        return topBand && rightBand;
                      }).sort((a, b) => b.getBoundingClientRect().left - a.getBoundingClientRect().left);
                      if (candidates.length >= 2) {
                        candidates[1].click();
                        return true;
                      }
                      return false;
                    })()""",
                    "returnByValue": True,
                },
            )
            return bool(res.get("result", {}).get("result", {}).get("value", False))

        async def click_ask_gemini_button_once() -> bool:
            res = await send(
                "Runtime.evaluate",
                {
                    "expression": """(() => {
                      const all = [...document.querySelectorAll('button,[role="button"],div[role="button"],span')];
                      const askBtn = all.find((e) => {
                        const t = (e.innerText || '').trim().toLowerCase();
                        const a = (e.getAttribute && e.getAttribute('aria-label') || '').trim().toLowerCase();
                        return t.includes('ask gemini') || a.includes('ask gemini');
                      });
                      if (!askBtn) return false;
                      askBtn.click();
                      return true;
                    })()""",
                    "returnByValue": True,
                },
            )
            return bool(res.get("result", {}).get("result", {}).get("value", False))

        async def is_gemini_panel_visible() -> bool:
            res = await send(
                "Runtime.evaluate",
                {
                    "expression": """(() => {
                      const editors = [...document.querySelectorAll('textarea,[role="textbox"],div[contenteditable="true"]')];
                      // Treat Gemini as visible only when an actual right-side composer is visible.
                      return editors.some((e) => {
                        const style = window.getComputedStyle(e);
                        if (!style || style.display === 'none' || style.visibility === 'hidden') return false;
                        const r = e.getBoundingClientRect();
                        if (!r || r.width < 40 || r.height < 20) return false;
                        return r.left >= (window.innerWidth * 0.5);
                      });
                    })()""",
                    "returnByValue": True,
                },
            )
            return bool(res.get("result", {}).get("result", {}).get("value", False))

        async def ensure_gemini_panel_visible() -> bool:
            if await is_gemini_panel_visible():
                return True
            clicked = await click_second_top_right_icon_once()
            if clicked:
                await asyncio.sleep(0.8)
                if await is_gemini_panel_visible():
                    return True
            clicked2 = await click_ask_gemini_button_once()
            if clicked2:
                await asyncio.sleep(0.8)
            return await is_gemini_panel_visible()

        async def ensure_gemini_composer_ready() -> bool:
            # Open chat composer explicitly if panel is visible but input is not ready.
            res = await send(
                "Runtime.evaluate",
                {
                    "expression": """(() => {
                      const editors = [...document.querySelectorAll('textarea,[role="textbox"],div[contenteditable="true"]')];
                      const ready = editors.some((e) => {
                        const style = window.getComputedStyle(e);
                        if (!style || style.display === 'none' || style.visibility === 'hidden') return false;
                        const r = e.getBoundingClientRect();
                        return r && r.width > 40 && r.height > 20 && r.left >= (window.innerWidth * 0.5);
                      });
                      if (ready) return true;

                      const all = [...document.querySelectorAll('button,[role="button"],div[role="button"],span')];
                      const askQ = all.find((e) => {
                        const t = (e.innerText || '').trim().toLowerCase();
                        return t.includes('ask a question about this file') || t.includes('ask a question');
                      });
                      if (!askQ) return false;
                      askQ.click();
                      return true;
                    })()""",
                    "returnByValue": True,
                },
            )
            ok = bool(res.get("result", {}).get("result", {}).get("value", False))
            if ok:
                await asyncio.sleep(0.8)
            return ok

        async def _find_submit_button_center() -> tuple[int, int] | None:
            res = await send(
                "Runtime.evaluate",
                {
                    "expression": """(() => {
                      const isVisible = (el) => {
                        if (!el) return false;
                        const style = window.getComputedStyle(el);
                        if (!style || style.display === 'none' || style.visibility === 'hidden') return false;
                        const r = el.getBoundingClientRect();
                        return !!r && r.width > 8 && r.height > 8;
                      };
                      const score = (el) => {
                        const r = el.getBoundingClientRect();
                        let s = 0;
                        if (r.left >= window.innerWidth * 0.5) s += 3;
                        if (r.top >= 0 && r.top <= window.innerHeight) s += 1;
                        const t = (el.innerText || '').trim().toLowerCase();
                        const a = (el.getAttribute('aria-label') || '').trim().toLowerCase();
                        if (t === 'submit' || a === 'submit') s += 4;
                        if (t.includes('submit') || a.includes('submit')) s += 3;
                        if (t === 'send' || a === 'send') s += 3;
                        if (t.includes('send') || a.includes('send')) s += 2;
                        return s;
                      };
                      const candidates = [...document.querySelectorAll('button,[role="button"],div[role="button"],span')]
                        .filter(isVisible)
                        .filter((el) => {
                          const ariaDisabled = (el.getAttribute && el.getAttribute('aria-disabled') || '').toLowerCase();
                          const disabled = Boolean(el.disabled) || ariaDisabled === 'true';
                          return !disabled;
                        })
                        .filter((el) => {
                          const t = (el.innerText || '').trim().toLowerCase();
                          const a = (el.getAttribute('aria-label') || '').trim().toLowerCase();
                          return (
                            t.includes('submit') || a.includes('submit') ||
                            t.includes('send') || a.includes('send')
                          );
                        })
                        .sort((a, b) => score(b) - score(a));

                      const toClickable = (el) => {
                        let cur = el;
                        for (let i = 0; i < 6 && cur; i += 1) {
                          const tag = (cur.tagName || '').toLowerCase();
                          const role = (cur.getAttribute && cur.getAttribute('role') || '').toLowerCase();
                          if (tag === 'button' || role === 'button' || typeof cur.onclick === 'function') return cur;
                          cur = cur.parentElement;
                        }
                        return el;
                      };
                      const center = (el) => {
                        const r = el.getBoundingClientRect();
                        const x = Math.max(1, Math.floor(r.left + r.width / 2));
                        const y = Math.max(1, Math.floor(r.top + r.height / 2));
                        return {x, y};
                      };

                      let target = candidates.length ? toClickable(candidates[0]) : null;
                      if (!target) {
                        // Fallback: locate visible "Submit" text and click nearest clickable ancestor.
                        const all = [...document.querySelectorAll('span,div,button')].filter(isVisible);
                        const sub = all.find((el) => (el.innerText || '').trim().toLowerCase() === 'submit');
                        if (sub) target = toClickable(sub);
                      }
                      if (!target || !isVisible(target)) return null;
                      return center(target);
                    })()""",
                    "returnByValue": True,
                },
            )
            v = res.get("result", {}).get("result", {}).get("value", None)
            if isinstance(v, dict):
                try:
                    x = int(v.get("x"))
                    y = int(v.get("y"))
                    return (x, y)
                except Exception:
                    return None
            return None

        async def click_submit_in_right_panel_once() -> bool:
            pt = await _find_submit_button_center()
            if pt is None:
                return False
            x, y = pt
            # Real mouse events via CDP; more reliable than synthetic DOM click.
            await send(
                "Input.dispatchMouseEvent",
                {"type": "mouseMoved", "x": x, "y": y, "button": "none"},
            )
            await send(
                "Input.dispatchMouseEvent",
                {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1},
            )
            await send(
                "Input.dispatchMouseEvent",
                {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1},
            )
            return True

        async def wait_submit_enabled(timeout_seconds: float = 6.0) -> bool:
            deadline = time.time() + max(0.5, timeout_seconds)
            while time.time() < deadline:
                if await _find_submit_button_center() is not None:
                    return True
                await asyncio.sleep(0.25)
            return False

        async def dispatch_enter_key() -> None:
            # Send Enter at CDP level (works better than synthetic DOM events on some editors).
            for evt in ("keyDown", "char", "keyUp"):
                await send(
                    "Input.dispatchKeyEvent",
                    {
                        "type": evt,
                        "key": "Enter",
                        "code": "Enter",
                        "windowsVirtualKeyCode": 13,
                        "nativeVirtualKeyCode": 13,
                    },
                )

        def _response_looks_complete(text: str) -> bool:
            t = (text or "").lower()
            if not t:
                return False
            if "generating your content" in t:
                return False
            done_markers = [
                "sources (",
                "export to docs",
                "retry",
                "good response",
                "bad response",
            ]
            return any(m in t for m in done_markers)

        async def ask_gemini_main_points_once() -> bool:
            res = await send(
                "Runtime.evaluate",
                {
                    "expression": """(() => {
                      const all = [...document.querySelectorAll('button,[role="button"],div[role="button"],span')];
                      const askBtn = all.find((e) => {
                        const t = (e.innerText || '').trim().toLowerCase();
                        const a = (e.getAttribute && e.getAttribute('aria-label') || '').trim().toLowerCase();
                        return t.includes('ask gemini') || a.includes('ask gemini');
                      });
                      if (askBtn) askBtn.click();

                      const clickTarget = all.find((e) => {
                        const t = (e.innerText || '').trim().toLowerCase();
                        return (
                          t.includes('list the main points for this file') ||
                          t.includes('main points for this file')
                        );
                      });
                      if (clickTarget) {
                        clickTarget.click();
                        return true;
                      }
                      return false;
                    })()""",
                    "returnByValue": True,
                },
            )
            return bool(res.get("result", {}).get("result", {}).get("value", False))

        async def ask_gemini_custom_prompt_once(prompt: str) -> bool:
            p = (prompt or "").strip()
            if not p:
                return False
            p_json = json.dumps(p, ensure_ascii=False)
            res = await send(
                "Runtime.evaluate",
                {
                    "expression": f"""(() => {{
                      const editors = [...document.querySelectorAll('textarea,[role="textbox"],div[contenteditable=\"true\"]')];
                      const visibleEditors = editors.filter((e) => {{
                        const style = window.getComputedStyle(e);
                        if (!style || style.display === 'none' || style.visibility === 'hidden') return false;
                        const r = e.getBoundingClientRect();
                        if (!r || r.width < 40 || r.height < 20) return false;
                        if (e.disabled || e.readOnly) return false;
                        return true;
                      }});
                      // Prefer Gemini side-panel composer (usually on right side and has Ask-a-question label).
                      const box = visibleEditors.find((e) => {{
                        const r = e.getBoundingClientRect();
                        const ph = ((e.getAttribute('placeholder') || '') + ' ' + (e.getAttribute('aria-label') || '')).toLowerCase();
                        return (
                          r.left >= (window.innerWidth * 0.5) &&
                          (ph.includes('ask a question') || ph.includes('ask gemini') || ph.includes('question about this file'))
                        );
                      }}) || visibleEditors.find((e) => e.getBoundingClientRect().left >= (window.innerWidth * 0.5))
                        || visibleEditors[visibleEditors.length - 1];
                      if (!box) return false;

                      const prompt = {p_json};
                      box.focus();
                      if ('value' in box) {{
                        box.value = prompt;
                      }} else {{
                        box.textContent = prompt;
                      }}
                      box.dispatchEvent(new Event('input', {{ bubbles: true }}));
                      box.dispatchEvent(new Event('change', {{ bubbles: true }}));

                      // Message typed successfully; sending is handled separately.
                      return true;
                    }})()""",
                    "returnByValue": True,
                },
            )
            return bool(res.get("result", {}).get("result", {}).get("value", False))

        async def close_question_overlay_once() -> bool:
            # Some Drive/Gemini layouts keep a question thread overlay open;
            # close it before typing a new prompt to avoid hidden composer state.
            res = await send(
                "Runtime.evaluate",
                {
                    "expression": """(() => {
                      const all = [...document.querySelectorAll('button,[role="button"],div[role="button"],span')];
                      const vis = (e) => {
                        const s = window.getComputedStyle(e);
                        if (!s || s.display === 'none' || s.visibility === 'hidden') return false;
                        const r = e.getBoundingClientRect();
                        return r && r.width > 8 && r.height > 8;
                      };
                      const cands = all.filter(vis).filter((e) => {
                        const t = (e.innerText || '').trim().toLowerCase();
                        const a = (e.getAttribute && e.getAttribute('aria-label') || '').trim().toLowerCase();
                        return t === 'close' || a === 'close' || t.includes('close');
                      });
                      if (!cands.length) return false;
                      cands[0].click();
                      return true;
                    })()""",
                    "returnByValue": True,
                },
            )
            return bool(res.get("result", {}).get("result", {}).get("value", False))

        # Custom prompt mode: ask Gemini first, then capture answer.
        if gemini_prompt:
            if pre_ask_delay_seconds > 0:
                await asyncio.sleep(float(pre_ask_delay_seconds))
            await ensure_gemini_panel_visible()
            # When summary cards are shown, explicitly click "Ask Gemini"
            # so the chat composer is activated before we type.
            _ = await click_ask_gemini_button_once()
            await asyncio.sleep(0.35)
            await close_question_overlay_once()
            await asyncio.sleep(0.2)
            await ensure_gemini_composer_ready()
            best = ""
            baseline_text = ""
            baseline_panel = ""
            baseline_res = await send(
                "Runtime.evaluate",
                {"expression": f"document.body ? document.body.innerText.slice(0, {max_chars}) : ''", "returnByValue": True},
            )
            baseline_text = str(baseline_res.get("result", {}).get("result", {}).get("value", "") or "")
            baseline_panel = _extract_panel_answer_block(baseline_text)
            asked = await ask_gemini_custom_prompt_once(gemini_prompt)
            if asked:
                await wait_submit_enabled(6.0)
                clicked = await click_submit_in_right_panel_once()
                await asyncio.sleep(0.6)
                if not clicked:
                    await dispatch_enter_key()
                    await asyncio.sleep(0.6)
            if asked:
                await asyncio.sleep(2.5)
            sent_prompt_snippet = re.sub(r"\s+", " ", gemini_prompt.strip().lower())[:60]
            json_nudge_count = 0
            deadline = time.time() + max(4, wait_seconds)
            tick = 0
            while time.time() < deadline:
                tick += 1
                res = await send(
                    "Runtime.evaluate",
                    {"expression": f"document.body ? document.body.innerText.slice(0, {max_chars}) : ''", "returnByValue": True},
                )
                text = str(res.get("result", {}).get("result", {}).get("value", "") or "")
                if text:
                    best = text
                # If prompt still appears with no answer yet, press Submit again.
                if tick % 3 == 0:
                    if (gemini_prompt in text) and ("submit" in text.lower()):
                        await click_submit_in_right_panel_once()
                        await asyncio.sleep(0.6)
                # If prompt text is not detected at all, retry type+submit.
                if tick % 4 == 0:
                    text_norm = re.sub(r"\s+", " ", text.lower())
                    if sent_prompt_snippet and sent_prompt_snippet not in text_norm:
                        await click_ask_gemini_button_once()
                        await asyncio.sleep(0.2)
                        await ensure_gemini_composer_ready()
                        retyped = await ask_gemini_custom_prompt_once(gemini_prompt)
                        if retyped:
                            await wait_submit_enabled(3.0)
                            await click_submit_in_right_panel_once()
                            await asyncio.sleep(0.5)
                expanded = await click_show_more_once()
                if expanded:
                    await asyncio.sleep(0.5)
                if _response_looks_complete(text):
                    panel = _extract_panel_answer_block(text)
                    if panel and not _looks_like_viewer_only_text(panel):
                        return text
                ans = _extract_panel_answer_block(text)
                if ans and ("{" in ans and "}" in ans) and not _looks_like_viewer_only_text(ans):
                    return text
                # If assistant responds with prose (no JSON), nudge once/twice to reformat.
                if ans and ("{" not in ans or "}" not in ans):
                    if json_nudge_count < 2 and tick % 4 == 0:
                        nudge = (
                            "Return the same answer again as STRICT JSON only. "
                            "No prose, no markdown, start with '{' and end with '}'."
                        )
                        retyped = await ask_gemini_custom_prompt_once(nudge)
                        if retyped:
                            await wait_submit_enabled(3.0)
                            await click_submit_in_right_panel_once()
                            await asyncio.sleep(0.6)
                            json_nudge_count += 1
                if ans and not _looks_like_viewer_only_text(ans):
                    if ans != baseline_panel or len(ans) > (len(baseline_panel) + 30):
                        return text
                if "```json" in text.lower():
                    return text
                await asyncio.sleep(1.0)
            return best

        deadline = time.time() + max(2, wait_seconds)
        best = ""
        while time.time() < deadline:
            res = await send(
                "Runtime.evaluate",
                {"expression": f"document.body ? document.body.innerText.slice(0, {max_chars}) : ''", "returnByValue": True},
            )
            text = str(res.get("result", {}).get("result", {}).get("value", "") or "")
            if text:
                best = text
            if "Summary" in text:
                expanded = await click_show_more_once()
                if expanded:
                    await asyncio.sleep(0.8)
                    res2 = await send(
                        "Runtime.evaluate",
                        {"expression": f"document.body ? document.body.innerText.slice(0, {max_chars}) : ''", "returnByValue": True},
                    )
                    text2 = str(res2.get("result", {}).get("result", {}).get("value", "") or "")
                    if text2:
                        best = text2
                return best or text
            await asyncio.sleep(1.0)

        # Fallback: trigger Gemini prompt and capture response text.
        asked = await ask_gemini_main_points_once()
        if asked:
            await asyncio.sleep(2.5)
            detail_deadline = time.time() + max(4, wait_seconds)
            while time.time() < detail_deadline:
                res = await send(
                    "Runtime.evaluate",
                    {"expression": f"document.body ? document.body.innerText.slice(0, {max_chars}) : ''", "returnByValue": True},
                )
                text = str(res.get("result", {}).get("result", {}).get("value", "") or "")
                if text:
                    best = text
                expanded = await click_show_more_once()
                if expanded:
                    await asyncio.sleep(0.5)
                if gemini_prompt:
                    if _extract_panel_answer_block(text):
                        return text
                elif _extract_summary_block(text):
                    return text
                await asyncio.sleep(1.0)
        return best


def _scrape_one(
    devtools_url: str,
    row: dict[str, Any],
    wait_seconds: int,
    retries: int = 3,
    retry_wait_increment: int = 5,
    gemini_prompt: str = "",
    pre_ask_delay_seconds: int = 0,
    open_interval_seconds: float = 0.0,
    require_json_response: bool = False,
) -> dict[str, Any]:
    drive_id = str(row.get("drive_id", "")).strip()
    drive_url = str(row.get("drive_url", "")).strip()
    name = str(row.get("name", "")).strip()
    folder_path = row.get("folder_path", [])
    province = str(row.get("province", "")).strip()
    constituency_number = int(row.get("constituency_number", 0) or 0)
    if not drive_id or not drive_url:
        return {"ok": False, "reason": "missing_id_or_url", "drive_id": drive_id}

    max_attempts = max(1, retries)
    last_reason = "no_summary"
    last_text = ""
    for attempt in range(1, max_attempts + 1):
        tab = _open_url_in_new_tab(
            devtools_url,
            drive_url,
            min_interval_seconds=open_interval_seconds,
        )
        if not tab:
            last_reason = "open_failed"
            continue
        tid = str(tab.get("id", ""))
        ws = str(tab.get("webSocketDebuggerUrl", ""))
        if not tid or not ws:
            if tid:
                _close_target(devtools_url, tid)
            last_reason = "missing_ws"
            continue
        try:
            wait_this_try = wait_seconds + ((attempt - 1) * max(0, retry_wait_increment))
            try:
                text = asyncio.run(
                    _read_page_text(
                        ws,
                        wait_seconds=wait_this_try,
                        gemini_prompt=gemini_prompt,
                        pre_ask_delay_seconds=pre_ask_delay_seconds,
                    )
                )
            except Exception:
                last_reason = "read_error"
                continue
            last_text = text
            summary = _extract_panel_answer_block(text) if gemini_prompt else _extract_summary_block(text)
            if gemini_prompt and not summary:
                summary = _extract_answer_after_prompt(text, gemini_prompt)
            # Fallback: in some Drive/Gemini layouts the JSON answer appears
            # in page text but not in the detected panel block.
            if gemini_prompt and not summary:
                summary = _extract_json_object_text(text)
            if gemini_prompt and summary and _looks_like_viewer_only_text(summary):
                summary = ""
            if gemini_prompt and require_json_response:
                # Keep only JSON payload text when strict JSON mode is enabled.
                j = _extract_json_object_text(summary or "")
                if not j:
                    j = _extract_json_object_text(text or "")
                summary = j or ""
            if summary:
                hints = _extract_location_hints(
                    summary_text=summary,
                    name=name,
                    folder_path=folder_path if isinstance(folder_path, list) else [],
                    province_fallback=province,
                    district_fallback=constituency_number,
                )
                return {
                    "ok": True,
                    "drive_id": drive_id,
                    "drive_url": drive_url,
                    "name": name,
                    "summary": summary,
                    "raw_text": text,
                    "gemini_prompt_used": bool(gemini_prompt),
                    "folder_path": folder_path if isinstance(folder_path, list) else [],
                    **hints,
                }
            last_reason = "no_summary"
        finally:
            _close_target(devtools_url, tid)

    hints = _extract_location_hints(
        summary_text=last_text,
        name=name,
        folder_path=folder_path if isinstance(folder_path, list) else [],
        province_fallback=province,
        district_fallback=constituency_number,
    )
    return {
        "ok": False,
        "reason": f"{last_reason}_after_{max_attempts}_tries",
        "drive_id": drive_id,
        "name": name,
        "raw_text": last_text,
        **hints,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Scrape only files with visible Drive PDF Summary")
    parser.add_argument("--mapping-file", default=DEFAULT_MAPPING)
    parser.add_argument("--devtools-url", default="http://127.0.0.1:9222/json")
    parser.add_argument("--out-file", default=DEFAULT_OUT)
    parser.add_argument("--state-file", default=DEFAULT_STATE)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--wait-seconds", type=int, default=10)
    parser.add_argument("--retries", type=int, default=3, help="Retries per file before marking as skipped")
    parser.add_argument("--retry-wait-increment", type=int, default=5, help="Extra wait seconds added on each retry")
    parser.add_argument("--pdf-only", dest="pdf_only", action="store_true", help="Process only .pdf file names (default)")
    parser.add_argument("--include-non-pdf", dest="pdf_only", action="store_false", help="Include non-PDF files")
    parser.set_defaults(pdf_only=True)
    parser.add_argument(
        "--mark-skipped-done",
        action="store_true",
        default=False,
        help="Add skipped files to state done_ids (default: keep them retryable)",
    )
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--gemini-prompt",
        default="",
        help="Optional custom Gemini prompt to ask in panel (if empty, uses summary/main-points flow).",
    )
    parser.add_argument(
        "--pre-ask-delay-seconds",
        type=int,
        default=0,
        help="Optional delay after opening each file tab before asking Gemini (stabilize tab load).",
    )
    parser.add_argument(
        "--open-interval-seconds",
        type=float,
        default=0.0,
        help="Rate limit opening new tabs per browser endpoint (e.g. 1.0 = one tab/sec).",
    )
    parser.add_argument(
        "--require-json-response",
        action="store_true",
        default=False,
        help="When using --gemini-prompt, save only valid JSON object responses.",
    )
    parser.add_argument("--resume", action="store_true", default=True)
    parser.add_argument("--no-resume", dest="resume", action="store_false")
    args = parser.parse_args()

    mapping = _load_json(args.mapping_file, {"files": {}})
    files_map = mapping.get("files", {}) if isinstance(mapping, dict) else {}
    if not isinstance(files_map, dict):
        print("ERROR: invalid mapping file")
        return 1
    rows: list[dict[str, Any]] = []
    for did, entry in files_map.items():
        if not isinstance(entry, dict):
            continue
        drive_id = str(entry.get("drive_id") or did).strip()
        if not drive_id:
            continue
        drive_url = str(entry.get("drive_url", "")).strip()
        if not drive_url:
            drive_url = f"https://drive.google.com/file/d/{drive_id}/view"
        rows.append(
            {
                "drive_id": drive_id,
                "drive_url": drive_url,
                "name": str(entry.get("name", "")).strip(),
                "folder_path": entry.get("folder_path", []),
                "province": str(entry.get("province", "")).strip(),
                "constituency_number": int(entry.get("constituency_number", 0) or 0),
                "gemini_prompt": str(entry.get("gemini_prompt", "")).strip(),
            }
        )
    if args.pdf_only:
        rows = [r for r in rows if str(r.get("name", "")).lower().endswith(".pdf")]
    rows = sorted(rows, key=lambda x: x["drive_id"])
    if args.limit and args.limit > 0:
        rows = rows[: args.limit]

    done_ids: set[str] = set()
    if args.resume:
        st = _load_json(args.state_file, {"done_ids": []})
        if isinstance(st, dict) and isinstance(st.get("done_ids"), list):
            done_ids = set(str(x) for x in st["done_ids"])
        # Also infer from output file
        out_p = Path(args.out_file)
        if out_p.exists():
            try:
                for line in out_p.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    obj = json.loads(line)
                    did = str(obj.get("drive_id", "")).strip()
                    if did:
                        done_ids.add(did)
            except Exception:
                pass

    queue = [r for r in rows if r["drive_id"] not in done_ids]
    if not queue:
        print("Nothing to do (all files already visited).")
        return 0

    lock = threading.Lock()
    scanned = 0
    saved = 0
    skipped = 0

    out_path = Path(args.out_file)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("a", encoding="utf-8") as out:
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
            futures = [
                ex.submit(
                    _scrape_one,
                    args.devtools_url,
                    row,
                    args.wait_seconds,
                    args.retries,
                    args.retry_wait_increment,
                    row.get("gemini_prompt") or args.gemini_prompt,
                    args.pre_ask_delay_seconds,
                    args.open_interval_seconds,
                    args.require_json_response,
                )
                for row in queue
            ]
            for fut in concurrent.futures.as_completed(futures):
                result = fut.result()
                did = str(result.get("drive_id", "")).strip()
                with lock:
                    scanned += 1
                    if result.get("ok"):
                        if did:
                            done_ids.add(did)
                        payload = {
                            "drive_id": result["drive_id"],
                            "drive_url": result["drive_url"],
                            "name": result.get("name", ""),
                            "summary": result.get("summary", ""),
                            "raw_text": result.get("raw_text", ""),
                            "folder_path": result.get("folder_path", []),
                            "province_hint": result.get("province_hint"),
                            "district_number_hint": result.get("district_number_hint"),
                            "unit_number_hint": result.get("unit_number_hint"),
                            "committee_number_hint": result.get("committee_number_hint"),
                            "form_type_hint": result.get("form_type_hint"),
                            "location_number_hint": result.get("location_number_hint"),
                            "location_kind_hint": result.get("location_kind_hint"),
                        }
                        out.write(json.dumps(payload, ensure_ascii=False) + "\n")
                        saved += 1
                        print(f"[{scanned}/{len(queue)}] saved summary: {payload['drive_id']} {payload['name']}")
                    else:
                        if did and args.mark_skipped_done:
                            done_ids.add(did)
                        skipped += 1
                        print(f"[{scanned}/{len(queue)}] skip({result.get('reason')}): {did} {result.get('name','')}")
                    _save_json(args.state_file, {"done_ids": sorted(done_ids), "updated_at_epoch": int(time.time())})

    print(f"Done. scanned={scanned} saved={saved} skipped={skipped}")
    print(f"Output: {args.out_file}")
    print(f"State: {args.state_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
