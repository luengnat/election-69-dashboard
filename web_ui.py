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
