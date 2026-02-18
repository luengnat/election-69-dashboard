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

# Re-export everything for backwards compatibility
from ballot_types import *
from ballot_extraction import *
from ballot_validation import *
from ballot_aggregation import *
from ballot_reporting import *
from ballot_pdf import *

# Explicit re-exports for names that appear in multiple submodules
from ballot_extraction import ECT_AVAILABLE  # noqa: F401,F811
from ballot_pdf import HAS_REPORTLAB        # noqa: F401,F811

import os
import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from batch_processor import BatchResult

def main():
    """Main entry point."""
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
    parser.add_argument("--parallel", action="store_true", help="Enable parallel processing with ThreadPoolExecutor")
    parser.add_argument("--workers", type=int, default=5, help="Number of concurrent workers for parallel processing (default: 5)")

    args = parser.parse_args()

    input_path = args.input

    # Determine what to process
    if os.path.isdir(input_path) or args.batch:
        # Process directory of images and/or PDFs
        images = []
        pdfs = []

        # Find all images
        for ext in ["*.png", "*.jpg", "*.jpeg"]:
            images.extend(sorted(Path(input_path).glob(ext)))

        # Find all PDFs recursively
        for root, dirs, files in os.walk(input_path):
            for f in files:
                if f.lower().endswith('.pdf'):
                    pdfs.append(os.path.join(root, f))

        if not images and not pdfs:
            print(f"No images or PDFs found in {input_path}")
            return

        print(f"Found {len(images)} images and {len(pdfs)} PDFs in {input_path}")

        # Convert PDFs to images
        if pdfs:
            temp_dir = "/tmp/ballot_images"
            os.makedirs(temp_dir, exist_ok=True)
            print(f"\nConverting {len(pdfs)} PDFs to images...")
            for pdf_path in pdfs:
                try:
                    pdf_images = pdf_to_images(pdf_path, temp_dir)
                    images.extend([Path(img) for img in pdf_images])
                    print(f"  {os.path.basename(pdf_path)}: {len(pdf_images)} pages")
                except Exception as e:
                    print(f"  {os.path.basename(pdf_path)}: ERROR - {e}")

        print(f"\nTotal images to process: {len(images)}")
    elif input_path.lower().endswith(".pdf"):
        # Create temp directory for images if PDF
        temp_dir = "/tmp/ballot_images"
        os.makedirs(temp_dir, exist_ok=True)
        print("Converting PDF to images...")
        images = pdf_to_images(input_path, temp_dir)
        print(f"Created {len(images)} images")
    else:
        images = [input_path]

    # Create report directory if needed
    if args.reports:
        os.makedirs(args.report_dir, exist_ok=True)

    # Process images (parallel or sequential)
    results = []
    ballot_data_list = []
    processing_errors = []

    if args.parallel and len(images) > 1:
        # Use BatchProcessor for parallel processing
        print(f"\nProcessing {len(images)} images in parallel with {args.workers} workers...")
        from batch_processor import BatchProcessor
        processor = BatchProcessor(max_workers=args.workers, rate_limit=2.0)
        batch_result = processor.process_batch([str(img) for img in images])

        ballot_data_list = batch_result.results
        processing_errors = batch_result.errors

        if processing_errors:
            print(f"\nWarning: {len(processing_errors)} images failed to process")
            for err in processing_errors:
                print(f"  - {err['path']}: {err['error']}")

        print(f"\nSuccessfully processed {batch_result.processed}/{batch_result.total} images")
    else:
        # Sequential processing (default)
        for i, image_path in enumerate(images, 1):
            print(f"\nProcessing: {image_path}")
            ballot_data = extract_ballot_data_with_ai(image_path)
            if ballot_data:
                ballot_data_list.append(ballot_data)

    # Process results (verification and reporting)
    for i, ballot_data in enumerate(ballot_data_list, 1):
        print(f"\nResult {i}: {ballot_data.source_file}")
        print(f"  Form type: {ballot_data.form_type}")
        print(f"  Category: {ballot_data.form_category}")
        print(f"  Station: {ballot_data.polling_station_id}")
        if ballot_data.form_category == "party_list":
            print(f"  Party votes: {ballot_data.party_votes}")
        else:
            print(f"  Vote counts: {ballot_data.vote_counts}")
        print(f"  Total: {ballot_data.total_votes}")

        discrepancy_report = None

        if args.verify:
            verification = verify_with_ect_data(ballot_data, "")
            results.append(verification)
            discrepancy_report = verification
        else:
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
            results.append(result)

        # Generate individual report if requested
        if args.reports:
            report_filename = f"{args.report_dir}/ballot_{i:03d}.md"
            report = generate_single_ballot_report(ballot_data, discrepancy_report=discrepancy_report)
            save_report(report, report_filename)

            # Also generate PDF if requested
            if args.pdf:
                pdf_filename = f"{args.report_dir}/ballot_{i:03d}.pdf"
                generate_ballot_pdf(ballot_data, pdf_filename)

    # Save results
    with open(args.output, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\nResults saved to: {args.output}")

    # Aggregate results by constituency if requested (do this first so batch PDF can use it)
    aggregated_results = {}
    if args.aggregate and len(ballot_data_list) > 1:
        print("\nAggregating results by constituency...")
        aggregated_results = aggregate_ballot_results(ballot_data_list)

        # Save aggregated results
        aggregated_output = args.output.replace('.json', '_aggregated.json')
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
                "overall_total": agg.overall_total,
                "aggregated_confidence": agg.aggregated_confidence,
                "discrepancy_rate": agg.discrepancy_rate,
                "winners": agg.winners,
            }
            if agg.candidate_totals:
                aggregated_data[key]["candidate_totals"] = agg.candidate_totals
            if agg.party_totals:
                aggregated_data[key]["party_totals"] = agg.party_totals

        with open(aggregated_output, "w") as f:
            json.dump(aggregated_data, f, indent=2, ensure_ascii=False)
        print(f"Aggregated results saved to: {aggregated_output}")

        # Generate constituency reports and PDFs
        for (province, cons_no), agg in aggregated_results.items():
            cons_key = f"{province}_{cons_no}"

            if args.reports:
                # Markdown report
                cons_report = generate_constituency_report(agg)
                cons_report_filename = f"{args.report_dir}/constituency_{cons_key}.md"
                save_report(cons_report, cons_report_filename)
                print(f"Constituency report saved to: {cons_report_filename}")

            if args.pdf:
                # PDF report
                cons_pdf_filename = f"{args.report_dir}/constituency_{cons_key}.pdf"
                generate_constituency_pdf(agg, cons_pdf_filename)

        # Generate executive summary PDF if requested
        if args.pdf and len(aggregated_results) > 1:
            all_agg_results = list(aggregated_results.values())
            anomalies = detect_anomalous_constituencies(aggregated_results)
            exec_summary_pdf = f"{args.report_dir}/EXECUTIVE_SUMMARY.pdf"
            generate_executive_summary_pdf(all_agg_results, anomalies, exec_summary_pdf)

    # Generate batch report if requested and multiple ballots
    if args.reports and len(ballot_data_list) > 1:
        batch_report_filename = f"{args.report_dir}/BATCH_SUMMARY.md"
        batch_report = generate_batch_report(results, ballot_data_list)
        save_report(batch_report, batch_report_filename)
        print(f"Batch report saved to: {batch_report_filename}")

        # Also generate batch PDF if requested (with charts if aggregated data available)
        if args.pdf:
            batch_pdf_filename = f"{args.report_dir}/BATCH_SUMMARY.pdf"
            generate_batch_pdf(aggregated_results, ballot_data_list, batch_pdf_filename)


if __name__ == "__main__":
    main()
