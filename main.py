#!/usr/bin/env python3
"""
Ballot OCR for Thai election verification.

This module is a thin re-export shim. All implementation lives in:
  ballot_types.py       — data types and Thai numeral utilities
  ballot_extraction.py  — AI vision extraction
  ballot_validation.py  — discrepancy detection and ECT verification
  ballot_aggregation.py — result aggregation and statistics
  ballot_reporting.py   — markdown report generation
  ballot_pdf.py         — PDF report generation
  crop_utils.py         — form-aware image cropping
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from argparse import ArgumentParser, Namespace
from typing import TYPE_CHECKING

# Re-export key components for backwards compatibility
from ballot_types import BallotData, FormType, AggregatedResults, convert_thai_numerals, validate_vote_entry, thai_text_to_number, VoteEntry
from ballot_extraction import extract_ballot_data_with_ai, ECT_AVAILABLE, pdf_to_images
from ballot_validation import detect_discrepancies, verify_with_ect_data
from ballot_aggregation import aggregate_ballot_results, aggregate_constituency
from ballot_reporting import generate_constituency_report, save_report
from ballot_pdf import generate_constituency_pdf, generate_batch_pdf, generate_one_page_executive_summary_pdf, HAS_REPORTLAB

if TYPE_CHECKING:
    from batch_processor import BatchResult

def _get_parser() -> "argparse.ArgumentParser":
    """Create the argument parser for ballot_ocr."""
    import argparse
    parser = argparse.ArgumentParser(description="Extract and verify ballot data")
    parser.add_argument("input", help="PDF, image file, or directory to process")
    parser.add_argument("--output", "-o", help="Output JSON file", default="ballot_data.json")
    parser.add_argument("--verify", action="store_true", help="Verify against ECT API")
    parser.add_argument("--batch", "-b", action="store_true", help="Process directory of images")
    parser.add_argument("--reports", "-r", action="store_true", help="Generate markdown reports")
    parser.add_argument("--pdf", "-p", action="store_true", help="Generate PDF reports")
    parser.add_argument("--aggregate", "-a", action="store_true", help="Aggregate results by constituency")
    parser.add_argument("--report-dir", default="reports", help="Directory to save reports")
    parser.add_argument("--parallel", action="store_true", help="Enable parallel processing (auto-enabled for directories)")
    parser.add_argument("--no-parallel", action="store_true", help="Disable automatic parallel processing")
    parser.add_argument("--workers", type=int, default=5, help="Number of concurrent workers (default: 5)")
    parser.add_argument("--rate-limit", type=float, default=2.0, help="API requests per second (default: 2.0)")
    parser.add_argument("--no-cache", action="store_true", help="Disable persistent result caching")
    parser.add_argument("--checkpoint", action="store_true", help="Enable checkpoint/resume for interrupted batch jobs")
    parser.add_argument("--verbose", "-v", action="count", default=0, help="Increase verbosity (-v, -vv)")
    return parser


def _find_images_and_pdfs(input_path: str) -> tuple[list[Path], list[str]]:
    """Scan directory for images and PDFs."""
    images = []
    pdfs = []
    
    for ext in ["*.png", "*.jpg", "*.jpeg"]:
        images.extend(sorted(Path(input_path).glob(ext)))

    for root, _, files in os.walk(input_path):
        for f in files:
            if f.lower().endswith('.pdf'):
                pdfs.append(os.path.join(root, f))
    
    return images, pdfs


def _convert_pdfs_to_images(pdfs: list[str]) -> list[Path]:
    """Convert a list of PDFs into images in a temp directory."""
    images = []
    if not pdfs:
        return images

    temp_dir = tempfile.mkdtemp(prefix="ballot_images_")
    print(f"\nConverting {len(pdfs)} PDFs to images...")
    for pdf_path in pdfs:
        try:
            pdf_images = pdf_to_images(pdf_path, temp_dir)
            images.extend([Path(img) for img in pdf_images])
            print(f"  {os.path.basename(pdf_path)}: {len(pdf_images)} pages")
        except Exception as e:
            print(f"  {os.path.basename(pdf_path)}: ERROR - {e}")
    return images


def _collect_images(input_path: str, force_batch: bool = False) -> list[Path]:
    """Find all images (PNG, JPG) and convert PDFs to images in the input path."""
    if os.path.isdir(input_path) or force_batch:
        images, pdfs = _find_images_and_pdfs(input_path)
        
        if not images and not pdfs:
            print(f"No images or PDFs found in {input_path}")
            return []

        print(f"Found {len(images)} images and {len(pdfs)} PDFs in {input_path}")
        if pdfs:
            images.extend(_convert_pdfs_to_images(pdfs))
        return images
        
    if input_path.lower().endswith(".pdf"):
        return _convert_pdfs_to_images([input_path])

    return [Path(input_path)]


def _reconstruct_ballot_dict(ballot_data) -> dict:
    """Reconstruct a dictionary representation of ballot data for JSON saving."""
    result = {
        "form_type": ballot_data.form_type,
        "form_category": ballot_data.form_category,
        "province": ballot_data.province,
        "constituency_number": ballot_data.constituency_number,
        "district": ballot_data.district,
        "polling_unit": ballot_data.polling_unit,
        "polling_station": ballot_data.polling_station_id,
        "valid_votes": ballot_data.valid_votes,
        "invalid_votes": ballot_data.invalid_votes,
        "blank_votes": ballot_data.blank_votes,
        "total_votes": ballot_data.total_votes,
        "confidence_score": ballot_data.confidence_score,
        "confidence_level": ballot_data.confidence_details.get("level", "UNKNOWN"),
        "source_file": ballot_data.source_file,
    }

    if ballot_data.form_category == "party_list":
        result["page_parties"] = ballot_data.page_parties
        result["party_votes"] = ballot_data.party_votes
        if ballot_data.party_info:
            result["party_info"] = ballot_data.party_info
    else:
        result["vote_counts"] = ballot_data.vote_counts
        if ballot_data.candidate_info:
            result["candidate_info"] = ballot_data.candidate_info
    return result


def _process_results(args, ballot_data_list) -> list[dict]:
    """Loop over results, verify if requested, and generate reports."""
    results = []
    for i, ballot_data in enumerate(ballot_data_list, 1):
        print(f"\nResult {i}: {ballot_data.source_file}")

        discrepancy_report = None
        if args.verify:
            verification = verify_with_ect_data(ballot_data, "")
            results.append(verification)
            discrepancy_report = verification
        else:
            results.append(_reconstruct_ballot_dict(ballot_data))

        if args.reports:
            report_filename = f"{args.report_dir}/ballot_{i:03d}.md"
            report = generate_single_ballot_report(ballot_data, discrepancy_report=discrepancy_report)
            save_report(report, report_filename)

            if args.pdf:
                generate_ballot_pdf(ballot_data, f"{args.report_dir}/ballot_{i:03d}.pdf")

    return results


def _handle_aggregation(args, ballot_data_list):
    """Aggregate results by constituency and save to JSON."""
    if not args.aggregate or len(ballot_data_list) <= 1:
        return

    print("\nAggregating results by constituency...")
    aggregated_results = aggregate_ballot_results(ballot_data_list)

    # Convert to serializable format
    aggregated_data = {}
    for (province, cons_no), agg in aggregated_results.items():
        key = f"{province}_{cons_no}"
        aggregated_data[key] = {
            "province": agg.province,
            "constituency": agg.constituency,
            "constituency_no": agg.constituency_no,
            "ballots_processed": agg.ballots_processed,
            "polling_units_reporting": agg.polling_units_reporting,
            "valid_votes_total": agg.valid_votes_total,
            "invalid_votes_total": agg.invalid_votes_total,
            "blank_votes_total": agg.blank_votes_total,
            "total_votes_agg": agg.total_votes_agg,
            "party_totals": agg.party_totals,
            "candidate_totals": agg.candidate_totals
        }

    aggregated_output = args.output.replace('.json', '_aggregated.json')
    with open(aggregated_output, "w") as f:
        json.dump(aggregated_data, f, indent=2, ensure_ascii=False)

    print(f"Aggregated results saved to: {aggregated_output}")

    # Generate constituency reports and PDFs
    for (province, cons_no), agg in aggregated_results.items():
        cons_key = f"{province}_{cons_no}"

        if args.reports:
            save_report(generate_constituency_report(agg), f"{args.report_dir}/constituency_{cons_key}.md")

        if args.pdf:
            generate_constituency_pdf(agg, f"{args.report_dir}/constituency_{cons_key}.pdf")

    # Generate executive summary PDF
    if args.pdf and len(aggregated_results) > 1:
        anomalies = detect_anomalous_constituencies(aggregated_results)
        generate_executive_summary_pdf(list(aggregated_results.values()), anomalies, f"{args.report_dir}/EXECUTIVE_SUMMARY.pdf")


def _generate_batch_reports(args, results, ballot_data_list):
    """Generate summary reports for the entire batch."""
    if not args.reports or len(ballot_data_list) <= 1:
        return

    batch_report_filename = f"{args.report_dir}/BATCH_SUMMARY.md"
    save_report(generate_batch_report(results, ballot_data_list), batch_report_filename)
    print(f"Batch report saved to: {batch_report_filename}")

    if args.pdf:
        batch_pdf_filename = f"{args.report_dir}/BATCH_SUMMARY.pdf"
        # Try to get aggregated data if it was generated
        aggregated_results = aggregate_ballot_results(ballot_data_list) if args.aggregate else {}
        generate_batch_pdf(aggregated_results, ballot_data_list, batch_pdf_filename)


def main(args=None):
    """Main entry point."""
    if args is None:
        args = _get_parser().parse_args()

    # 1. Collect inputs
    images = _collect_images(args.input, force_batch=getattr(args, "batch", False))
    if not images:
        return

    # 2. Setup environment
    if args.reports:
        os.makedirs(args.report_dir, exist_ok=True)

    # 3. Execution via BatchProcessor
    from batch_processor import BatchProcessor, ConsoleProgressCallback, NullProgressCallback

    use_parallel = (os.path.isdir(args.input) and not getattr(args, "no_parallel", False)) or getattr(args, "parallel", False)
    verbose = getattr(args, "verbose", 0)

    print(f"\nProcessing {len(images)} image(s) {'in parallel' if use_parallel else 'sequentially'}...")

    processor = BatchProcessor(
        max_workers=args.workers if use_parallel else 1,
        rate_limit=getattr(args, "rate_limit", 2.0),
        use_cache=not getattr(args, "no_cache", False),
        verbose=verbose > 0,
    )
    batch_result = processor.process_batch(
        [str(img) for img in images],
        progress_callback=ConsoleProgressCallback() if verbose > 0 else NullProgressCallback(),
        checkpoint_file=os.path.join(args.report_dir, "checkpoint.jsonl") if getattr(args, "checkpoint", False) else None,
    )

    if batch_result.errors:
        print(f"\nWarning: {len(batch_result.errors)} image(s) failed to process", file=sys.stderr)
        for err in batch_result.errors:
            print(f"  - {err['path']}: {err['error']}", file=sys.stderr)

    # 4. Results & Reporting
    results = _process_results(args, batch_result.results)

    with open(args.output, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\nSuccessfully processed {batch_result.processed}/{batch_result.total} images")
    print(f"Results saved to: {args.output}")

    # 5. Aggregation
    _handle_aggregation(args, batch_result.results)

    # 6. Batch Summary
    _generate_batch_reports(args, results, batch_result.results)


if __name__ == "__main__":
    main()
