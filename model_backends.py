#!/usr/bin/env python3
"""
Pluggable multi-model ensemble OCR backend registry.

Each backend implements the ModelBackend protocol. EnsembleExtractor runs all
available backends in parallel and votes on per-position consensus.

Configure via EXTRACTION_BACKENDS env var:

    # Default (each skipped if key/binary missing):
    EXTRACTION_BACKENDS=llamacpp,openrouter,anthropic,tesseract,trocr

    # Custom models:
    EXTRACTION_BACKENDS=openrouter:google/gemma-3-27b-it:free,anthropic:claude-haiku-4-20250514
    EXTRACTION_BACKENDS=ollama:llama3.2-vision

    # Ollama shorthand for glm-ocr:
    EXTRACTION_BACKENDS=glm-ocr,tesseract

    # LM Studio (defaults to port 1234):
    EXTRACTION_BACKENDS=lmstudio,tesseract

    # Single backend:
    EXTRACTION_BACKENDS=llamacpp

llama.cpp server setup:
    # Start with a vision-capable GGUF model
    llama-server -m model.gguf --port 8080 --ctx-size 4096

    # Or use LLAMACPP_BASE_URL to point to a different host/port
    LLAMACPP_BASE_URL=http://192.168.1.100:8080

LM Studio setup:
    # In LM Studio, go to Local Server tab and start server on port 1234
    # Override with LMSTUDIO_BASE_URL if needed
    LMSTUDIO_BASE_URL=http://127.0.0.1:1234
"""

import base64
import json
import os
import shutil
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace as dataclass_replace
from typing import Optional, Protocol, runtime_checkable

from ballot_types import FormType, BallotData


def _is_continuation_filename(image_path: str) -> bool:
    """Infer page 2+ from filename variants like page-2/page_2/page 2."""
    import re
    filename = os.path.basename(image_path).lower()
    match = re.search(r"page[\s_-]*0*(\d+)", filename, flags=re.IGNORECASE)
    return bool(match and int(match.group(1)) > 1)


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class ModelBackend(Protocol):
    """Protocol for ballot OCR extraction backends."""

    @property
    def name(self) -> str: ...

    @property
    def weight(self) -> float: ...

    @property
    def is_available(self) -> bool: ...

    def extract(self, image_path: str, form_type: Optional[FormType]) -> Optional[BallotData]: ...


# ---------------------------------------------------------------------------
# Concrete backends
# ---------------------------------------------------------------------------

class OpenRouterBackend:
    """OpenAI-compatible vision backend (OpenRouter, NVIDIA NIM, or any OAI endpoint).

    Examples:
        OpenRouterBackend()                                    # default OpenRouter
        OpenRouterBackend("moonshotai/kimi-k2.5",
                          base_url="https://integrate.api.nvidia.com/v1",
                          api_key_env="NVIDIA_API_KEY")        # NVIDIA NIM
    """

    DEFAULT_MODEL = "google/gemma-3-12b-it:free"
    DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
    DEFAULT_API_KEY_ENV = "OPENROUTER_API_KEY"

    def __init__(
        self,
        model_id: str = DEFAULT_MODEL,
        base_url: str = DEFAULT_BASE_URL,
        api_key_env: str = DEFAULT_API_KEY_ENV,
        crop_timeout: int = 30,
        full_timeout: int = 60,
    ):
        self._model_id = model_id
        self._base_url = base_url.rstrip("/")
        self._api_key_env = api_key_env
        self._crop_timeout = crop_timeout
        self._full_timeout = full_timeout

    @property
    def name(self) -> str:
        if self._base_url == self.DEFAULT_BASE_URL:
            return f"openrouter:{self._model_id}"
        # Derive a short label from the host, e.g. "integrate.api.nvidia.com" → "nim"
        from urllib.parse import urlparse
        host = urlparse(self._base_url).hostname or self._base_url
        label = "nim" if "nvidia" in host else host.split(".")[0]
        return f"{label}:{self._model_id}"

    @property
    def weight(self) -> float:
        return 1.0

    @property
    def is_available(self) -> bool:
        return bool(os.environ.get(self._api_key_env, "").strip())

    def extract(self, image_path: str, form_type: Optional[FormType]) -> Optional[BallotData]:
        import requests
        import ballot_extraction as be

        api_key = os.environ.get(self._api_key_env, "").strip()
        if not api_key:
            return None

        # Try crop-aware extraction first (cheaper — ~70% token reduction)
        if form_type is not None and be.CROP_UTILS_AVAILABLE:
            result = be._extract_with_crops(
                image_path, form_type, api_key,
                model_id=self._model_id,
                base_url=self._base_url,
                timeout=self._crop_timeout,
            )
            if result is not None:
                return result
            print(f"  {self.name}: crop extraction failed, trying full image...")

        # Full-image fallback
        image_data = base64.b64encode(be._preprocess_image(image_path)).decode("utf-8")

        if form_type is not None:
            if form_type.is_party_list:
                prompt = be.get_party_list_prompt()
            else:
                prompt = be.get_constituency_prompt()
        else:
            prompt = be.get_combined_prompt()

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        # OpenRouter-specific routing headers
        if self._base_url == self.DEFAULT_BASE_URL:
            headers["HTTP-Referer"] = "https://github.com/election-verification"
            headers["X-Title"] = "Thai Election Ballot OCR"

        try:
            response = requests.post(
                url=f"{self._base_url}/chat/completions",
                headers=headers,
                json={
                    "model": self._model_id,
                    "messages": [{
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_data}"}},
                            {"type": "text", "text": prompt},
                        ],
                    }],
                    "max_tokens": 2048,
                },
                timeout=self._full_timeout,
            )

            if response.status_code == 200:
                result = response.json()
                response_text = result["choices"][0]["message"]["content"]
                print(f"  {self.name}: response received ({len(response_text)} chars)")
                data = json.loads(be._strip_json_fences(response_text))
                return be.process_extracted_data(data, image_path, form_type)
            else:
                print(f"  {self.name}: API error {response.status_code} - {response.text}")
                return None

        except Exception as e:
            print(f"  {self.name}: failed: {e}")
            return None


class OllamaBackend:
    """Local Ollama vision backend.

    Uses Ollama `/api/generate` with `images` + prompt and expects JSON output.
    Best used with vision-capable models (e.g. `llama3.2-vision`).
    """

    DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "minicpm-v:latest")
    DEFAULT_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    DEFAULT_TIMEOUT = int(os.environ.get("OLLAMA_TIMEOUT", "120"))
    DEFAULT_DEBUG = os.environ.get("OLLAMA_DEBUG_RETRY", "").strip().lower() in {"1", "true", "yes", "on"}
    DEFAULT_DISABLE_FALLBACK = os.environ.get("OLLAMA_DISABLE_MODEL_FALLBACK", "").strip().lower() in {"1", "true", "yes", "on"}

    def __init__(
        self,
        model_id: str = DEFAULT_MODEL,
        base_url: str = DEFAULT_BASE_URL,
        timeout: int = DEFAULT_TIMEOUT,
        debug_retry: bool = DEFAULT_DEBUG,
        disable_model_fallback: bool = DEFAULT_DISABLE_FALLBACK,
    ):
        self._model_id = model_id
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._debug_retry = debug_retry
        self._disable_model_fallback = disable_model_fallback
        self._resolved_model_id: Optional[str] = None

    @property
    def name(self) -> str:
        return f"ollama:{self._model_id}"

    @property
    def weight(self) -> float:
        return 1.1

    @property
    def is_available(self) -> bool:
        try:
            import requests

            resp = requests.get(f"{self._base_url}/api/tags", timeout=2)
            return resp.status_code == 200
        except Exception:
            return False

    def _resolve_model(self) -> str:
        """Pick a usable local model, preferring configured id."""
        if self._resolved_model_id:
            return self._resolved_model_id
        for cand in self._candidate_models():
            self._resolved_model_id = cand
            return cand
        self._resolved_model_id = self._model_id
        return self._resolved_model_id

    def _candidate_models(self) -> list[str]:
        """Return ordered installed candidate models for fallback attempts."""
        if self._disable_model_fallback:
            return [self._model_id]

        models: list[str] = []
        try:
            import requests
            resp = requests.get(f"{self._base_url}/api/tags", timeout=3)
            if resp.status_code == 200:
                models = [m.get("name", "") for m in resp.json().get("models", []) if isinstance(m, dict)]
        except Exception:
            models = []

        # Prefer explicit model first, then known vision/OCR-capable fallbacks.
        preferred = [
            self._model_id,
            os.environ.get("OLLAMA_MODEL", "").strip(),
            "llava:latest",
            "glm-ocr:latest",
            "minicpm-v:latest",
        ]
        preferred = [m for m in preferred if m]
        ordered: list[str] = []
        for cand in preferred:
            if cand in models:
                ordered.append(cand)
        # If tag listing unavailable, still try configured model.
        if not ordered:
            ordered.append(self._model_id)
        # Deduplicate while preserving order.
        return list(dict.fromkeys(ordered))

    def _build_options(self) -> dict:
        options = {"temperature": 0}
        num_gpu_raw = os.environ.get("OLLAMA_NUM_GPU", "").strip()
        num_gpu = int(num_gpu_raw) if num_gpu_raw.lstrip("-").isdigit() else None
        num_thread_raw = os.environ.get("OLLAMA_NUM_THREAD", "").strip()
        num_thread = int(num_thread_raw) if num_thread_raw.isdigit() else None
        if num_gpu is not None:
            options["num_gpu"] = num_gpu
        if num_thread is not None:
            options["num_thread"] = num_thread
        return options

    def _debug(self, msg: str) -> None:
        if self._debug_retry:
            print(f"  {self.name}: {msg}")

    def _parse_ollama_json_payload(self, obj: dict) -> tuple[str, bool]:
        response_text = str(obj.get("response", "")).strip()
        done = bool(obj.get("done", False))
        return response_text, done

    def _generate_once(
        self,
        model: str,
        prompt: str,
        image_data: str,
        *,
        stream: bool,
        use_json_format: bool,
    ) -> tuple[Optional[str], Optional[bool], Optional[str]]:
        import requests

        payload = {
            "model": model,
            "prompt": prompt,
            "images": [image_data],
            "stream": stream,
            "options": self._build_options(),
        }
        if use_json_format:
            payload["format"] = "json"

        try:
            response = requests.post(
                f"{self._base_url}/api/generate",
                json=payload,
                timeout=self._timeout,
                stream=stream,
            )
        except Exception as e:
            return None, None, str(e)

        if response.status_code != 200:
            return None, None, f"{response.status_code} {response.text[:220]}"

        if not stream:
            obj = response.json()
            txt, done = self._parse_ollama_json_payload(obj)
            return txt, done, None

        # Streaming path: concatenate chunk responses until final `done=true`.
        chunks: list[str] = []
        saw_done_true = False
        for line in response.iter_lines(decode_unicode=True):
            if not line:
                continue
            try:
                chunk_obj = json.loads(line)
            except Exception:
                continue
            chunk_txt, done = self._parse_ollama_json_payload(chunk_obj)
            if chunk_txt:
                chunks.append(chunk_txt)
            if done:
                saw_done_true = True
                break
        return "".join(chunks).strip(), saw_done_true, None

    def _extract_json_candidate(self, raw_text: str) -> Optional[dict]:
        import ballot_extraction as be

        text = be._strip_json_fences(raw_text).strip()
        if not text:
            return None
        try:
            return json.loads(text)
        except Exception:
            # Fallback: parse the largest {...} region if model added prose.
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end > start:
                try:
                    return json.loads(text[start : end + 1])
                except Exception:
                    return None
            return None

    def extract(self, image_path: str, form_type: Optional[FormType]) -> Optional[BallotData]:
        import ballot_extraction as be

        try:
            image_data = base64.b64encode(be._preprocess_image(image_path)).decode("utf-8")

            if form_type is not None:
                if form_type.is_party_list:
                    prompt = be.get_party_list_prompt()
                else:
                    prompt = be.get_constituency_prompt()
            else:
                prompt = be.get_combined_prompt()

            last_err = ""
            for model in self._candidate_models():
                # Attempt sequence:
                # 1) one-shot JSON mode (fast)
                # 2) streamed JSON mode (handles partial chunk responses)
                # 3) plain mode with stricter prompt fallback
                attempts = [
                    ("json-once", prompt, False, True),
                    ("json-stream", prompt, True, True),
                    (
                        "plain-fallback",
                        prompt
                        + "\n\nReturn ONLY one valid JSON object with no extra text.",
                        False,
                        False,
                    ),
                    (
                        "plain-stream",
                        prompt
                        + "\n\nReturn ONLY one valid JSON object with no extra text.",
                        True,
                        False,
                    )
                ]
                for attempt_name, attempt_prompt, stream, use_json_format in attempts:
                    self._debug(
                        f"trying model={model} attempt={attempt_name} stream={stream} json_format={use_json_format}"
                    )
                    response_text, done, err = self._generate_once(
                        model,
                        attempt_prompt,
                        image_data,
                        stream=stream,
                        use_json_format=use_json_format,
                    )
                    if err:
                        last_err = err
                        self._debug(f"attempt={attempt_name} model={model} failed: {err}")
                        continue
                    if not response_text:
                        last_err = "empty response"
                        self._debug(f"attempt={attempt_name} model={model} failed: empty response")
                        continue
                    if done is False:
                        last_err = "incomplete response (done=false)"
                        self._debug(f"attempt={attempt_name} model={model} failed: {last_err}")
                        continue

                    data = self._extract_json_candidate(response_text)
                    if data is None:
                        last_err = "json parse failed"
                        snippet = response_text[:160].replace("\n", " ")
                        self._debug(f"attempt={attempt_name} model={model} failed: {last_err}; snippet={snippet!r}")
                        continue

                    processed = be.process_extracted_data(data, image_path, form_type)
                    if processed is not None:
                        self._resolved_model_id = model
                        self._debug(f"success model={model} attempt={attempt_name}")
                        return processed
                    self._debug(f"attempt={attempt_name} model={model} parsed but post-processing returned None")
            if last_err:
                print(f"  {self.name}: all candidate models failed; last_error={last_err}")
            return None
        except Exception as e:
            print(f"  {self.name}: failed: {e}")
            return None


class LlamaCppBackend:
    """Local llama.cpp server backend.

    Uses llama.cpp's OpenAI-compatible HTTP server (/v1/chat/completions).
    Start the server with: llama-server -m model.gguf --port 8080
    """

    DEFAULT_BASE_URL = os.environ.get("LLAMACPP_BASE_URL", "http://127.0.0.1:8080")
    DEFAULT_TIMEOUT = int(os.environ.get("LLAMACPP_TIMEOUT", "120"))

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        timeout: int = DEFAULT_TIMEOUT,
    ):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    @property
    def name(self) -> str:
        return "llamacpp"

    @property
    def weight(self) -> float:
        return 1.1

    @property
    def is_available(self) -> bool:
        try:
            import requests
            resp = requests.get(f"{self._base_url}/health", timeout=2)
            return resp.status_code == 200
        except Exception:
            return False

    def extract(self, image_path: str, form_type: Optional[FormType]) -> Optional[BallotData]:
        import requests
        import ballot_extraction as be

        try:
            image_data = base64.b64encode(be._preprocess_image(image_path)).decode("utf-8")

            if form_type is not None:
                if form_type.is_party_list:
                    prompt = be.get_party_list_prompt()
                else:
                    prompt = be.get_constituency_prompt()
            else:
                prompt = be.get_combined_prompt()

            # llama.cpp server uses OpenAI-compatible chat completions API
            response = requests.post(
                f"{self._base_url}/v1/chat/completions",
                headers={"Content-Type": "application/json"},
                json={
                    "messages": [{
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_data}"}},
                            {"type": "text", "text": prompt},
                        ],
                    }],
                    "max_tokens": 2048,
                    "temperature": 0,
                },
                timeout=self._timeout,
            )

            if response.status_code == 200:
                result = response.json()
                response_text = result["choices"][0]["message"]["content"]
                print(f"  {self.name}: response received ({len(response_text)} chars)")
                data = json.loads(be._strip_json_fences(response_text))
                return be.process_extracted_data(data, image_path, form_type)
            else:
                print(f"  {self.name}: API error {response.status_code} - {response.text[:200]}")
                return None

        except Exception as e:
            print(f"  {self.name}: failed: {e}")
            return None


class LMStudioBackend(LlamaCppBackend):
    """LM Studio local server backend.

    LM Studio provides an OpenAI-compatible API on port 1234 by default.
    Start the server in LM Studio: Local Server tab → Start Server.

    Environment overrides:
        LMSTUDIO_BASE_URL - Change the base URL (default: http://127.0.0.1:1234)
        LMSTUDIO_TIMEOUT   - Request timeout in seconds (default: 120)
        LMSTUDIO_MODEL     - Model ID to use (default: auto-detect vision model)
    """

    DEFAULT_BASE_URL = os.environ.get("LMSTUDIO_BASE_URL", "http://127.0.0.1:1234")
    DEFAULT_TIMEOUT = int(os.environ.get("LMSTUDIO_TIMEOUT", "120"))
    DEFAULT_MODEL = os.environ.get("LMSTUDIO_MODEL", "")  # Empty = auto-detect

    # Known vision-capable model patterns (prefer glm-ocr for structured output)
    VISION_MODEL_PATTERNS = ["glm-ocr", "llava", "qwen2-vl", "qwen-vl", "minicpm-v", "bakllava", "moondream"]

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        timeout: int = DEFAULT_TIMEOUT,
        model_id: str = DEFAULT_MODEL,
    ):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._model_id = model_id
        self._resolved_model: Optional[str] = None

    @property
    def name(self) -> str:
        model = self._resolved_model or self._model_id or "auto"
        return f"lmstudio:{model}" if model else "lmstudio"

    @property
    def is_available(self) -> bool:
        """Check if LM Studio server is running (uses /v1/models endpoint)."""
        try:
            import requests
            resp = requests.get(f"{self._base_url}/v1/models", timeout=2)
            return resp.status_code == 200
        except Exception:
            return False

    def _get_vision_model(self) -> Optional[str]:
        """Find the best available vision model."""
        if self._resolved_model:
            return self._resolved_model

        if self._model_id:
            self._resolved_model = self._model_id
            return self._model_id

        try:
            import requests
            resp = requests.get(f"{self._base_url}/v1/models", timeout=3)
            if resp.status_code != 200:
                return None

            models = [m.get("id", "") for m in resp.json().get("data", []) if isinstance(m, dict)]

            # Find first matching vision model pattern
            for pattern in self.VISION_MODEL_PATTERNS:
                for model_id in models:
                    if pattern.lower() in model_id.lower():
                        self._resolved_model = model_id
                        return model_id
        except Exception:
            pass

        return None

    def extract(self, image_path: str, form_type: Optional[FormType]) -> Optional[BallotData]:
        import requests
        import ballot_extraction as be

        model = self._get_vision_model()
        if not model:
            print(f"  {self.name}: no vision model found")
            return None

        try:
            image_data = base64.b64encode(be._preprocess_image(image_path)).decode("utf-8")

            # Use minimal prompt for LM Studio models (they work better with shorter prompts)
            prompt = be.get_minimal_prompt()

            response = requests.post(
                f"{self._base_url}/v1/chat/completions",
                headers={"Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": [{
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_data}"}},
                            {"type": "text", "text": prompt},
                        ],
                    }],
                    "max_tokens": 2048,
                    "temperature": 0,
                },
                timeout=self._timeout,
            )

            if response.status_code == 200:
                result = response.json()
                response_text = result["choices"][0]["message"]["content"]
                print(f"  {self.name}: response received ({len(response_text)} chars)")
                stripped = be._strip_json_fences(response_text)
                # Use lenient parser for models that may produce slightly malformed JSON
                data = be._try_parse_lenient_json(stripped)
                if data is None:
                    print(f"  {self.name}: failed to parse JSON")
                    return None
                return be.process_extracted_data(data, image_path, form_type)
            else:
                print(f"  {self.name}: API error {response.status_code} - {response.text[:200]}")
                return None

        except Exception as e:
            print(f"  {self.name}: failed: {e}")
            return None


class AnthropicBackend:
    """Wraps Claude Vision extraction."""

    DEFAULT_MODEL = "claude-sonnet-4-20250514"

    def __init__(self, model_id: str = DEFAULT_MODEL):
        self._model_id = model_id

    @property
    def name(self) -> str:
        return f"anthropic:{self._model_id}"

    @property
    def weight(self) -> float:
        return 1.2

    @property
    def is_available(self) -> bool:
        return bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())

    def extract(self, image_path: str, form_type: Optional[FormType]) -> Optional[BallotData]:
        import ballot_extraction as be
        return be.extract_with_claude_vision(image_path, form_type, model_id=self._model_id)


class TesseractBackend:
    """Wraps local Tesseract OCR.

    Uses TesseractOCR.extract_vote_counts() directly (heuristic regex) to
    avoid the Anthropic API dependency in extract_with_tesseract().

    Tesseract tends to be more reliable for handwritten digits than
    TrOCR's strip fallback, so it gets a higher weight.
    """

    @property
    def name(self) -> str:
        return "tesseract"

    @property
    def weight(self) -> float:
        # Higher weight - Tesseract is reliable for digit extraction
        return 1.3

    @property
    def is_available(self) -> bool:
        return shutil.which("tesseract") is not None

    def extract(self, image_path: str, form_type: Optional[FormType]) -> Optional[BallotData]:
        try:
            from tesseract_ocr import TesseractOCR, is_available
            if not is_available():
                return None

            ocr = TesseractOCR()
            result = ocr.process_ballot(image_path)
            if not result:
                return None

            vote_counts = ocr.extract_vote_counts(image_path, form_type=form_type)
            if not vote_counts:
                print("  tesseract: no vote counts extracted")
                return None

            total = sum(vote_counts.values())
            return BallotData(
                form_type=form_type.value if form_type else "",
                form_category="party_list" if (form_type and form_type.is_party_list) else "constituency",
                province="",
                polling_station_id="",
                vote_counts=vote_counts,
                vote_details={},
                party_votes={},
                party_details={},
                total_votes=total,
                valid_votes=total,
                invalid_votes=0,
                blank_votes=0,
                source_file=image_path,
                confidence_score=result.confidence / 100.0,
                confidence_details={"level": "LOW", "tesseract_confidence": result.confidence},
            )
        except Exception as e:
            print(f"  tesseract: error: {e}")
            return None


class TrOCRBackend:
    """Local HuggingFace TrOCR backend for Thai text recognition.

    Supports multiple Thai TrOCR models:
    - kkatiz/thai-trocr-thaigov-v2 (recommended, 10-20% better accuracy)
    - openthaigpt/thai-trocr (original)
    - sthaps/DeepSeek-ocr-Thai (for handwritten numbers)

    Model is loaded lazily and cached as class variables to avoid reloading
    per image. Set TROCR_MODEL env var to override default.

    NOTE: This backend uses a strip fallback when cell extraction fails,
    which can produce inaccurate results. Weight is lowered to reflect this.
    """

    # Default to the better model; can override via env var
    MODEL_ID = os.environ.get("TROCR_MODEL", "kkatiz/thai-trocr-thaigov-v2")
    _processor = None
    _model = None
    _active_model_id = None
    _load_failed = False
    _load_error = ""
    _disabled_notice_printed = False

    @property
    def name(self) -> str:
        return "trocr"

    @property
    def weight(self) -> float:
        # Lower weight because strip fallback is unreliable for vote extraction
        return 0.7

    @property
    def is_available(self) -> bool:
        if self.__class__._load_failed:
            return False
        try:
            import transformers  # noqa: F401
            return True
        except ImportError:
            return False

    @classmethod
    def _get_model_candidates(cls) -> list[str]:
        """
        Return TrOCR model candidates in order.

        Supports optional env override:
            TROCR_MODEL_CANDIDATES="model-a,model-b,model-c"
        """
        env_candidates = os.environ.get("TROCR_MODEL_CANDIDATES", "").strip()
        if env_candidates:
            candidates = [m.strip() for m in env_candidates.split(",") if m.strip()]
        else:
            candidates = [
                cls.MODEL_ID,
                "openthaigpt/thai-trocr",
            ]
        # Deduplicate while preserving order.
        return list(dict.fromkeys(candidates))

    @classmethod
    def _load_model(cls) -> bool:
        # Already loaded and ready
        if cls._processor is not None and cls._model is not None:
            return True
        # Previous load attempt failed; avoid repeated noisy retries.
        if cls._load_failed:
            return False
        from transformers import TrOCRProcessor, VisionEncoderDecoderModel

        errors = []
        for model_id in cls._get_model_candidates():
            try:
                print(f"  Loading TrOCR model {model_id} (first use, may be slow)...")
                # Keep HF behavior stable across versions; avoid implicit fast processor switch.
                cls._processor = TrOCRProcessor.from_pretrained(model_id, use_fast=False)
                cls._model = VisionEncoderDecoderModel.from_pretrained(model_id)
                cls._active_model_id = model_id
                print(f"  TrOCR model loaded: {model_id}")
                return True
            except Exception as e:
                errors.append(f"{model_id}: {e}")
                cls._processor = None
                cls._model = None

        cls._load_failed = True
        cls._disabled_notice_printed = False
        cls._load_error = " | ".join(errors)
        print(f"  TrOCR model load failed: {cls._load_error}")
        return False

    def extract(self, image_path: str, form_type: Optional[FormType]) -> Optional[BallotData]:
        if not self._load_model():
            if self.__class__._load_error and not self.__class__._disabled_notice_printed:
                print(f"  TrOCR disabled for this run: {self.__class__._load_error}")
                self.__class__._disabled_notice_printed = True
            return None

        try:
            from PIL import Image
        except ImportError:
            print("  TrOCR: Pillow not available")
            return None

        try:
            from ballot_types import validate_vote_entry, thai_text_to_number
        except ImportError as e:
            print(f"  TrOCR missing dependency: {e}")
            return None

        try:
            from crop_utils import crop_page_image, deskew_image, extract_vote_cells, FORM_TEMPLATES, _DEFAULT_TEMPLATE, save_crop_persistently
        except ImportError:
            print("  TrOCR: crop_utils not available")
            return None

        # Select template based on form type
        template = FORM_TEMPLATES.get(form_type, _DEFAULT_TEMPLATE)

        # Determine if this is page 1 or a continuation page.
        is_page_1 = not _is_continuation_filename(image_path)
        
        # Select appropriate region from template
        crop_region = template.vote_numbers_p1 if is_page_1 else template.vote_numbers_cont

        vote_crop_path = None
        deskewed_path = None
        cell_paths = []
        try:
            vote_crop_path = crop_page_image(image_path, crop_region)
            deskewed_path = deskew_image(vote_crop_path)
            cell_rows = extract_vote_cells(deskewed_path)

            cell_pairs = []
            if not cell_rows:
                img = Image.open(deskewed_path).convert("RGB")
                for strip in self._split_into_row_strips(img):
                    cell_pairs.append({"thai": strip, "digit": None})
            else:
                for row_paths in cell_rows:
                    cell_paths.extend(row_paths)
                    thai_img = Image.open(row_paths[-1]).convert("RGB")
                    digit_img = Image.open(row_paths[-2]).convert("RGB") if len(row_paths) >= 2 else None
                    cell_pairs.append({"thai": thai_img, "digit": digit_img})

            if not cell_pairs:
                return None

            vote_counts: dict[int, int] = {}
            vote_details = {}

            for position, pair in enumerate(cell_pairs, start=1):
                # 1. Extract Thai text
                pixel_values_thai = self.__class__._processor(pair["thai"], return_tensors="pt").pixel_values
                generated_ids_thai = self.__class__._model.generate(pixel_values_thai)
                thai_text = self.__class__._processor.batch_decode(
                    generated_ids_thai, skip_special_tokens=True
                )[0].strip()

                number_from_thai = thai_text_to_number(thai_text)
                final_number = 0
                cell_confidence = 0.5

                import re

                # 2. Extract digit if available
                number_from_digit = None
                if pair["digit"]:
                    pixel_values_digit = self.__class__._processor(pair["digit"], return_tensors="pt").pixel_values
                    generated_ids_digit = self.__class__._model.generate(pixel_values_digit)
                    digit_text = self.__class__._processor.batch_decode(
                        generated_ids_digit, skip_special_tokens=True
                    )[0].strip()
                    
                    digits = re.findall(r'\d+', digit_text)
                    if digits:
                        number_from_digit = int(digits[0])

                # 3. Consensus Logic
                if number_from_thai is not None and number_from_digit is not None:
                    if number_from_thai == number_from_digit:
                        final_number = number_from_thai
                        cell_confidence = 1.0
                    else:
                        final_number = number_from_thai # Prefer Thai text as source of truth
                        cell_confidence = 0.3
                elif number_from_thai is not None:
                    final_number = number_from_thai
                    cell_confidence = 0.8 # Good thai text, couldn't read digit
                elif number_from_digit is not None:
                    final_number = number_from_digit
                    cell_confidence = 0.8 # Good digit, couldn't parse thai text
                else:
                    # Both failed clean parsing, try to salvage from raw thai text string
                    digits = re.findall(r'\d+', thai_text)
                    if digits:
                        final_number = int(digits[0])
                        cell_confidence = 0.4
                    else:
                        final_number = 0
                        cell_confidence = 0.1

                vote_counts[position] = final_number
                vote_details[position] = validate_vote_entry(final_number, thai_text, confidence=cell_confidence)

            if not vote_counts:
                return None

            total = sum(vote_counts.values())
            station_id = f"trocr-{form_type.value if form_type else 'unknown'}"

            # Calculate overall confidence based on cells
            avg_confidence = sum(v.confidence for v in vote_details.values()) / max(1, len(vote_details))

            return BallotData(
                form_type=form_type.value if form_type else "",
                form_category="party_list" if (form_type and form_type.is_party_list) else "constituency",
                province="",
                polling_station_id=station_id,
                vote_counts=vote_counts,
                vote_details=vote_details,
                party_votes={},
                party_details={},
                total_votes=total,
                valid_votes=total,
                invalid_votes=0,
                blank_votes=0,
                source_file=image_path,
                confidence_score=avg_confidence,
                confidence_details={
                    "level": "HIGH" if avg_confidence > 0.8 else "MEDIUM" if avg_confidence > 0.5 else "LOW",
                    "trocr_based": True,
                    "trocr_model": self.__class__._active_model_id,
                    "cell_confidences": {pos: v.confidence for pos, v in vote_details.items()}
                },
                provenance_images={
                    "vote_column": save_crop_persistently(deskewed_path or vote_crop_path, image_path, "vote_column")
                } if (deskewed_path or vote_crop_path) else {}
            )

        except Exception as e:
            print(f"  TrOCR extraction failed: {e}")
            return None
        finally:
            if vote_crop_path:
                try:
                    os.unlink(vote_crop_path)
                except OSError:
                    pass

    @staticmethod
    def _split_into_row_strips(img):
        """Split image into per-row strips by detecting near-white horizontal bands."""
        try:
            import numpy as np
            arr = np.array(img.convert("L"))
            row_means = arr.mean(axis=1)
            THRESHOLD = 240  # near-white

            strips = []
            in_strip = False
            start = 0
            for y, mean in enumerate(row_means):
                if mean < THRESHOLD and not in_strip:
                    in_strip = True
                    start = y
                elif mean >= THRESHOLD and in_strip:
                    in_strip = False
                    strip = img.crop((0, start, img.width, y))
                    if strip.height > 5:
                        strips.append(strip)

            if in_strip:
                strip = img.crop((0, start, img.width, img.height))
                if strip.height > 5:
                    strips.append(strip)

            return strips

        except ImportError:
            # numpy not available — split into equal chunks
            strips = []
            chunk_h = max(1, img.height // 20)
            for y in range(0, img.height, chunk_h):
                strips.append(img.crop((0, y, img.width, min(y + chunk_h, img.height))))
            return strips


# ---------------------------------------------------------------------------
# Voting
# ---------------------------------------------------------------------------

def _validate_and_clean_result(data: BallotData, max_votes: int = 5000) -> BallotData:
    """
    Validate and clean a single BallotData result.

    - Cap vote counts > max_votes to 0 (likely OCR errors)
    - Recalculate totals after capping

    Note: max_votes=5000 allows for typical Thai polling stations (up to ~3000 voters)
    """
    if not data:
        return data

    # Process constituency votes
    if data.vote_counts:
        cleaned_votes = {}
        for pos, count in data.vote_counts.items():
            if count > max_votes:
                print(f"  Capping outlier: position {pos} value {count} -> 0 (exceeds max {max_votes})")
                cleaned_votes[pos] = 0
            else:
                cleaned_votes[pos] = count
        data = dataclass_replace(data, vote_counts=cleaned_votes)
        # Recalculate total
        new_total = sum(cleaned_votes.values())
        if data.valid_votes != new_total:
            data = dataclass_replace(data, valid_votes=new_total, total_votes=new_total)

    # Process party votes
    if data.party_votes:
        cleaned_party = {}
        for party, count in data.party_votes.items():
            if count > max_votes:
                print(f"  Capping outlier: party {party} value {count} -> 0 (exceeds max {max_votes})")
                cleaned_party[party] = 0
            else:
                cleaned_party[party] = count
        data = dataclass_replace(data, party_votes=cleaned_party)
        # Recalculate total
        new_total = sum(cleaned_party.values())
        if data.valid_votes != new_total:
            data = dataclass_replace(data, valid_votes=new_total, total_votes=new_total)

    return data


def _mode_weighted(values: list, weights: list, outlier_threshold: int = 500):
    """
    Return (winner, confidence_score) using weighted voting.

    Outlier detection: values > outlier_threshold are considered suspicious
    and given reduced weight (likely OCR errors reading "1" as "1000").
    """
    scores = {}
    total_weight = sum(weights)

    for val, weight in zip(values, weights):
        # Penalize suspiciously large values (likely OCR errors)
        if val > outlier_threshold:
            weight *= 0.1  # Reduce weight by 90%
        scores[val] = scores.get(val, 0.0) + weight

    # Find winner
    winner = max(scores, key=scores.get)
    max_score = scores[winner]

    # Calculate confidence: score / total possible weight (if all agreed)
    # Actually, simplistic view: score / total_weight_of_participating_backends
    confidence = max_score / total_weight if total_weight > 0 else 0.0

    return winner, confidence


def _vote(results: list[tuple[str, BallotData, float]]) -> BallotData:
    """
    Compute per-position weighted consensus.

    Args:
        results: list of (backend_name, BallotData, backend_weight)
    """
    if not results:
        return None

    # If only one result, return it
    if len(results) == 1:
        return results[0][1]

    def template_score(item):
        """Score for selecting template - prefer backends with metadata."""
        name, bd, weight = item
        base_score = weight * bd.confidence_score
        # Bonus for metadata
        metadata_bonus = 0
        if bd.province:
            metadata_bonus += 2.0
        if bd.form_type:
            metadata_bonus += 1.0
        if bd.district:
            metadata_bonus += 0.5
        return base_score + metadata_bonus

    # Use the result with the highest score (includes metadata bonus)
    ranked = sorted(results, key=template_score, reverse=True)
    _, best_data, _ = ranked[0]

    # If best_data lacks metadata, try to merge from other backends
    if not best_data.province or not best_data.form_type:
        for _, bd, _ in results:
            if bd.province and not best_data.province:
                best_data = dataclass_replace(best_data, province=bd.province)
            if bd.form_type and not best_data.form_type:
                best_data = dataclass_replace(best_data, form_type=bd.form_type)
            if bd.district and not best_data.district:
                best_data = dataclass_replace(best_data, district=bd.district)
            if bd.form_category and not best_data.form_category:
                best_data = dataclass_replace(best_data, form_category=bd.form_category)

    # Determine form category based on actual data, not just metadata
    # If best_data says party_list but has no party_votes, check other backends
    has_party_votes = any(bd.party_votes for _, bd, _ in results)
    has_vote_counts = any(bd.vote_counts for _, bd, _ in results)

    # Use whichever has actual data
    if best_data.form_category == "party_list" and not best_data.party_votes and has_vote_counts:
        best_data = dataclass_replace(best_data, form_category="constituency")
    elif best_data.form_category == "constituency" and not best_data.vote_counts and has_party_votes:
        best_data = dataclass_replace(best_data, form_category="party_list")

    is_party_list = best_data.form_category == "party_list"

    # Voting structures
    final_vote_counts = {}
    final_party_votes = {}

    # Collect all backends info
    backends = [r[0] for r in results]
    backend_weights = [r[2] for r in results]

    # Thresholds for vote count validation
    # Single backend: values > 200 are suspicious (no corroboration)
    # Absolute max: values > 500 are unreasonable for handwritten ballots
    SINGLE_BACKEND_MAX = 200
    ABSOLUTE_MAX_VOTES = 500

    if is_party_list:
        # Collect all party keys found by any backend
        all_keys = set()
        for _, bd, _ in results:
            all_keys.update(bd.party_votes.keys())

        for key in all_keys:
            # Collect votes for this key from each backend
            votes = []
            weights = []
            backend_count = 0
            for _, bd, w in results:
                if key in bd.party_votes:
                    votes.append(bd.party_votes[key])
                    weights.append(w)
                    backend_count += 1

            if votes:
                winner, _ = _mode_weighted(votes, weights, SINGLE_BACKEND_MAX)
                # Cap unreasonably large values
                if winner > ABSOLUTE_MAX_VOTES:
                    print(f"  Capping outlier: position {key} value {winner} -> 0 (exceeds absolute max {ABSOLUTE_MAX_VOTES})")
                    winner = 0
                elif backend_count == 1 and winner > SINGLE_BACKEND_MAX:
                    print(f"  Capping outlier: position {key} value {winner} -> 0 (single backend, no corroboration)")
                    winner = 0
                final_party_votes[key] = winner

        consensus_data = dataclass_replace(
            best_data,
            party_votes=final_party_votes,
            total_votes=sum(final_party_votes.values()),
            valid_votes=sum(final_party_votes.values()),
        )
    else:
        # Collect all position keys
        all_keys = set()
        for _, bd, _ in results:
            all_keys.update(bd.vote_counts.keys())

        for key in all_keys:
            votes = []
            weights = []
            backend_count = 0
            for _, bd, w in results:
                if key in bd.vote_counts:
                    votes.append(bd.vote_counts[key])
                    weights.append(w)
                    backend_count += 1

            if votes:
                winner, _ = _mode_weighted(votes, weights, SINGLE_BACKEND_MAX)
                # Cap unreasonably large values
                if winner > ABSOLUTE_MAX_VOTES:
                    print(f"  Capping outlier: position {key} value {winner} -> 0 (exceeds absolute max {ABSOLUTE_MAX_VOTES})")
                    winner = 0
                elif backend_count == 1 and winner > SINGLE_BACKEND_MAX:
                    print(f"  Capping outlier: position {key} value {winner} -> 0 (single backend, no corroboration)")
                    winner = 0
                final_vote_counts[key] = winner

        consensus_data = dataclass_replace(
            best_data,
            vote_counts=final_vote_counts,
            total_votes=sum(final_vote_counts.values()),
            valid_votes=sum(final_vote_counts.values()),
        )

    # Update confidence details
    ensemble_details = dict(best_data.confidence_details)
    ensemble_details["ensemble_v2"] = {
        "backends": backends,
        "weights": backend_weights,
        "strategy": "weighted_voting"
    }
    
    return dataclass_replace(
        consensus_data,
        confidence_details=ensemble_details
    )


# ---------------------------------------------------------------------------
# Ensemble extractor
# ---------------------------------------------------------------------------

class EnsembleExtractor:
    """Runs multiple backends in parallel and votes on consensus."""

    def __init__(self, backends: list):
        self._backends = backends

    def extract(self, image_path: str, form_type: Optional[FormType] = None) -> Optional[BallotData]:
        available = [b for b in self._backends if b.is_available]
        if not available:
            print("  No extraction backends available.")
            return None

        # Form type detection runs once before dispatching to all backends
        if form_type is None:
            try:
                import ballot_extraction as be
                if be.CROP_UTILS_AVAILABLE:
                    from crop_utils import detect_form_type_from_path
                    detected = detect_form_type_from_path(image_path)
                    if detected is not None:
                        form_type = detected
                        print(f"  Form type from path: {form_type.value}")
            except Exception:
                pass

        # Single-backend fast path (with validation)
        if len(available) == 1:
            print(f"  Extracting with {available[0].name}...")
            result = available[0].extract(image_path, form_type)
            if result:
                result = _validate_and_clean_result(result)
            return result

        # Parallel extraction across all backends
        names = [b.name for b in available]
        print(f"  Running {len(available)} backends in parallel: {names}")
        
        # Store tuples of (name, BallotData, weight)
        results: list[tuple[str, BallotData, float]] = []

        with ThreadPoolExecutor(max_workers=len(available)) as executor:
            future_to_backend = {
                executor.submit(backend.extract, image_path, form_type): backend
                for backend in available
            }
            for future in as_completed(future_to_backend):
                backend = future_to_backend[future]
                try:
                    result = future.result()
                    if result is not None:
                        results.append((backend.name, result, backend.weight))
                        print(f"  {backend.name}: succeeded (confidence={result.confidence_score:.2f})")
                    else:
                        print(f"  {backend.name}: returned None")
                except Exception as e:
                    print(f"  {backend.name}: raised {e}")

        if not results:
            return None
        if len(results) == 1:
            return results[0][1]

        print(f"  Voting across {len(results)} results (weighted)...")
        return _vote(results)


class PaddleBackend:
    """
    PaddleOCR backend for high-performance local OCR.
    Excellent for tables and digits.
    """
    def __init__(self, lang="en"):
        self.lang = lang
        self._ocr = None

    @property
    def name(self) -> str:
        return "paddle"

    @property
    def weight(self) -> float:
        return 1.5

    @property
    def is_available(self) -> bool:
        try:
            import paddleocr
            return True
        except ImportError:
            return False

    def _load_model(self) -> bool:
        if self._ocr:
            return True
        try:
            from paddleocr import PaddleOCR
            # use_angle_cls=True helps with rotation
            # lang='en' usually sufficient for digits, 'th' for full text
            self._ocr = PaddleOCR(use_angle_cls=True, lang=self.lang, show_log=False)
            print("  PaddleOCR model loaded.")
            return True
        except Exception as e:
            print(f"  PaddleOCR init failed: {e}")
            return False

    @staticmethod
    def _cluster_lines_into_rows(lines: list, y_threshold: int = 15) -> list[list]:
        """
        Group PaddleOCR line detections into rows based on Y-coordinate alignment.
        """
        if not lines:
            return []
            
        # Sort by top Y coordinate
        sorted_lines = sorted(lines, key=lambda x: x[0][0][1])
        
        rows = []
        if not sorted_lines:
            return rows
            
        current_row = [sorted_lines[0]]
        for i in range(1, len(sorted_lines)):
            prev_y = current_row[-1][0][0][1]
            curr_y = sorted_lines[i][0][0][1]
            
            if abs(curr_y - prev_y) < y_threshold:
                current_row.append(sorted_lines[i])
            else:
                rows.append(current_row)
                current_row = [sorted_lines[i]]
        rows.append(current_row)
        return rows

    def extract(self, image_path: str, form_type: Optional[FormType]) -> Optional[BallotData]:
        if not self._load_model():
            return None
            
        try:
            from crop_utils import crop_page_image, FORM_TEMPLATES, _DEFAULT_TEMPLATE, save_crop_persistently
            from ballot_types import validate_vote_entry, thai_text_to_number
            import re
            import os
            
            # Select template based on form type
            template = FORM_TEMPLATES.get(form_type, _DEFAULT_TEMPLATE)

            # Determine if this is page 1 or a continuation page.
            is_page_1 = not _is_continuation_filename(image_path)
            
            # Select appropriate region from template
            crop_region = template.vote_numbers_p1 if is_page_1 else template.vote_numbers_cont

            vote_crop_path = None
            try:
                vote_crop_path = crop_page_image(image_path, crop_region)
                
                # PaddleOCR returns list of lines: [[box, (text, score)], ...]
                result = self._ocr.ocr(vote_crop_path, cls=True)
                
                vote_counts = {}
                
                if result and result[0]:
                    # 1. Group into rows using geometry
                    rows = self._cluster_lines_into_rows(result[0])
                    
                    for row in rows:
                        # 2. In each row, sort elements by X coordinate (left to right)
                        row.sort(key=lambda x: x[0][0][0])
                        
                        # Extract all numbers from all elements in the row
                        row_text = " ".join([item[1][0] for item in row])
                        nums = [int(n) for n in re.findall(r'\d+', row_text)]
                        
                        # Heuristic: 
                        # - If 2+ numbers: first is POS, second is VAL
                        # - If 1 number: it might be VAL if it's large, or POS if it's small
                        if len(nums) >= 2:
                            pos, val = nums[0], nums[1]
                            if 1 <= pos <= 100:
                                vote_counts[pos] = val
                        elif len(nums) == 1:
                            # Heuristic for single number rows
                            val = nums[0]
                            # If it's on the right side of the row, it's likely a vote count
                            # (But we need normalized coordinates to be sure)
                            # For now, skip ambiguous ones to maintain accuracy
                            pass

                if not vote_counts:
                    return None
                    
                total = sum(vote_counts.values())
                station_id = f"paddle-{form_type.value if form_type else 'unknown'}"
                
                return BallotData(
                    form_type=form_type.value if form_type else "",
                    form_category="party_list" if (form_type and form_type.is_party_list) else "constituency",
                    province="",
                    polling_station_id=station_id,
                    vote_counts=vote_counts,
                    vote_details={},
                    party_votes={},
                    party_details={},
                    total_votes=total,
                    valid_votes=total,
                    invalid_votes=0,
                    blank_votes=0,
                    source_file=image_path,
                    confidence_score=0.85, 
                    confidence_details={"level": "HIGH", "paddle_based": True, "geometric_clustering": True},
                    provenance_images={
                        "vote_column": save_crop_persistently(vote_crop_path, image_path, "vote_column")
                    } if vote_crop_path else {}
                )
                
            finally:
                if vote_crop_path:
                    try:
                        os.unlink(vote_crop_path)
                    except OSError:
                        pass
            
        except Exception as e:
            print(f"  Paddle extraction failed: {e}")
            return None


# ---------------------------------------------------------------------------
# Backend factory
# ---------------------------------------------------------------------------

def build_backends_from_env() -> list:
    """Parse EXTRACTION_BACKENDS env var and return backend instances.

    Format:
        EXTRACTION_BACKENDS=llamacpp,openrouter,anthropic,tesseract,trocr,paddle   (default)
        EXTRACTION_BACKENDS=llamacpp,tesseract
        EXTRACTION_BACKENDS=openrouter:google/gemma-3-27b-it:free,anthropic:claude-haiku-4-20250514
        EXTRACTION_BACKENDS=anthropic
    """
    spec = os.environ.get(
        "EXTRACTION_BACKENDS",
        "llamacpp,openrouter,anthropic,tesseract,trocr,paddle",
    ).strip()

    backends = []
    for token in spec.split(","):
        token = token.strip()
        if not token:
            continue

        # Split only on the first colon: "openrouter:model/id:suffix" -> ["openrouter", "model/id:suffix"]
        parts = token.split(":", 1)
        kind = parts[0].lower()
        model_id = parts[1] if len(parts) > 1 else None

        if kind == "openrouter":
            backends.append(OpenRouterBackend(model_id) if model_id else OpenRouterBackend())
        elif kind == "ollama":
            backends.append(OllamaBackend(model_id) if model_id else OllamaBackend())
        elif kind == "llamacpp":
            backends.append(LlamaCppBackend())
        elif kind == "lmstudio":
            backends.append(LMStudioBackend())
        elif kind == "glm-ocr":
            # Shorthand for ollama:glm-ocr
            backends.append(OllamaBackend("glm-ocr:latest"))
        elif kind == "nim":
            # NVIDIA NIM — OpenAI-compatible endpoint, key from NVIDIA_API_KEY
            backends.append(OpenRouterBackend(
                model_id=model_id or "moonshotai/kimi-k2.5",
                base_url="https://integrate.api.nvidia.com/v1",
                api_key_env="NVIDIA_API_KEY",
            ))
        elif kind == "anthropic":
            backends.append(AnthropicBackend(model_id) if model_id else AnthropicBackend())
        elif kind == "tesseract":
            backends.append(TesseractBackend())
        elif kind == "trocr":
            backends.append(TrOCRBackend())
        elif kind == "paddle":
            backends.append(PaddleBackend())
        else:
            print(f"  WARNING: Unknown backend type '{kind}', skipping.")

    return backends
