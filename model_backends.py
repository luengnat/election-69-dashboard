#!/usr/bin/env python3
"""
Pluggable multi-model ensemble OCR backend registry.

Each backend implements the ModelBackend protocol. EnsembleExtractor runs all
available backends in parallel and votes on per-position consensus.

Configure via EXTRACTION_BACKENDS env var:

    # Default (each skipped if key/binary missing):
    EXTRACTION_BACKENDS=openrouter,anthropic,tesseract,trocr

    # Custom models:
    EXTRACTION_BACKENDS=openrouter:google/gemma-3-27b-it:free,anthropic:claude-haiku-4-20250514

    # Single backend:
    EXTRACTION_BACKENDS=anthropic
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


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class ModelBackend(Protocol):
    """Protocol for ballot OCR extraction backends."""

    @property
    def name(self) -> str: ...

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


class AnthropicBackend:
    """Wraps Claude Vision extraction."""

    DEFAULT_MODEL = "claude-sonnet-4-20250514"

    def __init__(self, model_id: str = DEFAULT_MODEL):
        self._model_id = model_id

    @property
    def name(self) -> str:
        return f"anthropic:{self._model_id}"

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
    """

    @property
    def name(self) -> str:
        return "tesseract"

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

            vote_counts = ocr.extract_vote_counts(image_path)
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
    """

    # Default to the better model; can override via env var
    MODEL_ID = os.environ.get("TROCR_MODEL", "kkatiz/thai-trocr-thaigov-v2")
    _processor = None
    _model = None

    @property
    def name(self) -> str:
        return "trocr"

    @property
    def is_available(self) -> bool:
        try:
            import transformers  # noqa: F401
            return True
        except ImportError:
            return False

    @classmethod
    def _load_model(cls) -> bool:
        if cls._processor is not None:
            return True
        try:
            from transformers import TrOCRProcessor, VisionEncoderDecoderModel
            print(f"  Loading TrOCR model {cls.MODEL_ID} (first use, may be slow)...")
            cls._processor = TrOCRProcessor.from_pretrained(cls.MODEL_ID)
            cls._model = VisionEncoderDecoderModel.from_pretrained(cls.MODEL_ID)
            print("  TrOCR model loaded.")
            return True
        except Exception as e:
            print(f"  TrOCR model load failed: {e}")
            return False

    def extract(self, image_path: str, form_type: Optional[FormType]) -> Optional[BallotData]:
        if not self._load_model():
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
            from crop_utils import crop_page_image, FORM_TEMPLATES, _DEFAULT_TEMPLATE
        except ImportError:
            print("  TrOCR: crop_utils not available")
            return None

        # Select template based on form type
        template = FORM_TEMPLATES.get(form_type, _DEFAULT_TEMPLATE)

        # Determine if this is page 1 or a continuation page
        is_page_1 = True
        filename = os.path.basename(image_path).lower()
        if "page-" in filename and "page-1" not in filename and "page-01" not in filename:
            import re
            match = re.search(r'page-(\d+)', filename)
            if match and int(match.group(1)) > 1:
                is_page_1 = False
        
        # Select appropriate region from template
        crop_region = template.vote_numbers_p1 if is_page_1 else template.vote_numbers_cont

        vote_crop_path = None
        try:
            vote_crop_path = crop_page_image(image_path, crop_region)
            img = Image.open(vote_crop_path).convert("RGB")
            strips = self._split_into_row_strips(img)
            if not strips:
                return None

            vote_counts: dict[int, int] = {}
            vote_details = {}

            for position, strip in enumerate(strips, start=1):
                pixel_values = self.__class__._processor(strip, return_tensors="pt").pixel_values
                generated_ids = self.__class__._model.generate(pixel_values)
                text = self.__class__._processor.batch_decode(
                    generated_ids, skip_special_tokens=True
                )[0].strip()

                number = thai_text_to_number(text)
                if number is None:
                    import re
                    digits = re.findall(r'\d+', text)
                    number = int(digits[0]) if digits else 0

                vote_counts[position] = number
                vote_details[position] = validate_vote_entry(number, text)

            if not vote_counts:
                return None

            total = sum(vote_counts.values())
            station_id = f"trocr-{form_type.value if form_type else 'unknown'}"

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
                confidence_score=0.65,
                confidence_details={"level": "MEDIUM", "trocr_based": True},
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

def _mode_with_fallback(values: list, fallback):
    """Return (winner, agreement_rate). On a tie, prefer fallback."""
    counts = Counter(values)
    max_count = max(counts.values())
    winners = [v for v, c in counts.items() if c == max_count]
    agreement = max_count / len(values)

    if len(winners) == 1:
        return winners[0], agreement

    # Tie — prefer fallback if it's among the winners
    if fallback in winners:
        return fallback, agreement
    return winners[0], agreement  # arbitrary tiebreak


def _vote(results: list[tuple[str, BallotData]]) -> BallotData:
    """Compute per-position consensus across multiple BallotData results.

    For each vote position, takes the mode across all models. On a tie, falls
    back to the highest-confidence backend's value.

    Ensemble confidence = best_confidence * 0.6 + avg_vote_agreement * 0.4
    """
    if len(results) == 1:
        return results[0][1]

    # Sort by confidence descending so index 0 is the best
    ranked = sorted(results, key=lambda t: t[1].confidence_score, reverse=True)
    best_name, best_data = ranked[0]

    is_party_list = best_data.form_category == "party_list"
    agreement_rates: dict = {}

    if is_party_list:
        all_keys = set()
        for _, bd in results:
            all_keys.update(bd.party_votes.keys())

        consensus_party: dict[str, int] = {}
        for key in all_keys:
            values = [bd.party_votes[key] for _, bd in results if key in bd.party_votes]
            if not values:
                continue
            winner, agreement = _mode_with_fallback(values, best_data.party_votes.get(key))
            consensus_party[key] = winner
            agreement_rates[key] = agreement

        new_total = sum(consensus_party.values()) if consensus_party else best_data.total_votes
        consensus_data = dataclass_replace(
            best_data,
            party_votes=consensus_party,
            total_votes=new_total,
            valid_votes=new_total,
        )

    else:
        all_keys = set()
        for _, bd in results:
            all_keys.update(bd.vote_counts.keys())

        consensus_counts: dict[int, int] = {}
        for key in all_keys:
            values = [bd.vote_counts[key] for _, bd in results if key in bd.vote_counts]
            if not values:
                continue
            winner, agreement = _mode_with_fallback(values, best_data.vote_counts.get(key))
            consensus_counts[key] = winner
            agreement_rates[key] = agreement

        new_total = sum(consensus_counts.values()) if consensus_counts else best_data.total_votes
        consensus_data = dataclass_replace(
            best_data,
            vote_counts=consensus_counts,
            total_votes=new_total,
            valid_votes=new_total,
        )

    avg_agreement = sum(agreement_rates.values()) / len(agreement_rates) if agreement_rates else 0.0
    ensemble_confidence = best_data.confidence_score * 0.6 + avg_agreement * 0.4

    ensemble_details = dict(best_data.confidence_details)
    ensemble_details["ensemble"] = {
        "backends": [name for name, _ in results],
        "per_position_agreement": {str(k): v for k, v in agreement_rates.items()},
        "avg_agreement": avg_agreement,
        "best_backend": best_name,
    }

    return dataclass_replace(
        consensus_data,
        confidence_score=ensemble_confidence,
        confidence_details=ensemble_details,
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

        # Single-backend fast path (no voting overhead)
        if len(available) == 1:
            print(f"  Extracting with {available[0].name}...")
            return available[0].extract(image_path, form_type)

        # Parallel extraction across all backends
        names = [b.name for b in available]
        print(f"  Running {len(available)} backends in parallel: {names}")
        results: list[tuple[str, BallotData]] = []

        with ThreadPoolExecutor(max_workers=len(available)) as executor:
            future_to_name = {
                executor.submit(backend.extract, image_path, form_type): backend.name
                for backend in available
            }
            for future in as_completed(future_to_name):
                name = future_to_name[future]
                try:
                    result = future.result()
                    if result is not None:
                        results.append((name, result))
                        print(f"  {name}: succeeded (confidence={result.confidence_score:.2f})")
                    else:
                        print(f"  {name}: returned None")
                except Exception as e:
                    print(f"  {name}: raised {e}")

        if not results:
            return None
        if len(results) == 1:
            return results[0][1]

        print(f"  Voting across {len(results)} results...")
        return _vote(results)


# ---------------------------------------------------------------------------
# Backend factory
# ---------------------------------------------------------------------------

def build_backends_from_env() -> list:
    """Parse EXTRACTION_BACKENDS env var and return backend instances.

    Format:
        EXTRACTION_BACKENDS=openrouter,anthropic,tesseract,trocr   (default)
        EXTRACTION_BACKENDS=openrouter:google/gemma-3-27b-it:free,anthropic:claude-haiku-4-20250514
        EXTRACTION_BACKENDS=anthropic
    """
    spec = os.environ.get(
        "EXTRACTION_BACKENDS",
        "openrouter,anthropic,tesseract,trocr",
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
        else:
            print(f"  WARNING: Unknown backend type '{kind}', skipping.")

    return backends
