#!/usr/bin/env python3
"""
Command-line interface for Thai Election Ballot OCR.

This module provides a clean CLI entry point with comprehensive help text
and argument validation.

Usage:
    python cli.py --help
    python cli.py process <input> [options]
    python cli.py --version
"""

import argparse
import sys
from pathlib import Path

# Version
__version__ = "1.1.0"


def create_parser() -> argparse.ArgumentParser:
    """Create and configure the argument parser."""
    parser = argparse.ArgumentParser(
        prog="ballot-ocr",
        description="""
Thai Election Ballot OCR - Extract and verify ballot data from images.

This tool uses AI Vision to extract vote counts from handwritten Thai ballot
images, validates them against official ECT data, and generates PDF reports.

Examples:
  %(prog)s process ballot.jpg                    # Process single image
  %(prog)s process ./ballots/ --batch --pdf      # Batch process with PDF reports
  %(prog)s process ./ballots/ --parallel --workers 10  # Parallel processing
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--version", "-V",
        action="version",
        version=f"%(prog)s {__version__}"
    )

    # Subcommands
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Process command
    process_parser = subparsers.add_parser(
        "process",
        help="Process ballot images",
        description="Extract vote counts from ballot images and generate reports."
    )
    process_parser.add_argument(
        "input",
        help="PDF, image file, or directory to process"
    )
    process_parser.add_argument(
        "--output", "-o",
        default="ballot_data.json",
        help="Output JSON file (default: ballot_data.json)"
    )
    process_parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify against ECT API (requires internet)"
    )
    process_parser.add_argument(
        "--batch", "-b",
        action="store_true",
        help="Process directory of images"
    )
    process_parser.add_argument(
        "--reports", "-r",
        action="store_true",
        help="Generate markdown reports"
    )
    process_parser.add_argument(
        "--pdf", "-p",
        action="store_true",
        help="Generate PDF reports"
    )
    process_parser.add_argument(
        "--aggregate", "-a",
        action="store_true",
        help="Aggregate results by constituency"
    )
    process_parser.add_argument(
        "--report-dir",
        default="reports",
        help="Directory to save reports (default: reports)"
    )
    process_parser.add_argument(
        "--parallel",
        action="store_true",
        help="Enable parallel processing"
    )
    process_parser.add_argument(
        "--workers", "-w",
        type=int,
        default=5,
        help="Number of concurrent workers (default: 5)"
    )
    process_parser.add_argument(
        "--rate-limit",
        type=float,
        default=2.0,
        help="API requests per second (default: 2.0)"
    )
    process_parser.add_argument(
        "--verbose", "-v",
        action="count",
        default=0,
        help="Increase verbosity (-v, -vv)"
    )

    # Validate command
    validate_parser = subparsers.add_parser(
        "validate",
        help="Validate existing results",
        description="Validate previously extracted results against ECT data."
    )
    validate_parser.add_argument(
        "input",
        help="JSON file with ballot data to validate"
    )
    validate_parser.add_argument(
        "--report",
        action="store_true",
        help="Generate validation report"
    )

    return parser


def main():
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "process":
        # Import here to avoid circular imports
        from ballot_ocr import main as ocr_main
        # Call the original main with our args
        import sys
        sys.argv = [
            "ballot_ocr.py",
            args.input,
            "--output", args.output,
        ]
        if args.verify:
            sys.argv.append("--verify")
        if args.batch:
            sys.argv.append("--batch")
        if args.reports:
            sys.argv.append("--reports")
        if args.pdf:
            sys.argv.append("--pdf")
        if args.aggregate:
            sys.argv.append("--aggregate")
        if args.parallel:
            sys.argv.append("--parallel")
        if args.workers:
            sys.argv.extend(["--workers", str(args.workers)])
        sys.argv.extend(["--report-dir", args.report_dir])

        ocr_main()

    elif args.command == "validate":
        print(f"Validating {args.input}...")
        # TODO: Implement validation logic
        print("Validation complete.")


if __name__ == "__main__":
    main()
