#!/usr/bin/env python3
"""
Test suite for Thai Election Ballot OCR accuracy measurement.

Usage:
    python tests/test_accuracy.py --image test_images/high_res_page-1.png
    python tests/test_accuracy.py --all
"""

import json
import os
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from ballot_ocr import extract_ballot_data_with_ai, BallotData


@dataclass
class TestResult:
    """Result of a single test."""
    image: str
    passed: bool
    checks: dict
    extraction: Optional[dict]
    errors: list


def load_ground_truth() -> dict:
    """Load ground truth data."""
    gt_path = Path(__file__).parent / "ground_truth.json"
    with open(gt_path, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_extraction(extraction: BallotData, expected: dict) -> tuple[dict, list]:
    """
    Validate extraction against expected values.
    Returns (checks, errors) tuple.
    """
    checks = {}
    errors = []

    # Check province
    if "province" in expected:
        expected_province = expected["province"]
        actual_province = extraction.province
        province_match = actual_province == expected_province
        checks["province"] = {
            "expected": expected_province,
            "actual": actual_province,
            "pass": province_match
        }
        if not province_match:
            errors.append(f"Province mismatch: expected '{expected_province}', got '{actual_province}'")

    # Check form type
    if "form_type" in expected:
        expected_form = expected["form_type"]
        actual_form = extraction.form_type
        form_match = actual_form == expected_form
        checks["form_type"] = {
            "expected": expected_form,
            "actual": actual_form,
            "pass": form_match
        }
        if not form_match:
            errors.append(f"Form type mismatch: expected '{expected_form}', got '{actual_form}'")

    # Check form type pattern (for party-list forms)
    if "form_type_pattern" in expected:
        import re
        pattern = expected["form_type_pattern"]
        actual_form = extraction.form_type
        form_match = bool(re.match(pattern, actual_form))
        checks["form_type_pattern"] = {
            "expected": pattern,
            "actual": actual_form,
            "pass": form_match
        }
        if not form_match:
            errors.append(f"Form type pattern mismatch: '{actual_form}' doesn't match '{pattern}'")

    # Check is_party_list
    if "is_party_list" in expected:
        expected_pl = expected["is_party_list"]
        actual_pl = extraction.form_category == "party_list"
        pl_match = actual_pl == expected_pl
        checks["is_party_list"] = {
            "expected": expected_pl,
            "actual": actual_pl,
            "pass": pl_match
        }
        if not pl_match:
            errors.append(f"Party-list mismatch: expected {expected_pl}, got {actual_pl}")

    # Check form category
    if "form_category" in expected:
        expected_cat = expected["form_category"]
        actual_cat = extraction.form_category
        cat_match = actual_cat == expected_cat
        checks["form_category"] = {
            "expected": expected_cat,
            "actual": actual_cat,
            "pass": cat_match
        }
        if not cat_match:
            errors.append(f"Form category mismatch: expected '{expected_cat}', got '{actual_cat}'")

    # Check constituency number
    if "constituency_number" in expected:
        expected_cons = expected["constituency_number"]
        actual_cons = extraction.constituency_number
        cons_match = actual_cons == expected_cons
        checks["constituency_number"] = {
            "expected": expected_cons,
            "actual": actual_cons,
            "pass": cons_match
        }
        if not cons_match:
            errors.append(f"Constituency number mismatch: expected {expected_cons}, got {actual_cons}")

    # Check polling unit
    if "polling_unit" in expected:
        expected_unit = expected["polling_unit"]
        actual_unit = extraction.polling_unit
        unit_match = actual_unit == expected_unit
        checks["polling_unit"] = {
            "expected": expected_unit,
            "actual": actual_unit,
            "pass": unit_match
        }
        if not unit_match:
            errors.append(f"Polling unit mismatch: expected {expected_unit}, got {actual_unit}")

    return checks, errors


def test_image(image_path: str, ground_truth: dict) -> TestResult:
    """Test a single image against ground truth."""
    image_name = Path(image_path).name

    if image_name not in ground_truth["test_images"]:
        return TestResult(
            image=image_name,
            passed=False,
            checks={},
            extraction=None,
            errors=[f"No ground truth found for {image_name}"]
        )

    expected = ground_truth["test_images"][image_name]["expected"]

    print(f"\n{'='*60}")
    print(f"Testing: {image_name}")
    print(f"Description: {ground_truth['test_images'][image_name]['description']}")
    print(f"{'='*60}")

    # Extract data
    extraction = extract_ballot_data_with_ai(image_path)

    if extraction is None:
        return TestResult(
            image=image_name,
            passed=False,
            checks={},
            extraction=None,
            errors=["Extraction failed - returned None"]
        )

    # Validate
    checks, errors = validate_extraction(extraction, expected)

    # Print results
    print("\nChecks:")
    for check_name, check_data in checks.items():
        status = "✓" if check_data["pass"] else "✗"
        print(f"  {status} {check_name}: expected={check_data['expected']}, actual={check_data['actual']}")

    if errors:
        print("\nErrors:")
        for error in errors:
            print(f"  - {error}")

    passed = len(errors) == 0

    # Convert extraction to dict for serialization
    extraction_dict = {
        "form_type": extraction.form_type,
        "form_category": extraction.form_category,
        "province": extraction.province,
        "constituency_number": extraction.constituency_number,
        "district": extraction.district,
        "polling_unit": extraction.polling_unit,
        "vote_counts": extraction.vote_counts,
        "party_votes": extraction.party_votes,
        "valid_votes": extraction.valid_votes,
        "invalid_votes": extraction.invalid_votes,
        "blank_votes": extraction.blank_votes,
        "total_votes": extraction.total_votes,
    }

    return TestResult(
        image=image_name,
        passed=passed,
        checks=checks,
        extraction=extraction_dict,
        errors=errors
    )


def run_all_tests(test_images_dir: str = "test_images") -> list:
    """Run tests on all images in test_images directory."""
    ground_truth = load_ground_truth()
    results = []

    test_dir = Path(test_images_dir)
    if not test_dir.exists():
        print(f"Error: Test images directory not found: {test_images_dir}")
        return results

    for image_path in sorted(test_dir.glob("*.png")):
        result = test_image(str(image_path), ground_truth)
        results.append(result)

    return results


def print_summary(results: list):
    """Print test summary."""
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)

    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed

    print(f"\nTotal: {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Accuracy: {passed/total*100:.1f}%" if total > 0 else "N/A")

    if failed > 0:
        print("\nFailed tests:")
        for r in results:
            if not r.passed:
                print(f"  - {r.image}: {len(r.errors)} errors")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Test ballot OCR accuracy")
    parser.add_argument("--image", "-i", help="Test a single image")
    parser.add_argument("--all", "-a", action="store_true", help="Test all images")
    parser.add_argument("--output", "-o", help="Output results to JSON file")
    parser.add_argument("--test-images-dir", default="test_images", help="Directory containing test images")

    args = parser.parse_args()

    results = []

    if args.image:
        ground_truth = load_ground_truth()
        result = test_image(args.image, ground_truth)
        results.append(result)
    elif args.all:
        results = run_all_tests(args.test_images_dir)
    else:
        parser.print_help()
        return

    print_summary(results)

    if args.output:
        output_data = [
            {
                "image": r.image,
                "passed": r.passed,
                "checks": r.checks,
                "extraction": r.extraction,
                "errors": r.errors
            }
            for r in results
        ]
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        print(f"\nResults saved to: {args.output}")


if __name__ == "__main__":
    main()
