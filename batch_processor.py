"""
Batch Processor for Thai Election Ballot OCR.

Provides concurrent processing of ballot images using ThreadPoolExecutor,
with rate limiting to stay under OpenRouter API limits (2 req/sec default)
and automatic retry with exponential backoff for failed requests.

Usage:
    from batch_processor import BatchProcessor

    processor = BatchProcessor(max_workers=5, rate_limit=2.0)
    results, errors = processor.process_batch(image_paths)
"""

import json
import dataclasses
import os
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Any, Protocol, runtime_checkable

# Import the existing OCR function
from ballot_ocr import BallotData, extract_ballot_data_with_ai

# Import path metadata parser (Phase 7)
from metadata_parser import PathMetadataParser

# Import tenacity for retry logic
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type
)

import requests
import sys
import gc


# Memory cleanup interval - run gc.collect() every N ballots
MEMORY_CLEANUP_INTERVAL = 50


@runtime_checkable
class ProgressCallback(Protocol):
    """
    Protocol for progress callbacks during batch processing.

    Any class with these methods can be used as a progress callback,
    enabling integration with CLI, GUI, or web interfaces.

    Example:
        class MyCallback:
            def on_start(self, total: int) -> None:
                print(f"Starting batch of {total} images")

            def on_progress(self, current: int, total: int, path: str, result: Optional[BallotData]) -> None:
                print(f"[{current}/{total}] Processed: {path}")

            def on_error(self, current: int, total: int, path: str, error: str) -> None:
                print(f"[{current}/{total}] Error on {path}: {error}")

            def on_complete(self, results: list, errors: list) -> None:
                print(f"Done: {len(results)} succeeded, {len(errors)} failed")
    """

    def on_start(self, total: int) -> None:
        """Called when batch processing starts."""
        ...

    def on_progress(self, current: int, total: int, path: str, result: Optional["BallotData"]) -> None:
        """Called after each ballot is successfully processed."""
        ...

    def on_error(self, current: int, total: int, path: str, error: str) -> None:
        """Called when a ballot processing fails."""
        ...

    def on_complete(self, results: list, errors: list) -> None:
        """Called when batch processing completes."""
        ...


class ConsoleProgressCallback:
    """
    Console-based progress callback for terminal output.

    Displays progress as "[X/Y] Processing: filename.png" with in-place updates.
    Shows summary on completion.

    Args:
        verbose: If True, print additional details like retries and memory cleanups
    """

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self._start_time: Optional[float] = None
        self._errors_seen = 0

    def on_start(self, total: int) -> None:
        """Print start message and begin timing."""
        self._start_time = time.time()
        self._errors_seen = 0
        print(f"Starting batch processing of {total} images...")

    def on_progress(self, current: int, total: int, path: str, result: Optional["BallotData"]) -> None:
        """Print progress with in-place update (overwrites current line)."""
        # Get filename from path for cleaner display
        filename = path.split("/")[-1] if "/" in path else path

        # Calculate percentage
        percent = (current / total * 100) if total > 0 else 0

        # Use \r for in-place update (works in terminals)
        sys.stdout.write(f"\r[{current}/{total}] ({percent:.0f}%) Processing: {filename}")
        sys.stdout.flush()

        # Newline after last item
        if current == total:
            print()  # Newline after progress complete

    def on_error(self, current: int, total: int, path: str, error: str) -> None:
        """Print error message on new line."""
        self._errors_seen += 1
        filename = path.split("/")[-1] if "/" in path else path
        # Print on new line (don't overwrite progress)
        print(f"\n[{current}/{total}] Error on {filename}: {error}")

    def on_complete(self, results: list, errors: list) -> None:
        """Print completion summary with timing."""
        elapsed = time.time() - self._start_time if self._start_time else 0
        success_count = len(results)
        error_count = len(errors)

        print(f"\nBatch complete: {success_count} succeeded, {error_count} failed")
        if elapsed > 0:
            rate = success_count / elapsed if success_count > 0 else 0
            print(f"Duration: {elapsed:.1f}s ({rate:.2f} images/sec)")

        if self.verbose and error_count > 0:
            print("Errors:")
            for err in errors:
                print(f"  - {err.get('path', 'unknown')}: {err.get('error', 'unknown error')}")


class NullProgressCallback:
    """
    No-op progress callback for when progress tracking is not needed.

    Useful for testing, non-interactive use, or when progress is handled elsewhere.
    All methods do nothing.
    """

    def on_start(self, total: int) -> None:
        pass

    def on_progress(self, current: int, total: int, path: str, result: Optional["BallotData"]) -> None:
        pass

    def on_error(self, current: int, total: int, path: str, error: str) -> None:
        pass

    def on_complete(self, results: list, errors: list) -> None:
        pass


class RateLimiter:
    """
    Thread-safe rate limiter for API calls.

    Uses a lock and timestamp tracking to enforce requests-per-second limits.
    Suitable for use with ThreadPoolExecutor (not asyncio).

    Example:
        limiter = RateLimiter(requests_per_second=2.0)
        with limiter:
            # Make API call
            response = requests.get(url)
    """

    def __init__(self, requests_per_second: float = 2.0):
        """
        Initialize rate limiter.

        Args:
            requests_per_second: Maximum requests allowed per second (default 2.0 for OpenRouter)
        """
        self.requests_per_second = requests_per_second
        self.min_interval = 1.0 / requests_per_second  # Minimum seconds between requests
        self._lock = threading.Lock()
        self._last_request_time = 0.0

    def acquire(self) -> None:
        """
        Acquire permission to make a request, blocking if necessary.

        Thread-safe: multiple threads can call this concurrently.
        """
        with self._lock:
            current_time = time.time()
            elapsed = current_time - self._last_request_time

            if elapsed < self.min_interval:
                # Need to wait before allowing this request
                wait_time = self.min_interval - elapsed
                time.sleep(wait_time)

            # Update last request time
            self._last_request_time = time.time()

    def __enter__(self) -> "RateLimiter":
        """Context manager entry - acquire rate limit slot."""
        self.acquire()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit - nothing to clean up."""
        pass


@dataclass
class BatchResult:
    """
    Results from batch processing with timing and performance statistics.

    Attributes:
        results: List of successfully processed BallotData objects
        errors: List of error dicts with 'path' and 'error' keys
        total: Total number of images attempted
        processed: Number of images successfully processed
        start_time: Unix timestamp when processing started
        end_time: Unix timestamp when processing completed
        duration_seconds: Total processing duration in seconds
        requests_per_second: Actual achieved rate (processed / duration)
        memory_cleanups: Number of gc.collect() calls made
        retries: Total retry attempts (from tenacity statistics)
    """
    results: list[BallotData] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)
    total: int = 0
    processed: int = 0
    start_time: float = 0.0
    end_time: float = 0.0
    duration_seconds: float = 0.0
    requests_per_second: float = 0.0
    memory_cleanups: int = 0
    retries: int = 0

    def __str__(self) -> str:
        """Human-readable summary."""
        success_rate = (self.processed / self.total * 100) if self.total > 0 else 0
        return (
            f"BatchResult(processed={self.processed}/{self.total}, "
            f"success={success_rate:.1f}%, "
            f"duration={self.duration_seconds:.1f}s, "
            f"rate={self.requests_per_second:.2f}/s)"
        )


class BatchProcessor:
    """
    Process multiple ballot images concurrently using ThreadPoolExecutor.

    Features:
    - Thread pool for concurrent processing (I/O-bound API calls)
    - Rate limiting to stay under API limits
    - Automatic retry with exponential backoff for transient failures
    - Memory cleanup for large batches to prevent OOM
    - Progress callbacks for UI integration

    Example:
        processor = BatchProcessor(max_workers=5, rate_limit=2.0)
        result = processor.process_batch(["img1.png", "img2.png"])
        print(f"Processed {result.processed}/{result.total} images")
    """

    def __init__(
        self,
        max_workers: int = 5,
        rate_limit: float = 2.0,
        enable_memory_cleanup: bool = True,
        verbose: bool = False
    ):
        """
        Initialize batch processor.

        Args:
            max_workers: Maximum concurrent threads (default 5)
            rate_limit: Requests per second limit (default 2.0 for OpenRouter)
            enable_memory_cleanup: Run gc.collect() every 50 ballots (default True)
            verbose: Enable verbose logging for debugging (default False)
        """
        self.max_workers = max_workers
        self.rate_limit = rate_limit
        self.rate_limiter = RateLimiter(requests_per_second=rate_limit)
        self.metadata_parser = PathMetadataParser()  # Phase 7: Path-based metadata extraction
        self.enable_memory_cleanup = enable_memory_cleanup
        self.verbose = verbose

    def _load_checkpoint(self, checkpoint_file: str) -> dict[str, dict]:
        """
        Load a JSONL checkpoint file, returning {path -> entry} dict.

        Silently skips truncated or malformed lines (handles mid-crash writes).
        """
        result: dict[str, dict] = {}
        try:
            with open(checkpoint_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        path = entry.get("path", "")
                        if path:
                            result[path] = entry
                    except json.JSONDecodeError:
                        pass  # Silently ignore truncated last line
        except (IOError, OSError):
            pass
        return result

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((requests.HTTPError, ConnectionError)),
        reraise=True
    )
    def process_single(self, image_path: str) -> Optional[BallotData]:
        """
        Process a single ballot image with retry logic.

        Args:
            image_path: Path to the ballot image

        Returns:
            BallotData if successful, None if extraction failed

        Raises:
            requests.HTTPError: After 3 failed retries
            ConnectionError: After 3 failed retries
        """
        # Pre-extract metadata from file path (Phase 7)
        path_metadata = self.metadata_parser.parse_path(image_path)

        # Acquire rate limit slot before API call
        with self.rate_limiter:
            ballot_data = extract_ballot_data_with_ai(image_path)

        if ballot_data:
            # Pre-fill from path if OCR missed these fields (path is NOT authoritative)
            if not ballot_data.province and path_metadata.province:
                ballot_data.province = path_metadata.province
            if not ballot_data.constituency_number and path_metadata.constituency_number:
                ballot_data.constituency_number = path_metadata.constituency_number
            if not ballot_data.district and path_metadata.district:
                ballot_data.district = path_metadata.district
            if not ballot_data.polling_unit and path_metadata.polling_unit:
                ballot_data.polling_unit = path_metadata.polling_unit

            # Track metadata source for auditing (Phase 7)
            ballot_data.confidence_details["metadata_source"] = {
                "province": "path" if path_metadata.province and not ballot_data.province else "ocr",
                "constituency": "path" if path_metadata.constituency_number and not ballot_data.constituency_number else "ocr",
                "path_confidence": path_metadata.confidence,
            }

            # Log any mismatches between path and OCR for debugging
            if (path_metadata.province and ballot_data.province and
                path_metadata.province != ballot_data.province):
                ballot_data.confidence_details["province_mismatch"] = {
                    "path": path_metadata.province,
                    "ocr": ballot_data.province
                }

        return ballot_data

    def process_batch(
        self,
        image_paths: list[str],
        progress_callback: Optional[ProgressCallback] = None,
        checkpoint_file: Optional[str] = None,
        retry_errors: bool = False,
    ) -> BatchResult:
        """
        Process multiple ballot images concurrently.

        Args:
            image_paths: List of paths to ballot images
            progress_callback: Optional callback for progress updates (default: None)
            checkpoint_file: Optional path to a JSONL checkpoint file for resume support.
                If the file exists, already-processed paths are skipped and their results
                are loaded directly.  Each completed ballot is appended as a JSON line
                immediately after processing so a crash can be resumed.
            retry_errors: If True, re-process paths that previously errored.
                Only meaningful when checkpoint_file is provided.

        Returns:
            BatchResult with results, errors, total, and processed count
        """
        from ballot_types import BallotData as _BallotData

        # Use NullProgressCallback if no callback provided
        callback = progress_callback if progress_callback else NullProgressCallback()
        total = len(image_paths)

        # ── Load checkpoint ──────────────────────────────────────────────────
        checkpoint: dict[str, dict] = {}
        if checkpoint_file and os.path.isfile(checkpoint_file):
            checkpoint = self._load_checkpoint(checkpoint_file)

        paths_to_skip: set[str] = set()
        preloaded_results: list[_BallotData] = []
        preloaded_errors: list[dict] = []

        for path_str, entry in checkpoint.items():
            if entry.get("status") == "ok":
                try:
                    ballot = _BallotData.from_dict(entry["result"])
                    preloaded_results.append(ballot)
                except Exception:
                    pass  # Corrupted entry — reprocess
                else:
                    paths_to_skip.add(path_str)
            elif entry.get("status") == "error" and not retry_errors:
                preloaded_errors.append({"path": path_str, "error": entry.get("error", "previous error")})
                paths_to_skip.add(path_str)

        pending_paths = [p for p in image_paths if str(p) not in paths_to_skip]

        # ── Open checkpoint file for appending ──────────────────────────────
        checkpoint_fh = None
        checkpoint_lock = threading.Lock()
        if checkpoint_file:
            checkpoint_fh = open(checkpoint_file, "a", encoding="utf-8")

        # ── Initialise result pre-populated with checkpoint data ─────────────
        start_time = time.time()
        result = BatchResult(total=total, start_time=start_time)
        result.results.extend(preloaded_results)
        result.processed = len(preloaded_results)
        result.errors.extend(preloaded_errors)

        # Track metrics
        memory_cleanups = 0

        # Notify callback that batch is starting
        callback.on_start(total)

        try:
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                # Submit only pending (non-checkpointed) tasks
                future_to_path = {
                    executor.submit(self.process_single, path): path
                    for path in pending_paths
                }

                # Track current including already-skipped items
                current = len(paths_to_skip)

                for future in as_completed(future_to_path):
                    path = future_to_path[future]
                    current += 1  # 1-indexed for user display
                    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                    try:
                        ballot_data = future.result()
                        if ballot_data:
                            result.results.append(ballot_data)
                            result.processed += 1
                            callback.on_progress(current, total, str(path), ballot_data)
                            # Write success line to checkpoint
                            if checkpoint_fh:
                                entry = {
                                    "path": str(path),
                                    "status": "ok",
                                    "ts": ts,
                                    "result": dataclasses.asdict(ballot_data),
                                }
                                with checkpoint_lock:
                                    checkpoint_fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
                                    checkpoint_fh.flush()
                        else:
                            error_msg = "No data extracted from image"
                            error_info = {"path": str(path), "error": error_msg}
                            result.errors.append(error_info)
                            callback.on_error(current, total, str(path), error_msg)
                            if checkpoint_fh:
                                entry = {"path": str(path), "status": "error", "ts": ts, "error": error_msg}
                                with checkpoint_lock:
                                    checkpoint_fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
                                    checkpoint_fh.flush()
                    except Exception as e:
                        error_msg = str(e)
                        error_info = {"path": str(path), "error": error_msg}
                        result.errors.append(error_info)
                        callback.on_error(current, total, str(path), error_msg)
                        if checkpoint_fh:
                            entry = {"path": str(path), "status": "error", "ts": ts, "error": error_msg}
                            with checkpoint_lock:
                                checkpoint_fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
                                checkpoint_fh.flush()

                    # Memory cleanup every N ballots to prevent OOM
                    if self.enable_memory_cleanup and current % MEMORY_CLEANUP_INTERVAL == 0:
                        gc.collect()
                        memory_cleanups += 1
                        if self.verbose:
                            print(f"\n[Memory cleanup #{memory_cleanups}]")
        finally:
            if checkpoint_fh:
                checkpoint_fh.close()

        # Calculate final timing and metrics
        end_time = time.time()
        duration = end_time - start_time
        result.end_time = end_time
        result.duration_seconds = duration
        result.requests_per_second = result.processed / duration if duration > 0 else 0.0
        result.memory_cleanups = memory_cleanups

        # Notify callback that batch is complete
        callback.on_complete(result.results, result.errors)

        return result

    def process_batch_sequential(
        self,
        image_paths: list[str],
        progress_callback: Optional[ProgressCallback] = None,
        checkpoint_file: Optional[str] = None,
        retry_errors: bool = False,
    ) -> BatchResult:
        """
        Process ballot images sequentially (for comparison testing or low-rate APIs).

        Uses the same rate limiting and retry logic as parallel processing,
        but processes one image at a time.

        Args:
            image_paths: List of paths to ballot images
            progress_callback: Optional callback for progress updates (default: None)
            checkpoint_file: Optional JSONL checkpoint path for resume support.
            retry_errors: If True, re-process paths that previously errored.

        Returns:
            BatchResult with results, errors, total, and processed count
        """
        from ballot_types import BallotData as _BallotData

        callback = progress_callback if progress_callback else NullProgressCallback()
        total = len(image_paths)

        # ── Load checkpoint ──────────────────────────────────────────────────
        checkpoint: dict[str, dict] = {}
        if checkpoint_file and os.path.isfile(checkpoint_file):
            checkpoint = self._load_checkpoint(checkpoint_file)

        paths_to_skip: set[str] = set()
        preloaded_results: list[_BallotData] = []
        preloaded_errors: list[dict] = []

        for path_str, entry in checkpoint.items():
            if entry.get("status") == "ok":
                try:
                    ballot = _BallotData.from_dict(entry["result"])
                    preloaded_results.append(ballot)
                except Exception:
                    pass
                else:
                    paths_to_skip.add(path_str)
            elif entry.get("status") == "error" and not retry_errors:
                preloaded_errors.append({"path": path_str, "error": entry.get("error", "previous error")})
                paths_to_skip.add(path_str)

        # ── Open checkpoint for appending ────────────────────────────────────
        checkpoint_fh = None
        if checkpoint_file:
            checkpoint_fh = open(checkpoint_file, "a", encoding="utf-8")

        # ── Initialise result with checkpoint data ────────────────────────────
        start_time = time.time()
        result = BatchResult(total=total, start_time=start_time)
        result.results.extend(preloaded_results)
        result.processed = len(preloaded_results)
        result.errors.extend(preloaded_errors)

        memory_cleanups = 0
        callback.on_start(total)

        # Offset idx by already-skipped items so on_progress counts are consistent
        idx_offset = len(paths_to_skip)

        try:
            pending_paths = [(i, p) for i, p in enumerate(image_paths, start=1) if str(p) not in paths_to_skip]
            for seq, (orig_idx, path) in enumerate(pending_paths, start=1):
                idx = idx_offset + seq
                ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                try:
                    ballot_data = self.process_single(path)
                    if ballot_data:
                        result.results.append(ballot_data)
                        result.processed += 1
                        callback.on_progress(idx, total, str(path), ballot_data)
                        if checkpoint_fh:
                            entry = {
                                "path": str(path),
                                "status": "ok",
                                "ts": ts,
                                "result": dataclasses.asdict(ballot_data),
                            }
                            checkpoint_fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
                            checkpoint_fh.flush()
                    else:
                        error_msg = "No data extracted from image"
                        result.errors.append({"path": str(path), "error": error_msg})
                        callback.on_error(idx, total, str(path), error_msg)
                        if checkpoint_fh:
                            entry = {"path": str(path), "status": "error", "ts": ts, "error": error_msg}
                            checkpoint_fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
                            checkpoint_fh.flush()
                except Exception as e:
                    error_msg = str(e)
                    result.errors.append({"path": str(path), "error": error_msg})
                    callback.on_error(idx, total, str(path), error_msg)
                    if checkpoint_fh:
                        entry = {"path": str(path), "status": "error", "ts": ts, "error": error_msg}
                        checkpoint_fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
                        checkpoint_fh.flush()

                if self.enable_memory_cleanup and idx % MEMORY_CLEANUP_INTERVAL == 0:
                    gc.collect()
                    memory_cleanups += 1
                    if self.verbose:
                        print(f"\n[Memory cleanup #{memory_cleanups}]")
        finally:
            if checkpoint_fh:
                checkpoint_fh.close()

        end_time = time.time()
        duration = end_time - start_time
        result.end_time = end_time
        result.duration_seconds = duration
        result.requests_per_second = result.processed / duration if duration > 0 else 0.0
        result.memory_cleanups = memory_cleanups

        callback.on_complete(result.results, result.errors)
        return result


if __name__ == "__main__":
    # Simple test/demo
    print("BatchProcessor module loaded successfully")
    print(f"  RateLimiter: {RateLimiter}")
    print(f"  BatchProcessor: {BatchProcessor}")
    print(f"  BatchResult: {BatchResult}")
