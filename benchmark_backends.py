#!/usr/bin/env python3
"""
Per-backend accuracy benchmark.

Ground truth is manually verified against official ECT results.
Each backend runs individually (not ensembled) so we can compare them.

Usage:
    python benchmark_backends.py
    EXTRACTION_BACKENDS=nim python benchmark_backends.py
"""

import json
import os
import time
from dataclasses import dataclass, field
from typing import Optional

from ballot_types import FormType

# ---------------------------------------------------------------------------
# Ground truth  (manually verified against official ECT data)
# ---------------------------------------------------------------------------

GROUND_TRUTH = [
    {
        "image": "test_images/high_res_page-1.png",
        "form_type": FormType.S5_16,
        "description": "high-res constituency (Phrae 1, unit 2)",
        "vote_counts": {1: 614, 2: 4, 3: 24},
        "valid_votes": 642,
    },
    {
        "image": "test_images/page-1.png",
        "form_type": FormType.S5_17,
        "description": "standard constituency",
        "vote_counts": {1: 82, 2: 6, 3: 25, 4: 11, 5: 12, 6: 10},
        "valid_votes": 155,  # approximate (no total in source)
    },
]

# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

@dataclass
class BackendResult:
    backend_name: str
    image: str
    success: bool
    elapsed: float
    vote_counts: dict = field(default_factory=dict)
    confidence: float = 0.0
    error: str = ""


def score(result: BackendResult, truth: dict) -> dict:
    """Return accuracy metrics comparing result to ground truth."""
    gt = truth["vote_counts"]
    pred = {int(k): v for k, v in result.vote_counts.items()}

    positions = sorted(gt.keys())
    exact_matches = sum(1 for p in positions if pred.get(p) == gt[p])
    mae_values = [abs(pred.get(p, 0) - gt[p]) for p in positions]
    mae = sum(mae_values) / len(mae_values) if mae_values else 0.0
    full_match = exact_matches == len(positions)

    pred_total = sum(pred.get(p, 0) for p in positions)
    gt_total = truth["valid_votes"]
    total_err = abs(pred_total - gt_total)

    return {
        "exact_positions": exact_matches,
        "total_positions": len(positions),
        "exact_pct": 100 * exact_matches / len(positions) if positions else 0,
        "full_ballot_match": full_match,
        "mae": mae,
        "total_votes_error": total_err,
        "per_position": {p: {"gt": gt[p], "pred": pred.get(p, "?"), "ok": pred.get(p) == gt[p]} for p in positions},
    }


# ---------------------------------------------------------------------------
# Run one backend against one image
# ---------------------------------------------------------------------------

def run_backend(backend, image_path: str, form_type: Optional[FormType]) -> BackendResult:
    start = time.time()
    try:
        result = backend.extract(image_path, form_type)
        elapsed = time.time() - start
        if result is None:
            return BackendResult(backend.name, image_path, False, elapsed, error="returned None")
        return BackendResult(
            backend_name=backend.name,
            image=image_path,
            success=True,
            elapsed=elapsed,
            vote_counts=result.vote_counts,
            confidence=result.confidence_score,
        )
    except Exception as e:
        return BackendResult(backend.name, image_path, False, time.time() - start, error=str(e))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    from model_backends import (
        OpenRouterBackend, AnthropicBackend, TesseractBackend, TrOCRBackend,
        build_backends_from_env,
    )

    # Build individual backends for isolated comparison
    # (bypass EnsembleExtractor so each runs alone)
    all_backends = [
        OpenRouterBackend(),                               # default Gemma 12B
        OpenRouterBackend("google/gemma-3-27b-it:free"),   # bigger Gemma
        AnthropicBackend(),                                # Claude Sonnet
        OpenRouterBackend(                                 # NIM Kimi K2.5
            model_id="moonshotai/kimi-k2.5",
            base_url="https://integrate.api.nvidia.com/v1",
            api_key_env="NVIDIA_API_KEY",
            crop_timeout=90,   # slow cold-start
            full_timeout=180,
        ),
        TesseractBackend(),
    ]

    available = [b for b in all_backends if b.is_available]
    skipped   = [b for b in all_backends if not b.is_available]

    print("=" * 70)
    print("BACKEND ACCURACY BENCHMARK")
    print("=" * 70)
    print(f"Available : {[b.name for b in available]}")
    print(f"Skipped   : {[b.name for b in skipped]} (no API key / binary)")
    print(f"Images    : {len(GROUND_TRUTH)}")
    print()

    all_scores: dict[str, list] = {b.name: [] for b in available}

    for truth in GROUND_TRUTH:
        image = truth["image"]
        form_type = truth["form_type"]
        print(f"── {truth['description']}  ({image})")
        print(f"   Ground truth: {truth['vote_counts']}  total={truth['valid_votes']}")
        print()

        for backend in available:
            print(f"   Running {backend.name}...", flush=True)
            r = run_backend(backend, image, form_type)

            if not r.success:
                print(f"   FAILED: {r.error}  ({r.elapsed:.1f}s)\n")
                all_scores[backend.name].append(None)
                continue

            m = score(r, truth)
            m["elapsed"] = r.elapsed
            all_scores[backend.name].append(m)

            def _pos(p, info):
                return f"#{p}:OK" if info["ok"] else f"#{p}:{info['pred']}!={info['gt']}"
            pos_str = "  ".join(_pos(p, info) for p, info in m["per_position"].items())
            print(f"   {r.elapsed:5.1f}s  conf={r.confidence:.2f}  "
                  f"exact={m['exact_positions']}/{m['total_positions']} ({m['exact_pct']:.0f}%)  "
                  f"MAE={m['mae']:.1f}  totalΔ={m['total_votes_error']}")
            print(f"          {pos_str}")
            print()

        print()

    # Summary table
    print("=" * 70)
    print(f"{'Backend':<38} {'ExactPos%':>9} {'FullMatch':>9} {'MAE':>6} {'TotalΔ':>7} {'AvgTime':>8}")
    print("-" * 70)

    for backend in available:
        scores = [s for s in all_scores[backend.name] if s is not None]
        if not scores:
            print(f"{backend.name:<38} {'no data':>9}")
            continue

        avg_exact = sum(s["exact_pct"]     for s in scores) / len(scores)
        full_rate = sum(s["full_ballot_match"] for s in scores) / len(scores) * 100
        avg_mae   = sum(s["mae"]            for s in scores) / len(scores)
        avg_terr  = sum(s["total_votes_error"] for s in scores) / len(scores)
        avg_time  = sum(s["elapsed"]        for s in scores) / len(scores)

        print(f"{backend.name:<38} {avg_exact:>8.0f}%  {full_rate:>7.0f}%  {avg_mae:>6.1f}  {avg_terr:>7.1f}  {avg_time:>6.1f}s")

    print()


if __name__ == "__main__":
    main()
