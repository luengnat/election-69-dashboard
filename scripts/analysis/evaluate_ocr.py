#!/usr/bin/env python3
"""
OCR Method Evaluation Script.

Compares different OCR methods on Thai ballot images:
1. Tesseract OCR (local, free)
2. EasyOCR (local, free, better for handwriting)
3. Cloud AI Vision (OpenRouter/Claude - paid)

Usage:
    python evaluate_ocr.py
"""

import os
import sys
import time
import json
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

# Disable cloud APIs for local-only comparison
os.environ.pop("OPENROUTER_API_KEY", None)


@dataclass
class OCResult:
    """OCR evaluation result."""
    method: str
    image: str
    success: bool
    confidence: float
    time_seconds: float
    text_length: int
    numbers_found: list
    vote_counts: dict
    error: Optional[str] = None


def evaluate_tesseract(image_path: str) -> OCResult:
    """Evaluate Tesseract OCR."""
    start = time.time()
    try:
        from tesseract_ocr import TesseractOCR, is_available

        if not is_available():
            return OCResult(
                method="Tesseract",
                image=image_path,
                success=False,
                confidence=0,
                time_seconds=time.time() - start,
                text_length=0,
                numbers_found=[],
                vote_counts={},
                error="Tesseract not installed"
            )

        ocr = TesseractOCR()
        result = ocr.process_ballot(image_path)
        elapsed = time.time() - start

        if result:
            # Try to extract vote counts from the OCR result
            vote_counts = ocr.extract_vote_counts(image_path)
            return OCResult(
                method="Tesseract",
                image=image_path,
                success=True,
                confidence=result.confidence,
                time_seconds=elapsed,
                text_length=len(result.text),
                numbers_found=result.numbers[:20],
                vote_counts=vote_counts,
            )
        else:
            return OCResult(
                method="Tesseract",
                image=image_path,
                success=False,
                confidence=0,
                time_seconds=elapsed,
                text_length=0,
                numbers_found=[],
                vote_counts={},
                error="OCR returned None"
            )
    except Exception as e:
        return OCResult(
            method="Tesseract",
            image=image_path,
            success=False,
            confidence=0,
            time_seconds=time.time() - start,
            text_length=0,
            numbers_found=[],
            vote_counts={},
            error=str(e)
        )


def evaluate_easyocr(image_path: str) -> OCResult:
    """Evaluate EasyOCR."""
    start = time.time()
    try:
        from easyocr_wrapper import EasyOCRExtractor, is_available

        if not is_available():
            return OCResult(
                method="EasyOCR",
                image=image_path,
                success=False,
                confidence=0,
                time_seconds=time.time() - start,
                text_length=0,
                numbers_found=[],
                vote_counts={},
                error="EasyOCR not installed (pip install easyocr)"
            )

        extractor = EasyOCRExtractor(gpu=False)
        result = extractor.extract(image_path)
        elapsed = time.time() - start

        if result:
            numbers = extractor.extract_numbers(image_path)
            return OCResult(
                method="EasyOCR",
                image=image_path,
                success=True,
                confidence=result.confidence * 100,  # Convert to percentage
                time_seconds=elapsed,
                text_length=len(result.text),
                numbers_found=numbers[:20],
                vote_counts={},  # EasyOCR doesn't have built-in vote extraction
            )
        else:
            return OCResult(
                method="EasyOCR",
                image=image_path,
                success=False,
                confidence=0,
                time_seconds=elapsed,
                text_length=0,
                numbers_found=[],
                vote_counts={},
                error="OCR returned None"
            )
    except ImportError:
        return OCResult(
            method="EasyOCR",
            image=image_path,
            success=False,
            confidence=0,
            time_seconds=time.time() - start,
            text_length=0,
            numbers_found=[],
            vote_counts={},
            error="EasyOCR not installed (pip install easyocr)"
        )
    except Exception as e:
        return OCResult(
            method="EasyOCR",
            image=image_path,
            success=False,
            confidence=0,
            time_seconds=time.time() - start,
            text_length=0,
            numbers_found=[],
            vote_counts={},
            error=str(e)
        )


def evaluate_full_pipeline(image_path: str) -> OCResult:
    """Evaluate full extraction pipeline (AI + Tesseract fallback)."""
    start = time.time()
    try:
        from ballot_extraction import extract_ballot_data_with_ai

        result = extract_ballot_data_with_ai(image_path)
        elapsed = time.time() - start

        if result:
            return OCResult(
                method="Full Pipeline",
                image=image_path,
                success=True,
                confidence=result.confidence_score * 100,
                time_seconds=elapsed,
                text_length=0,  # Full pipeline doesn't return raw text
                numbers_found=list(result.vote_counts.values())[:20],
                vote_counts=result.vote_counts,
            )
        else:
            return OCResult(
                method="Full Pipeline",
                image=image_path,
                success=False,
                confidence=0,
                time_seconds=elapsed,
                text_length=0,
                numbers_found=[],
                vote_counts={},
                error="Pipeline returned None"
            )
    except Exception as e:
        return OCResult(
            method="Full Pipeline",
            image=image_path,
            success=False,
            confidence=0,
            time_seconds=time.time() - start,
            text_length=0,
            numbers_found=[],
            vote_counts={},
            error=str(e)
        )


def print_results(results: list[OCResult]):
    """Print results in a formatted table."""
    print("\n" + "=" * 100)
    print("OCR EVALUATION RESULTS")
    print("=" * 100)

    # Group by method
    methods = ["Tesseract", "EasyOCR", "Full Pipeline"]

    for method in methods:
        method_results = [r for r in results if r.method == method]
        if not method_results:
            continue

        print(f"\n### {method} ###")
        print("-" * 80)
        print(f"{'Image':<25} {'Success':<8} {'Conf%':<8} {'Time':<8} {'TextLen':<8} {'Votes':<8}")
        print("-" * 80)

        total_conf = 0
        total_time = 0
        success_count = 0

        for r in method_results:
            status = "OK" if r.success else "FAIL"
            conf = f"{r.confidence:.1f}" if r.success else "-"
            time_s = f"{r.time_seconds:.2f}s"
            text_len = str(r.text_length) if r.text_length else "-"
            votes = str(len(r.vote_counts)) if r.vote_counts else "0"

            print(f"{Path(r.image).name:<25} {status:<8} {conf:<8} {time_s:<8} {text_len:<8} {votes:<8}")

            if r.success:
                total_conf += r.confidence
                total_time += r.time_seconds
                success_count += 1

        print("-" * 80)
        if success_count > 0:
            avg_conf = total_conf / success_count
            avg_time = total_time / success_count
            print(f"{'AVERAGES':<25} {success_count}/{len(method_results):<5} {avg_conf:.1f}%    {avg_time:.2f}s")

    # Summary comparison
    print("\n" + "=" * 100)
    print("SUMMARY COMPARISON")
    print("=" * 100)
    print(f"{'Method':<20} {'Success Rate':<15} {'Avg Confidence':<15} {'Avg Time':<12} {'Best For'}")
    print("-" * 100)

    for method in methods:
        method_results = [r for r in results if r.method == method]
        if not method_results:
            continue

        success_count = sum(1 for r in method_results if r.success)
        success_rate = success_count / len(method_results) * 100

        if success_count > 0:
            avg_conf = sum(r.confidence for r in method_results if r.success) / success_count
            avg_time = sum(r.time_seconds for r in method_results if r.success) / success_count
        else:
            avg_conf = 0
            avg_time = 0

        # Determine best use case
        if method == "Tesseract":
            best_for = "Offline, printed text"
        elif method == "EasyOCR":
            best_for = "Handwritten text, Thai"
        else:
            best_for = "Structured data extraction"

        print(f"{method:<20} {success_count}/{len(method_results)} ({success_rate:.0f}%){' ':>4} {avg_conf:.1f}%{' ':>8} {avg_time:.2f}s{' ':>5} {best_for}")


def main():
    """Run OCR evaluation."""
    print("=" * 100)
    print("THAI BALLOT OCR EVALUATION")
    print("=" * 100)

    # Find test images
    test_images = list(Path("test_images").glob("*.png"))
    if not test_images:
        print("No test images found in test_images/")
        return 1

    print(f"\nFound {len(test_images)} test images:")
    for img in test_images:
        print(f"  - {img}")

    print("\nRunning OCR evaluation...")
    print("Note: Cloud AI (OpenRouter) is disabled for local-only comparison")

    results = []

    for i, image_path in enumerate(test_images, 1):
        print(f"\n[{i}/{len(test_images)}] Processing: {image_path.name}")

        # Evaluate each method
        print("  - Tesseract...", end=" ", flush=True)
        r = evaluate_tesseract(str(image_path))
        results.append(r)
        print(f"{'OK' if r.success else 'FAIL'} ({r.time_seconds:.1f}s)")

        print("  - EasyOCR...", end=" ", flush=True)
        r = evaluate_easyocr(str(image_path))
        results.append(r)
        print(f"{'OK' if r.success else 'FAIL'} ({r.time_seconds:.1f}s)")

        print("  - Full Pipeline...", end=" ", flush=True)
        r = evaluate_full_pipeline(str(image_path))
        results.append(r)
        print(f"{'OK' if r.success else 'FAIL'} ({r.time_seconds:.1f}s)")

    # Print results
    print_results(results)

    return 0


if __name__ == "__main__":
    sys.exit(main())
