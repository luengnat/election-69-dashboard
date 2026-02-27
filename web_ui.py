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
from typing import Optional, Any
import tempfile
import os
import logging
import json
import csv
import copy
import zipfile
import shutil
import re
from pathlib import Path
from dataclasses import asdict

from batch_processor import BatchProcessor, BatchResult
from ballot_types import BallotData
from ballot_ocr import (
    AggregatedResults,
    pdf_to_images
)
from config import config

# Configure logging
logging.basicConfig(level=getattr(logging, config.log_level, logging.INFO))
logger = logging.getLogger(__name__)

# Maximum number of results to display (to avoid UI overload)
MAX_DISPLAY_RESULTS = 100

# File upload validation settings (from config)
ALLOWED_EXTENSIONS = set(config.allowed_extensions)
ZIP_MAX_MEMBERS = config.max_batch_size * 5
ZIP_MAX_TOTAL_UNCOMPRESSED_BYTES = config.max_file_size * config.max_batch_size


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
        if size > config.max_file_size:
            return False, f"File too large: {size // (1024*1024)}MB (max {config.max_file_size // (1024*1024)}MB)"
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

    def on_progress(self, current: int, total: int, path: str, _result: Optional[BallotData]) -> None:
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


def _normalize_uploaded_paths(files: Any) -> list[str]:
    """
    Normalize Gradio upload payload into a list of filesystem paths.
    """
    if not files:
        return []
    if isinstance(files, (str, Path)):
        return [str(files)]
    normalized: list[str] = []
    for item in files:
        if isinstance(item, (str, Path)):
            normalized.append(str(item))
            continue
        name = getattr(item, "name", None)
        if isinstance(name, str) and name:
            normalized.append(name)
    return normalized


def extract_zip_archive(zip_path: str, extract_to: str) -> list[str]:
    """
    Extract images from a ZIP archive.
    
    Args:
        zip_path: Path to the ZIP file
        extract_to: Directory to extract files into
        
    Returns:
        List of paths to extracted image files
    """
    image_paths = []
    
    try:
        if not zipfile.is_zipfile(zip_path):
            logger.warning(f"Not a valid zip file: {zip_path}")
            return []
            
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            members = zip_ref.infolist()
            if len(members) > ZIP_MAX_MEMBERS:
                logger.warning(f"ZIP has too many entries: {len(members)} (max {ZIP_MAX_MEMBERS})")
                return []

            total_uncompressed = sum(max(0, m.file_size) for m in members)
            if total_uncompressed > ZIP_MAX_TOTAL_UNCOMPRESSED_BYTES:
                logger.warning(
                    f"ZIP too large when extracted: {total_uncompressed} bytes "
                    f"(max {ZIP_MAX_TOTAL_UNCOMPRESSED_BYTES})"
                )
                return []

            extract_root = os.path.abspath(extract_to)
            for member in members:
                # Skip directories and unsupported file types.
                if member.is_dir():
                    continue

                member_ext = os.path.splitext(member.filename)[1].lower()
                if member_ext not in {".png", ".jpg", ".jpeg", ".pdf"}:
                    continue

                # Defend against path traversal and absolute paths.
                member_path = os.path.abspath(os.path.join(extract_root, member.filename))
                if not member_path.startswith(extract_root + os.sep):
                    logger.warning(f"Skipping suspicious zip entry: {member.filename}")
                    continue

                os.makedirs(os.path.dirname(member_path), exist_ok=True)
                with zip_ref.open(member, "r") as src, open(member_path, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                image_paths.append(member_path)
                        
    except Exception as e:
        logger.error(f"Error extracting zip {zip_path}: {e}")
        
    return image_paths


def process_ballots(files, local_folder, force_reprocess, backend_name="Ensemble (Default)", progress=gr.Progress()) -> tuple[list[list], str, list]:
    """
    Process ballot images (uploaded or from local folder) and return results.

    Args:
        files: List of uploaded file paths from gr.File
        local_folder: String path to a local directory for recursive scanning
        force_reprocess: Boolean to disable cache and force reprocessing
        backend_name: Selected backend option from dropdown
        progress: Gradio progress tracker

    Returns:
        Tuple of (results_dataframe, error_messages, ballot_results)
    """
    # Mapping of UI labels to backend strings
    BACKEND_MAPPING = {
        "Ensemble (Default)": None,
        "OpenRouter (Gemma/Claude)": "openrouter",
        "Anthropic Claude": "anthropic",
        "Local (TrOCR + Paddle)": "trocr,paddle",
        "Local Fast (Tesseract)": "tesseract"
    }
    backend_spec = BACKEND_MAPPING.get(backend_name)
    
    logger.info(f"process_ballots: {len(files) if files else 0} files, folder: {local_folder}, backend: {backend_name}")

    all_paths = []
    if files:
        all_paths.extend(_normalize_uploaded_paths(files))
    
    if local_folder and os.path.isdir(local_folder):
        logger.info(f"Scanning local folder: {local_folder}")
        folder_files = []
        for root, _, filenames in os.walk(local_folder):
            for filename in filenames:
                if filename.lower().endswith((".png", ".jpg", ".jpeg", ".pdf")):
                    folder_files.append(os.path.join(root, filename))
        logger.info(f"Found {len(folder_files)} files in local folder")
        all_paths.extend(folder_files)

    # Handle empty input
    if not all_paths:
        logger.warning("No files or folder provided")
        return [], "Please upload files or provide a valid local folder path.", []

    files = all_paths

    # Log file info (including Thai filenames)
    for f in files[:5]:  # Log first 5 files
        filename = os.path.basename(f) if f else "unknown"
        logger.info(f"  File: {filename}")
    if len(files) > 5:
        logger.info(f"  ... and {len(files) - 5} more files")

    # --- NEW ZIP LOGIC ---
    temp_extract_dir = None
    processed_files = []
    
    try:
        # Check for ZIP and PDF files and handle them
        has_zip = any(f.lower().endswith(".zip") for f in files)
        has_pdf = any(f.lower().endswith(".pdf") for f in files)
        
        if has_zip or has_pdf:
            temp_extract_dir = tempfile.mkdtemp(prefix="ballot_process_")
            logger.info(f"Created temp processing dir: {temp_extract_dir}")
            
            for f in files:
                if f.lower().endswith(".zip"):
                    extracted_images = extract_zip_archive(f, temp_extract_dir)
                    processed_files.extend(extracted_images)
                    logger.info(f"Extracted {len(extracted_images)} files from ZIP: {os.path.basename(f)}")
                elif f.lower().endswith(".pdf"):
                    try:
                        extracted_images = pdf_to_images(f, temp_extract_dir)
                        processed_files.extend(extracted_images)
                        logger.info(f"Converted PDF to {len(extracted_images)} images: {os.path.basename(f)}")
                    except Exception as e:
                        logger.error(f"Error converting PDF {f}: {e}")
                        # Fallback to original if conversion fails (processor might have limited native support or show error later)
                        processed_files.append(f)
                else:
                    processed_files.append(f)
        else:
            processed_files = files

        # Validate batch size
        if len(processed_files) > config.max_batch_size:
            logger.warning(f"Batch too large: {len(processed_files)} files (max {config.max_batch_size})")
            return [], f"Too many files: {len(processed_files)}. Maximum is {config.max_batch_size}.", []

        # Validate all files before processing
        invalid_files = []
        valid_files_to_process = []
        
        for f in processed_files:
            is_valid, error_msg = validate_file(f)
            if not is_valid:
                filename = os.path.basename(f) if f else "unknown"
                invalid_files.append(f"{filename}: {error_msg}")
            else:
                valid_files_to_process.append(f)

        if invalid_files:
            error_list = "\n".join(invalid_files[:10])  # Show first 10 errors
            if len(invalid_files) > 10:
                error_list += f"\n... and {len(invalid_files) - 10} more invalid files"
            logger.warning(f"Found {len(invalid_files)} invalid files")
            return [], f"Invalid files:\n{error_list}", []
            
        if not valid_files_to_process:
             return [], "No valid image files found to process.", []

        # Create progress callback
        callback = GradioProgressCallback(progress)

        # Create batch processor with rate limiting
        # Phase 13: Pass use_cache based on checkbox
        processor = BatchProcessor(
            max_workers=5, 
            rate_limit=2.0, 
            use_cache=not force_reprocess,
            backend_spec=backend_spec
        )

        # Process the batch
        logger.info(f"Starting batch processing (Force Reprocess: {force_reprocess})...")
        result = processor.process_batch(valid_files_to_process, progress_callback=callback)
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
        return [], "File error: Could not find uploaded file. Please try again.", []
    except PermissionError as e:
        logger.error(f"Permission error: {e}")
        return [], "Permission error: Cannot read uploaded files.", []
    except ConnectionError as e:
        logger.error(f"Connection error: {e}")
        return [], "API connection error: Could not reach OCR service. Please check your internet connection.", []
    except Exception as e:
        logger.exception(f"Unexpected error during processing: {e}")
        # Return user-friendly error message
        error_msg = str(e)
        if len(error_msg) > 200:
            error_msg = error_msg[:200] + "..."
        return [], f"Processing error: {error_msg}", []
    finally:
        # Cleanup temp directory
        if temp_extract_dir and os.path.exists(temp_extract_dir):
            try:
                shutil.rmtree(temp_extract_dir)
                logger.info(f"Removed temp extraction dir: {temp_extract_dir}")
            except Exception as e:
                logger.warning(f"Failed to remove temp dir {temp_extract_dir}: {e}")


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
        fd, json_path = tempfile.mkstemp(suffix="_ballot_results.json")
        os.close(fd)

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
        fd, csv_path = tempfile.mkstemp(suffix="_ballot_results.csv")
        os.close(fd)

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


def get_review_candidates(ballot_results: list[BallotData]) -> gr.update:
    """
    Get list of ballots that need review (low/medium confidence).
    
    Args:
        ballot_results: List of BallotData objects
        
    Returns:
        Gradio update for dropdown choices
    """
    if not ballot_results:
        return gr.update(choices=[], value=None)
    
    candidates = []
    for b in ballot_results:
        # Criteria: Confidence < 0.9 (approx 90%)
        # Or missing critical metadata
        needs_review = (b.confidence_score < 0.9) or (not b.province) or (b.constituency_number == 0)
            
        if needs_review:
            filename = os.path.basename(b.source_file)
            confidence_str = f"{b.confidence_score:.0%}"
            candidates.append(f"{filename} ({confidence_str})")
            
    if not candidates:
        return gr.update(choices=[], value=None)
        
    # Sort by confidence ascending (lowest first)
    try:
        candidates.sort(key=lambda x: int(x.split("(")[1].split("%")[0]))
    except Exception:
        pass
        
    return gr.update(choices=candidates, value=candidates[0] if candidates else None)


def load_review_data(selected_item: str, ballot_results: list[BallotData]):
    """
    Load data for the selected ballot into the review form.
    
    Args:
        selected_item: String from dropdown (e.g. "file.png (85%)")
        ballot_results: List of BallotData objects
        
    Returns:
        Tuple of (image_path, province, constituency, vote_data, status_msg)
    """
    if not selected_item or not ballot_results:
        return None, "", "", [], "No ballot selected"
        
    # Extract filename from "filename.png (85%)"
    filename = selected_item.split(" (")[0]
    
    # Find ballot
    target_ballot = None
    for b in ballot_results:
        if os.path.basename(b.source_file) == filename:
            target_ballot = b
            break
            
    if not target_ballot:
        return None, "", "", [], "Ballot not found"
        
    # Prepare vote data for dataframe
    vote_data = []
    if target_ballot.form_category == "party_list":
        # Party-list form
        for k, v in target_ballot.party_votes.items():
            vote_data.append([str(k), v])
        # Sort by party number
        try:
            vote_data.sort(key=lambda x: int(x[0]))
        except:
            pass
    else:
        # Constituency form
        for k, v in target_ballot.vote_counts.items():
            vote_data.append([str(k), v])
        # Sort by candidate number
        try:
            vote_data.sort(key=lambda x: int(x[0]))
        except:
            pass
        
    # Prepare provenance gallery
    provenance = []
    if target_ballot.provenance_images:
        for label, path in target_ballot.provenance_images.items():
            if os.path.exists(path):
                provenance.append((path, label.replace("_", " ").title()))
        
    return (
        target_ballot.source_file,
        target_ballot.province,
        str(target_ballot.constituency_number),
        vote_data,
        provenance,
        f"Loaded {filename}"
    )


def save_review_data(
    selected_item: str,
    new_province: str,
    new_constituency: str,
    new_votes: pd.DataFrame if 'pd' in globals() else list, # Handle potential type hint issue
    ballot_results: list[BallotData]
):
    """
    Save updated data to the state.
    
    Args:
        selected_item: String from dropdown
        new_province: Updated province string
        new_constituency: Updated constituency string
        new_votes: Updated votes dataframe/list
        ballot_results: Current state list
        
    Returns:
        Tuple of (updated_ballot_results, updated_results_table, status_msg, updated_dropdown)
    """
    if not selected_item or not ballot_results:
        return ballot_results, [], "No ballot selected", gr.update()
        
    filename = selected_item.split(" (")[0]
    
    # Find index
    idx = -1
    for i, b in enumerate(ballot_results):
        if os.path.basename(b.source_file) == filename:
            idx = i
            break
            
    if idx == -1:
        return ballot_results, [], "Error: Ballot not found in state", gr.update()
        
    # Create copy to update
    ballot = copy.deepcopy(ballot_results[idx])
    
    # Update Metadata
    ballot.province = new_province.strip()
    try:
        ballot.constituency_number = int(new_constituency)
    except Exception:
        pass # Keep old if invalid
        
    # Update Votes
    # new_votes comes from Dataframe, likely pandas or list of lists
    updated_votes = {}
    
    # Convert input to list of lists if needed
    vote_list = new_votes.values.tolist() if hasattr(new_votes, 'values') else new_votes
    
    for row in vote_list:
        try:
            # Handle potential empty strings or formatting
            num_str = str(row[0])
            count_str = str(row[1])
            if not num_str or not count_str:
                continue
                
            num = int(float(num_str)) # Handle "1.0"
            count = int(float(count_str))
            updated_votes[num] = count
        except (ValueError, IndexError):
            continue
            
    if ballot.form_category == "party_list":
        # Party-list uses string keys for party numbers
        ballot.party_votes = {str(k): v for k, v in updated_votes.items()}
    else:
        # Constituency uses int keys
        ballot.vote_counts = updated_votes
        
    # Update totals
    ballot.total_votes = sum(updated_votes.values())
    ballot.valid_votes = ballot.total_votes # Simplified assumption for manual edit
    
    # Mark as manually verified (High confidence)
    ballot.confidence_score = 1.0
    
    # Update state
    ballot_results[idx] = ballot
    
    # Re-generate results table
    new_table, _ = format_results(ballot_results)
    
    # Re-generate dropdown choices (this item might leave the list if we filter by score)
    # But for now, let's keep it visible so user knows it's done.
    # Alternatively, get_review_candidates will refresh it automatically on next call.
    # We'll return the updated list for the dropdown to refresh.
    new_dropdown = get_review_candidates(ballot_results)
    
    return ballot_results, new_table, f"Saved changes for {filename}", new_dropdown


def save_template_correction(selected_item: str, points: list, ballot_results: list[BallotData]):
    """
    Save a user-defined region as a potential template for training.
    """
    if not selected_item or len(points) < 2:
        return "Please select two points (top-left and bottom-right) on the image first."
        
    filename = selected_item.split(" (")[0]
    target_ballot = next((b for b in ballot_results if os.path.basename(b.source_file) == filename), None)
    
    if not target_ballot:
        return "Ballot data not found."
        
    # Save the correction to a persistent file
    correction_dir = Path("corrections")
    correction_dir.mkdir(exist_ok=True)
    
    correction_data = {
        "source_file": filename,
        "form_type": target_ballot.form_type,
        "points": points,
        "timestamp": os.path.getmtime(target_ballot.source_file) if os.path.exists(target_ballot.source_file) else 0
    }
    
    safe_name = re.sub(r'[^\w\s-]', '_', filename)
    target_path = correction_dir / f"correction_{safe_name}.json"
    
    with open(target_path, "w", encoding="utf-8") as f:
        json.dump(correction_data, f, indent=2, ensure_ascii=False)
        
    return f"Saved region {points} as template candidate for {target_ballot.form_type}. (หลักฐานการเลือกตำแหน่งถูกบันทึกแล้ว)"


def clear_results():
    """
    Clear all results and reset the interface.

    Returns:
        Tuple of empty values for all outputs
    """
    logger.info("Clearing results")
    return [], "", None, None, None, None, None, None, None, ""


def build_demo() -> gr.Blocks:
    """Build and return the Gradio UI."""
    # Create Gradio interface with Thai text support
    with gr.Blocks(title="Thai Election Ballot OCR") as demo:
        gr.Markdown("# Thai Election Ballot OCR / ระบบอ่านบัตรลงคะแนนเลือกตั้ง")
        gr.Markdown("""
Upload ballot images to extract vote counts.

**รองรับภาษาไทย** - Thai text is fully supported in filenames and results.

**Instructions / วิธีใช้:**
1. Upload ballot images / อัปโหลดรูปภาพบัตรเลือกตั้ง (supports PNG, JPG, JPEG)
2. Click "Process Ballots" to start OCR / คลิก "ประมวลผลบัตร" เพื่อเริ่มอ่านข้อมูล
3. **NEW:** Use the "Review / ตรวจสอบ" tab to manually verify low-confidence results.
4. Download reports as PDF, JSON, or CSV / ดาวน์โหลดรายงานเป็น PDF, JSON หรือ CSV
""")

        # Global Controls
        with gr.Row():
            with gr.Column(scale=2):
                file_input = gr.File(
                    file_count="multiple",
                    label="Upload Ballot Images or ZIP / อัปโหลดรูปภาพหรือไฟล์ ZIP (100-500)",
                    file_types=[".png", ".jpg", ".jpeg", ".pdf", ".zip"]
                )
            with gr.Column(scale=2):
                local_folder_input = gr.Textbox(
                    label="Local Folder Path (Recursive) / เส้นทางโฟลเดอร์ในเครื่อง (ค้นหาทุกโฟลเดอร์ย่อย)",
                    placeholder="/Users/name/ballots",
                    info="Scans for .png, .jpg, .jpeg, .pdf recursively"
                )
            with gr.Column(scale=1):
                backend_selector = gr.Dropdown(
                    label="AI Model / โมเดล AI",
                    choices=[
                        "Ensemble (Default)",
                        "OpenRouter (Gemma/Claude)",
                        "Anthropic Claude",
                        "Local (TrOCR + Paddle)",
                        "Local Fast (Tesseract)"
                    ],
                    value="Ensemble (Default)",
                    info="Select AI backend strategy"
                )
                force_reprocess_chk = gr.Checkbox(label="Force Reprocess (Disable Cache)", value=False)

        with gr.Row():
            process_btn = gr.Button("Process Ballots / ประมวลผลบัตร", variant="primary", size="lg")
            clear_btn = gr.Button("Clear / ล้างข้อมูล", variant="secondary", size="lg")

        # Tabs for different views
        with gr.Tabs():
            # Tab 1: Main Results Table
            with gr.TabItem("Results / ผลลัพธ์"):
                with gr.Row():
                    results_table = gr.Dataframe(
                        headers=["Image / รูปภาพ", "Province / จังหวัด", "Constituency / เขต", "Station / หน่วย", "Form Type / ประเภท", "Confidence / ความมั่นใจ", "Votes / คะแนนเสียง"],
                        label="Extracted Results / ผลลัพธ์",
                        wrap=True,
                        interactive=False
                    )

                with gr.Row():
                    status_output = gr.Textbox(label="Status / สถานะ", lines=2, placeholder="Processing status will appear here...")

                with gr.Row():
                    error_output = gr.Textbox(label="Errors / ข้อผิดพลาด", lines=5, placeholder="Any errors will be shown here...")

            # Tab 2: Review Queue
            with gr.TabItem("Review / ตรวจสอบ"):
                gr.Markdown("### Review Low-Confidence Ballots / ตรวจสอบบัตรที่มีความมั่นใจต่ำ")
                
                with gr.Row():
                    with gr.Column(scale=1):
                        review_dropdown = gr.Dropdown(
                            label="Select Ballot to Review / เลือกบัตรเพื่อตรวจสอบ",
                            choices=[],
                            interactive=True
                        )
                        refresh_review_btn = gr.Button("Refresh Queue / รีเฟรชรายการ", variant="secondary")
                        
                    with gr.Column(scale=2):
                        review_status = gr.Textbox(label="Status / สถานะ", interactive=False)
                
                with gr.Row():
                    # Left Column: Image Viewer
                    with gr.Column(scale=1):
                        review_image = gr.Image(label="Ballot Image / รูปภาพบัตร", type="filepath", interactive=False)
                        review_provenance = gr.Gallery(
                            label="Visual Evidence (Crops) / หลักฐานภาพถ่าย",
                            show_label=True,
                            elem_id="provenance_gallery",
                            columns=1,
                            object_fit="contain",
                            height="auto"
                        )
                    
                    # Right Column: Editor Form
                    with gr.Column(scale=1):
                        with gr.Row():
                            review_province = gr.Textbox(label="Province / จังหวัด", interactive=True)
                            review_constituency = gr.Textbox(label="Constituency / เขต", interactive=True)
                        
                        # Editable Vote Table
                        review_votes = gr.Dataframe(
                            headers=["Number / เบอร์", "Votes / คะแนน"],
                            datatype=["str", "number"],
                            label="Vote Counts / คะแนนเสียง",
                            interactive=True,
                            column_count=(2, "fixed"),
                        )
                        
                        save_review_btn = gr.Button("Save Changes / บันทึกการแก้ไข", variant="primary")
                        
                        gr.Markdown("---")
                        gr.Markdown("#### Region Selection (Training) / กำหนดตำแหน่งข้อมูล (เพื่อการฝึกฝน)")
                        gr.Markdown("*Click two points on the image above (top-left, bottom-right) to define a data region.*")
                        save_template_btn = gr.Button("Save as New Template / บันทึกตำแหน่งเป็นแม่แบบใหม่", variant="secondary")

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
**Thai Election Ballot OCR** - v1.2

Powered by AI vision models for accurate ballot data extraction.
""")

        # State to store ballot results for PDF generation
        ballot_state = gr.State(value=[])
        selected_points = gr.State(value=[])

        # Event Handlers
        
        # Process Ballots -> Updates Results Table & Review Queue
        process_btn.click(
            fn=process_ballots,
            inputs=[file_input, local_folder_input, force_reprocess_chk, backend_selector],
            outputs=[results_table, error_output, ballot_state]
        ).then(
            fn=get_review_candidates,
            inputs=[ballot_state],
            outputs=[review_dropdown]
        )

        # Review Tab Events
        refresh_review_btn.click(
            fn=get_review_candidates,
            inputs=[ballot_state],
            outputs=[review_dropdown]
        )
        
        review_dropdown.change(
            fn=load_review_data,
            inputs=[review_dropdown, ballot_state],
            outputs=[review_image, review_province, review_constituency, review_votes, review_provenance, review_status]
        )
        
        save_review_btn.click(
            fn=save_review_data,
            inputs=[review_dropdown, review_province, review_constituency, review_votes, ballot_state],
            outputs=[ballot_state, results_table, review_status, review_dropdown]
        )

        # Region Selection Logic
        def on_image_select(evt: gr.SelectData, points: list):
            points.append(evt.index)
            if len(points) > 2:
                points = points[-2:]
            
            msg = f"Points selected: {points}. "
            if len(points) == 2:
                msg += "Region defined! Click 'Save as New Template' to proceed."
            else:
                msg += "Click one more point to define the bottom-right corner."
            return points, msg

        review_image.select(
            fn=on_image_select,
            inputs=[selected_points],
            outputs=[selected_points, review_status]
        )

        save_template_btn.click(
            fn=save_template_correction,
            inputs=[review_dropdown, selected_points, ballot_state],
            outputs=[review_status]
        )

        # Download Events
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

        # Clear Results -> Clears All Outputs including Review
        clear_btn.click(
            fn=clear_results,
            inputs=[],
            outputs=[
                results_table, error_output, ballot_state, 
                batch_pdf_output, constituency_pdf_output, exec_summary_output, 
                json_output, csv_output, file_input, status_output
            ]
        ).then(
            fn=lambda: (None, None, "", "", [], [], [], ""),  # Clear review fields
            inputs=[],
            outputs=[review_dropdown, review_image, review_province, review_constituency, review_votes, review_provenance, selected_points, review_status]
        )

    return demo


if __name__ == "__main__":
    # Use config module for server settings
    if config.web_ui_host == "0.0.0.0":
        logger.warning("Web UI binding to all network interfaces. This may expose the application.")
        logger.warning("Set WEB_UI_HOST=127.0.0.1 for local-only access.")

    logger.info(f"Starting web UI on http://{config.web_ui_host}:{config.web_ui_port}")
    if config.auth_credentials:
        logger.info("Authentication enabled.")
    
    demo = build_demo()
    demo.launch(
        server_name=config.web_ui_host, 
        server_port=config.web_ui_port,
        auth=config.auth_credentials
    )
