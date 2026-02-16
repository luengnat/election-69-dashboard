"""
Gradio Web UI for Thai Election Ballot OCR.

Provides a web interface with multi-file upload and real-time progress tracking
for batch processing ballot images.

Usage:
    python web_ui.py

Then open http://localhost:7860 in your browser.
"""

import gradio as gr
from typing import Optional
import tempfile
import os

from batch_processor import BatchProcessor, BallotData


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


def format_results(results: list[BallotData]) -> list[list]:
    """
    Format BallotData results for Gradio Dataframe display.

    Args:
        results: List of BallotData objects from batch processing

    Returns:
        List of rows for gr.Dataframe, sorted by filename
    """
    if not results:
        return []

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

        row = [
            filename,
            ballot.province or "-",
            str(ballot.constituency_number) if ballot.constituency_number > 0 else "-",
            ballot.polling_station_id or "-",
            ballot.form_type or "-",
            confidence
        ]
        rows.append(row)

    # Sort by filename for predictable display
    rows.sort(key=lambda x: x[0])
    return rows


def process_ballots(files, progress=gr.Progress()):
    """
    Process uploaded ballot images and return results.

    Args:
        files: List of uploaded file paths from gr.File
        progress: Gradio progress tracker

    Returns:
        Tuple of (results_dataframe, error_messages)
    """
    # Handle empty upload
    if not files:
        return [], "Please upload at least one ballot image."

    # Ensure files is a list
    if isinstance(files, str):
        files = [files]

    # Create progress callback
    callback = GradioProgressCallback(progress)

    # Create batch processor
    processor = BatchProcessor(max_workers=5, rate_limit=2.0)

    # Process the batch
    try:
        result = processor.process_batch(files, progress_callback=callback)

        # Format results for display
        results_df = format_results(result.results)

        # Format errors for display
        if result.errors:
            error_lines = []
            for i, err in enumerate(result.errors, 1):
                filename = os.path.basename(err.get("path", "unknown"))
                error_msg = err.get("error", "Unknown error")
                # Truncate long error messages
                if len(error_msg) > 200:
                    error_msg = error_msg[:200] + "..."
                error_lines.append(f"{i}. {filename}: {error_msg}")
            error_text = "\n".join(error_lines)
        else:
            error_text = ""

        return results_df, error_text

    except Exception as e:
        return [], f"Processing error: {str(e)}"


# Create Gradio interface
with gr.Blocks(title="Thai Election Ballot OCR") as demo:
    gr.Markdown("# Thai Election Ballot OCR")
    gr.Markdown("Upload ballot images to extract vote counts")

    with gr.Row():
        file_input = gr.File(
            file_count="multiple",
            label="Upload Ballot Images (100-500)",
            file_types=["image"]
        )

    with gr.Row():
        process_btn = gr.Button("Process Ballots", variant="primary")

    with gr.Row():
        results_table = gr.Dataframe(
            headers=["Image", "Province", "Constituency", "Station", "Form Type", "Confidence"],
            label="Extracted Results"
        )

    with gr.Row():
        error_output = gr.Textbox(label="Errors", lines=5)

    process_btn.click(
        fn=process_ballots,
        inputs=[file_input],
        outputs=[results_table, error_output]
    )


if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860)
