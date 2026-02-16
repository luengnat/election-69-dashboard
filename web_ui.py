"""
Gradio Web UI for Thai Election Ballot OCR.

Provides a web interface with multi-file upload and real-time progress tracking
for batch processing ballot images.

Usage:
    python web_ui.py

Then open http://localhost:7860 in your browser.

Features:
- Multi-file upload (100-500 images supported)
- Real-time progress bar during processing
- Thai text support (UTF-8 throughout)
- Clear error messages with filename context
- Results sorted by filename, limited to 100 for display
"""

import gradio as gr
from typing import Optional
import tempfile
import os
import logging
import json
import csv
from pathlib import Path
from dataclasses import asdict

from batch_processor import BatchProcessor, BallotData, BatchResult
from ballot_ocr import (
    aggregate_ballot_results,
    generate_constituency_pdf,
    generate_batch_pdf,
    generate_one_page_executive_summary_pdf,
    AggregatedResults
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Maximum number of results to display (to avoid UI overload)
MAX_DISPLAY_RESULTS = 100

# File upload validation settings
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB per file
MAX_BATCH_SIZE = 500  # Maximum files per batch
ALLOWED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.pdf'}


def validate_file(file_path: str) -> tuple[bool, str]:
    """
    Validate an uploaded file for security and size constraints.

    Args:
        file_path: Path to the uploaded file

    Returns:
        Tuple of (is_valid, error_message)
    """
    import re

    if not file_path:
        return False, "No file path provided"

    # Check file exists
    if not os.path.isfile(file_path):
        return False, "File not found"

    # Check extension
    ext = Path(file_path).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        return False, f"Invalid file type: {ext}. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"

    # Check file size
    try:
        size = os.path.getsize(file_path)
        if size > MAX_FILE_SIZE:
            return False, f"File too large: {size // (1024*1024)}MB (max {MAX_FILE_SIZE // (1024*1024)}MB)"
        if size == 0:
            return False, "File is empty"
    except OSError as e:
        return False, f"Cannot read file: {e}"

    return True, "OK"


def sanitize_filename(name: str) -> str:
    """
    Sanitize a string for safe use in filenames.
    Removes path traversal attempts and special characters.

    Args:
        name: Input string to sanitize

    Returns:
        Sanitized string safe for use in filenames
    """
    import re
    # Remove any path components
    name = os.path.basename(name)
    # Keep only alphanumeric, spaces, underscores, hyphens, and Thai characters
    sanitized = re.sub(r'[^\w\s\-\u0E00-\u0E7F]', '_', name)
    # Limit length
    return sanitized[:100]


class GradioProgressCallback:
    """
    Progress callback for Gradio web interface.

    Implements the ProgressCallback protocol from batch_processor.py,
    updating a Gradio progress bar during batch processing.

    Args:
        progress: Optional gr.Progress() object for progress updates

    Example:
        with gr.Blocks() as demo:
            def process(files, progress=gr.Progress()):
                callback = GradioProgressCallback(progress)
                processor = BatchProcessor()
                result = processor.process_batch(paths, progress_callback=callback)
    """

    def __init__(self, progress: Optional[gr.Progress] = None):
        self.progress = progress
        self._errors: list[dict] = []

    def on_start(self, total: int) -> None:
        """Called when batch processing starts."""
        if self.progress:
            self.progress(0, desc=f"Starting batch of {total} images...")

    def on_progress(self, current: int, total: int, path: str, result: Optional[BallotData]) -> None:
        """Called after each ballot is successfully processed."""
        if self.progress:
            # Get filename from path for cleaner display
            filename = os.path.basename(path) if path else "unknown"
            self.progress(current / total, desc=f"[{current}/{total}] {filename}")

    def on_error(self, current: int, total: int, path: str, error: str) -> None:
        """Called when a ballot processing fails."""
        self._errors.append({"path": path, "error": error})
        if self.progress:
            filename = os.path.basename(path) if path else "unknown"
            self.progress(current / total, desc=f"[{current}/{total}] Error on {filename}")

    def on_complete(self, results: list, errors: list) -> None:
        """Called when batch processing completes."""
        if self.progress:
            success_count = len(results) if results else 0
            error_count = len(errors) if errors else 0
            self.progress(1.0, desc=f"Complete: {success_count} succeeded, {error_count} failed")

    @property
    def errors(self) -> list[dict]:
        """Return list of errors encountered during processing."""
        return self._errors


def format_vote_summary(ballot: BallotData) -> str:
    """
    Create a compact vote summary string for display in the results table.

    Args:
        ballot: BallotData object with vote information

    Returns:
        Formatted string like "6 candidates, 1,234 total" or "Party 1: 100, Party 2: 50"
    """
    if ballot.form_category == "party_list":
        # Party-list form: show top 3 parties with votes
        if ballot.party_votes:
            sorted_parties = sorted(ballot.party_votes.items(), key=lambda x: x[1], reverse=True)[:3]
            vote_strs = [f"P{p}:{v}" for p, v in sorted_parties]
            total = sum(ballot.party_votes.values())
            return f"{', '.join(vote_strs)}... ({total:,} total)"
        return "-"
    else:
        # Constituency form: show candidate count and total
        if ballot.vote_counts:
            num_candidates = len(ballot.vote_counts)
            total_votes = sum(ballot.vote_counts.values())
            return f"{num_candidates} candidates, {total_votes:,} total"
        return "-"


def format_vote_table(ballot: BallotData) -> str:
    """
    Create a detailed vote breakdown string for expanded view.

    Args:
        ballot: BallotData object with vote information

    Returns:
        Formatted string with all vote details, one per line
    """
    lines = []

    if ballot.form_category == "party_list":
        # Party-list form: show all parties with names and votes
        if ballot.party_votes:
            sorted_parties = sorted(ballot.party_votes.items(), key=lambda x: x[1], reverse=True)
            for party_num, votes in sorted_parties:
                # Get party info if available
                info = ballot.party_info.get(party_num, {})
                name = info.get("name", "")
                abbr = info.get("abbr", "")
                if name:
                    lines.append(f"Party {party_num} ({abbr}): {votes:,}")
                else:
                    lines.append(f"Party {party_num}: {votes:,}")
    else:
        # Constituency form: show all candidates with names and votes
        if ballot.vote_counts:
            sorted_candidates = sorted(ballot.vote_counts.items(), key=lambda x: x[1], reverse=True)
            for position, votes in sorted_candidates:
                # Get candidate info if available
                info = ballot.candidate_info.get(position, {})
                name = info.get("name", "")
                party = info.get("party_abbr", "")
                if name:
                    lines.append(f"#{position} {name} ({party}): {votes:,}")
                else:
                    lines.append(f"Candidate #{position}: {votes:,}")

    # Add vote category totals
    if ballot.valid_votes or ballot.invalid_votes or ballot.blank_votes:
        lines.append("---")
        if ballot.valid_votes:
            lines.append(f"Valid: {ballot.valid_votes:,}")
        if ballot.invalid_votes:
            lines.append(f"Invalid: {ballot.invalid_votes:,}")
        if ballot.blank_votes:
            lines.append(f"Blank: {ballot.blank_votes:,}")

    return "\n".join(lines) if lines else "-"


def format_results(results: list[BallotData]) -> tuple[list[list], str]:
    """
    Format BallotData results for Gradio Dataframe display.

    Args:
        results: List of BallotData objects from batch processing

    Returns:
        Tuple of (rows for gr.Dataframe, status message)
        Status message indicates if results were truncated.
    """
    if not results:
        return [], ""

    rows = []
    for ballot in results:
        # Get filename from source_file
        filename = os.path.basename(ballot.source_file) if ballot.source_file else "unknown"

        # Determine confidence based on data completeness
        has_province = bool(ballot.province)
        has_constituency = ballot.constituency_number > 0
        has_votes = bool(ballot.vote_counts) or bool(ballot.party_votes)

        if has_province and has_constituency and has_votes:
            confidence = "High"
        elif has_province or has_constituency:
            confidence = "Medium"
        else:
            confidence = "Low"

        # Get vote summary for display
        vote_summary = format_vote_summary(ballot)

        row = [
            filename,
            ballot.province or "-",
            str(ballot.constituency_number) if ballot.constituency_number > 0 else "-",
            ballot.polling_station_id or "-",
            ballot.form_type or "-",
            confidence,
            vote_summary
        ]
        rows.append(row)

    # Sort by filename for predictable display
    rows.sort(key=lambda x: x[0])

    # Limit display and generate status message
    total_count = len(rows)
    if total_count > MAX_DISPLAY_RESULTS:
        display_rows = rows[:MAX_DISPLAY_RESULTS]
        status_msg = f"Showing {MAX_DISPLAY_RESULTS} of {total_count} results"
        logger.info(f"Results truncated: {total_count} total, showing {MAX_DISPLAY_RESULTS}")
    else:
        display_rows = rows
        status_msg = f"Showing {total_count} results"

    return display_rows, status_msg


def generate_pdfs(ballot_results: list[BallotData]) -> tuple[Optional[str], Optional[str]]:
    """
    Generate constituency and batch PDFs from results.

    Args:
        ballot_results: List of BallotData objects from batch processing

    Returns:
        Tuple of (batch_pdf_path, constituency_pdf_path)
        Returns (None, None) if no results to process
    """
    if not ballot_results:
        logger.warning("No ballot results to generate PDFs from")
        return None, None

    try:
        # Create temp directory for PDFs
        pdf_dir = tempfile.mkdtemp(prefix="ballot_pdfs_")
        logger.info(f"Created temp PDF directory: {pdf_dir}")

        # Aggregate results by constituency
        aggregated = aggregate_ballot_results(ballot_results)
        logger.info(f"Aggregated {len(aggregated)} constituencies")

        # Generate batch summary PDF
        batch_pdf_path = os.path.join(pdf_dir, "batch_summary.pdf")
        if generate_batch_pdf(aggregated, ballot_results, batch_pdf_path):
            logger.info(f"Generated batch PDF: {batch_pdf_path}")
        else:
            logger.error("Failed to generate batch PDF")
            batch_pdf_path = None

        # Generate first constituency PDF (for demo - user can generate others later)
        constituency_pdf_path = None
        for key, agg in aggregated.items():
            province, cons_no = key
            # Create safe filename from constituency info
            safe_province = sanitize_filename(province)
            cons_pdf_path = os.path.join(pdf_dir, f"constituency_{safe_province}_{cons_no}.pdf")
            if generate_constituency_pdf(agg, cons_pdf_path):
                constituency_pdf_path = cons_pdf_path
                logger.info(f"Generated constituency PDF: {cons_pdf_path}")
                break  # Just use first one for now

        if not constituency_pdf_path:
            logger.warning("No constituency PDF generated")

        return batch_pdf_path, constituency_pdf_path

    except Exception as e:
        logger.exception(f"Error generating PDFs: {e}")
        return None, None


def process_ballots(files, progress=gr.Progress()) -> tuple[list[list], str, list]:
    """
    Process uploaded ballot images and return results.

    Args:
        files: List of uploaded file paths from gr.File
        progress: Gradio progress tracker

    Returns:
        Tuple of (results_dataframe, error_messages, ballot_results)
        ballot_results is a list of BallotData objects for PDF generation
    """
    logger.info(f"process_ballots called with {len(files) if files else 0} files")

    # Handle empty upload
    if not files:
        logger.warning("No files uploaded")
        return [], "Please upload at least one ballot image.", []

    # Ensure files is a list (Gradio can return single file as string)
    if isinstance(files, str):
        files = [files]
        logger.info("Converted single file to list")

    # Log file info (including Thai filenames)
    for f in files[:5]:  # Log first 5 files
        filename = os.path.basename(f) if f else "unknown"
        logger.info(f"  File: {filename}")
    if len(files) > 5:
        logger.info(f"  ... and {len(files) - 5} more files")

    # Validate batch size
    if len(files) > MAX_BATCH_SIZE:
        logger.warning(f"Batch too large: {len(files)} files (max {MAX_BATCH_SIZE})")
        return [], f"Too many files: {len(files)}. Maximum is {MAX_BATCH_SIZE}.", []

    # Validate all files before processing
    invalid_files = []
    for f in files:
        is_valid, error_msg = validate_file(f)
        if not is_valid:
            filename = os.path.basename(f) if f else "unknown"
            invalid_files.append(f"{filename}: {error_msg}")

    if invalid_files:
        error_list = "\n".join(invalid_files[:10])  # Show first 10 errors
        if len(invalid_files) > 10:
            error_list += f"\n... and {len(invalid_files) - 10} more invalid files"
        logger.warning(f"Found {len(invalid_files)} invalid files")
        return [], f"Invalid files:\n{error_list}", []

    # Create progress callback
    callback = GradioProgressCallback(progress)

    # Create batch processor with rate limiting
    processor = BatchProcessor(max_workers=5, rate_limit=2.0)

    # Process the batch
    try:
        logger.info("Starting batch processing...")
        result = processor.process_batch(files, progress_callback=callback)
        logger.info(f"Batch complete: {result.processed} processed, {len(result.errors)} errors")

        # Format results for display
        results_df, status_msg = format_results(result.results)

        # Format errors for display (numbered list, truncated messages)
        error_parts = []
        if result.errors:
            for i, err in enumerate(result.errors, 1):
                filename = os.path.basename(err.get("path", "unknown"))
                error_msg = err.get("error", "Unknown error")
                # Truncate long error messages to 200 chars
                if len(error_msg) > 200:
                    error_msg = error_msg[:200] + "..."
                # Handle Thai text in error messages (UTF-8 safe)
                error_parts.append(f"{i}. {filename}: {error_msg}")

            # Add error summary
            error_text = f"Errors ({len(result.errors)}):\n" + "\n".join(error_parts)
            logger.warning(f"Batch had {len(result.errors)} errors")
        else:
            error_text = status_msg  # Show status when no errors

        # Return results along with BallotData list for PDF generation
        return results_df, error_text, result.results

    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        return [], f"File error: Could not find uploaded file. Please try again.", []
    except PermissionError as e:
        logger.error(f"Permission error: {e}")
        return [], f"Permission error: Cannot read uploaded files.", []
    except ConnectionError as e:
        logger.error(f"Connection error: {e}")
        return [], f"API connection error: Could not reach OCR service. Please check your internet connection.", []
    except Exception as e:
        logger.exception(f"Unexpected error during processing: {e}")
        # Return user-friendly error message
        error_msg = str(e)
        if len(error_msg) > 200:
            error_msg = error_msg[:200] + "..."
        return [], f"Processing error: {error_msg}", []


def download_batch_pdf(ballot_results: list[BallotData]) -> Optional[str]:
    """
    Download handler for batch summary PDF.

    Args:
        ballot_results: List of BallotData objects from state

    Returns:
        Path to batch PDF file or None if no results
    """
    if not ballot_results:
        logger.warning("No ballot results available for batch PDF")
        return None

    batch_path, _ = generate_pdfs(ballot_results)
    return batch_path


def download_constituency_pdf(ballot_results: list[BallotData]) -> Optional[str]:
    """
    Download handler for constituency report PDF.

    Args:
        ballot_results: List of BallotData objects from state

    Returns:
        Path to constituency PDF file or None if no results
    """
    if not ballot_results:
        logger.warning("No ballot results available for constituency PDF")
        return None

    _, constituency_path = generate_pdfs(ballot_results)
    return constituency_path


def download_executive_summary_pdf(ballot_results: list[BallotData]) -> Optional[str]:
    """
    Download handler for one-page executive summary PDF.

    Args:
        ballot_results: List of BallotData objects from state

    Returns:
        Path to executive summary PDF file or None if no results
    """
    if not ballot_results:
        logger.warning("No ballot results available for executive summary PDF")
        return None

    try:
        # Create temp directory
        pdf_dir = tempfile.mkdtemp(prefix="exec_summary_")

        # Aggregate results
        aggregated = aggregate_ballot_results(ballot_results)
        all_results = list(aggregated.values())

        # Create BatchResult from ballot_results metadata
        batch_result = BatchResult(
            results=ballot_results,
            processed=len(ballot_results),
            total=len(ballot_results),
            duration_seconds=0.0  # Will be populated if available
        )

        # Generate executive summary
        pdf_path = os.path.join(pdf_dir, "executive_summary.pdf")
        if generate_one_page_executive_summary_pdf(all_results, batch_result, pdf_path):
            logger.info(f"Generated executive summary PDF: {pdf_path}")
            return pdf_path
        else:
            logger.error("Failed to generate executive summary PDF")
            return None
    except Exception as e:
        logger.exception(f"Error generating executive summary: {e}")
        return None


def export_json(ballot_results: list[BallotData]) -> Optional[str]:
    """
    Export ballot results to JSON file.

    Args:
        ballot_results: List of BallotData objects from state

    Returns:
        Path to JSON file or None if no results
    """
    if not ballot_results:
        logger.warning("No ballot results available for JSON export")
        return None

    try:
        # Create temp file for JSON
        json_path = tempfile.mktemp(suffix="_ballot_results.json")

        # Convert BallotData to dict for JSON serialization
        data = []
        for ballot in ballot_results:
            ballot_dict = {
                "source_file": ballot.source_file,
                "form_type": ballot.form_type,
                "form_category": ballot.form_category,
                "province": ballot.province,
                "constituency_number": ballot.constituency_number,
                "district": ballot.district,
                "polling_station_id": ballot.polling_station_id,
                "polling_unit": ballot.polling_unit,
                "vote_counts": ballot.vote_counts,
                "party_votes": ballot.party_votes,
                "candidate_info": ballot.candidate_info,
                "party_info": ballot.party_info,
                "valid_votes": ballot.valid_votes,
                "invalid_votes": ballot.invalid_votes,
                "blank_votes": ballot.blank_votes,
                "total_votes": ballot.total_votes,
                "confidence_score": ballot.confidence_score,
            }
            data.append(ballot_dict)

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info(f"Exported JSON to: {json_path}")
        return json_path

    except Exception as e:
        logger.exception(f"Error exporting JSON: {e}")
        return None


def export_csv(ballot_results: list[BallotData]) -> Optional[str]:
    """
    Export ballot results to CSV file.

    Args:
        ballot_results: List of BallotData objects from state

    Returns:
        Path to CSV file or None if no results
    """
    if not ballot_results:
        logger.warning("No ballot results available for CSV export")
        return None

    try:
        # Create temp file for CSV
        csv_path = tempfile.mktemp(suffix="_ballot_results.csv")

        with open(csv_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)

            # Write header
            writer.writerow([
                "Source File",
                "Form Type",
                "Form Category",
                "Province",
                "Constituency Number",
                "District",
                "Polling Station ID",
                "Valid Votes",
                "Invalid Votes",
                "Blank Votes",
                "Total Votes",
                "Confidence Score",
                "Vote Details"
            ])

            # Write data rows
            for ballot in ballot_results:
                # Format vote details as readable string
                if ballot.form_category == "party_list":
                    vote_details = "; ".join(
                        f"Party {p}: {v}" for p, v in sorted(ballot.party_votes.items())
                    )
                else:
                    vote_details = "; ".join(
                        f"Candidate {c}: {v}" for c, v in sorted(ballot.vote_counts.items())
                    )

                writer.writerow([
                    ballot.source_file,
                    ballot.form_type,
                    ballot.form_category,
                    ballot.province,
                    ballot.constituency_number,
                    ballot.district,
                    ballot.polling_station_id,
                    ballot.valid_votes,
                    ballot.invalid_votes,
                    ballot.blank_votes,
                    ballot.total_votes,
                    ballot.confidence_score,
                    vote_details
                ])

        logger.info(f"Exported CSV to: {csv_path}")
        return csv_path

    except Exception as e:
        logger.exception(f"Error exporting CSV: {e}")
        return None


def clear_results():
    """
    Clear all results and reset the interface.

    Returns:
        Tuple of empty values for all outputs
    """
    logger.info("Clearing results")
    return [], "", None, None, None, None, None, None, None


# Create Gradio interface with Thai text support
with gr.Blocks(title="Thai Election Ballot OCR") as demo:
    gr.Markdown("# Thai Election Ballot OCR / ระบบอ่านบัตรลงคะแนนเลือกตั้ง")
    gr.Markdown("""
Upload ballot images to extract vote counts.

**รองรับภาษาไทย** - Thai text is fully supported in filenames and results.

**Instructions / วิธีใช้:**
1. Upload ballot images / อัปโหลดรูปภาพบัตรเลือกตั้ง (supports PNG, JPG, JPEG)
2. Click "Process Ballots" to start OCR / คลิก "ประมวลผลบัตร" เพื่อเริ่มอ่านข้อมูล
3. View results in the table / ดูผลลัพธ์ในตารางด้านล่าง
4. Download reports as PDF, JSON, or CSV / ดาวน์โหลดรายงานเป็น PDF, JSON หรือ CSV
""")

    with gr.Row():
        file_input = gr.File(
            file_count="multiple",
            label="Upload Ballot Images / อัปโหลดรูปภาพบัตรลงคะแนน (100-500)",
            file_types=["image"]
        )

    with gr.Row():
        process_btn = gr.Button("Process Ballots / ประมวลผลบัตร", variant="primary", size="lg")
        clear_btn = gr.Button("Clear / ล้างข้อมูล", variant="secondary", size="lg")

    with gr.Row():
        results_table = gr.Dataframe(
            headers=["Image / รูปภาพ", "Province / จังหวัด", "Constituency / เขต", "Station / หน่วย", "Form Type / ประเภท", "Confidence / ความมั่นใจ", "Votes / คะแนนเสียง"],
            label="Extracted Results / ผลลัพธ์",
            wrap=True
        )

    with gr.Row():
        status_output = gr.Textbox(label="Status / สถานะ", lines=2, placeholder="Processing status will appear here...")

    with gr.Row():
        error_output = gr.Textbox(label="Errors / ข้อผิดพลาด", lines=5, placeholder="Any errors will be shown here...")

    # Download section - PDF reports
    gr.Markdown("### Download Reports / ดาวน์โหลดรายงาน")

    with gr.Row():
        batch_pdf_btn = gr.Button("Batch Summary PDF / สรุปผลการประมวลผล", variant="secondary")
        constituency_pdf_btn = gr.Button("Constituency Report PDF / รายงานเขตเลือกตั้ง", variant="secondary")
        exec_summary_btn = gr.Button("Executive Summary (1 page) / สรุปผู้บริหาร", variant="secondary")

    with gr.Row():
        batch_pdf_output = gr.File(label="Batch Summary PDF / สรุปผลการประมวลผล", visible=True)
        constituency_pdf_output = gr.File(label="Constituency Report PDF / รายงานเขตเลือกตั้ง", visible=True)
        exec_summary_output = gr.File(label="Executive Summary / สรุปผู้บริหาร", visible=True)

    # Export section - JSON and CSV
    gr.Markdown("### Export Data / ส่งออกข้อมูล")

    with gr.Row():
        json_btn = gr.Button("Export JSON / ส่งออก JSON", variant="secondary")
        csv_btn = gr.Button("Export CSV / ส่งออก CSV", variant="secondary")

    with gr.Row():
        json_output = gr.File(label="JSON Export / ส่งออก JSON", visible=True)
        csv_output = gr.File(label="CSV Export / ส่งออก CSV", visible=True)

    # Footer
    gr.Markdown("""
---
**Thai Election Ballot OCR** - v1.1

Powered by AI vision models for accurate ballot data extraction.
""")

    # State to store ballot results for PDF generation
    ballot_state = gr.State(value=None)

    # Wire up event handlers
    process_btn.click(
        fn=process_ballots,
        inputs=[file_input],
        outputs=[results_table, error_output, ballot_state]
    )

    batch_pdf_btn.click(
        fn=download_batch_pdf,
        inputs=[ballot_state],
        outputs=[batch_pdf_output]
    )

    constituency_pdf_btn.click(
        fn=download_constituency_pdf,
        inputs=[ballot_state],
        outputs=[constituency_pdf_output]
    )

    exec_summary_btn.click(
        fn=download_executive_summary_pdf,
        inputs=[ballot_state],
        outputs=[exec_summary_output]
    )

    json_btn.click(
        fn=export_json,
        inputs=[ballot_state],
        outputs=[json_output]
    )

    csv_btn.click(
        fn=export_csv,
        inputs=[ballot_state],
        outputs=[csv_output]
    )

    clear_btn.click(
        fn=clear_results,
        inputs=[],
        outputs=[results_table, error_output, ballot_state, batch_pdf_output, constituency_pdf_output, exec_summary_output, json_output, csv_output, file_input]
    )


if __name__ == "__main__":
    import os

    # Default to localhost for security. Set WEB_UI_HOST=0.0.0.0 to allow external access.
    server_name = os.environ.get("WEB_UI_HOST", "127.0.0.1")
    server_port = int(os.environ.get("WEB_UI_PORT", "7860"))

    if server_name == "0.0.0.0":
        logger.warning("Web UI binding to all network interfaces. This may expose the application.")
        logger.warning("Set WEB_UI_HOST=127.0.0.1 for local-only access.")

    logger.info(f"Starting web UI on http://{server_name}:{server_port}")
    demo.launch(server_name=server_name, server_port=server_port)
