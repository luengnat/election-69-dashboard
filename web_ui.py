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

from batch_processor import BatchProcessor, BallotData

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Maximum number of results to display (to avoid UI overload)
MAX_DISPLAY_RESULTS = 100


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


# Create Gradio interface with Thai text support
with gr.Blocks(title="Thai Election Ballot OCR") as demo:
    gr.Markdown("# Thai Election Ballot OCR")
    gr.Markdown("""
Upload ballot images to extract vote counts.

**รองรับภาษาไทย** - Thai text is fully supported in filenames and results.

**Instructions:**
1. Upload ballot images (supports PNG, JPG, JPEG)
2. Click "Process Ballots" to start OCR
3. View results in the table below
4. Any errors will be shown in the Errors box
""")

    with gr.Row():
        file_input = gr.File(
            file_count="multiple",
            label="Upload Ballot Images / อัปโหลดรูปภาพบัตรลงคะแนน (100-500)",
            file_types=["image"]
        )

    with gr.Row():
        process_btn = gr.Button("Process Ballots / ประมวลผลบัตร", variant="primary")

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

    # State to store ballot results for PDF generation
    ballot_state = gr.State(value=None)

    process_btn.click(
        fn=process_ballots,
        inputs=[file_input],
        outputs=[results_table, error_output, ballot_state]
    )


if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860)
