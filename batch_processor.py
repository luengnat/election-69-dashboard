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

import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Optional, Any

# Import the existing OCR function
from ballot_ocr import BallotData, extract_ballot_data_with_ai

# Import tenacity for retry logic
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type
)

import requests


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
    Results from batch processing.

    Attributes:
        results: List of successfully processed BallotData objects
        errors: List of error dicts with 'path' and 'error' keys
        total: Total number of images attempted
        processed: Number of images successfully processed
    """
    results: list[BallotData] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)
    total: int = 0
    processed: int = 0


class BatchProcessor:
    """
    Process multiple ballot images concurrently using ThreadPoolExecutor.

    Features:
    - Thread pool for concurrent processing (I/O-bound API calls)
    - Rate limiting to stay under API limits
    - Automatic retry with exponential backoff for transient failures

    Example:
        processor = BatchProcessor(max_workers=5, rate_limit=2.0)
        result = processor.process_batch(["img1.png", "img2.png"])
        print(f"Processed {result.processed}/{result.total} images")
    """

    def __init__(self, max_workers: int = 5, rate_limit: float = 2.0):
        """
        Initialize batch processor.

        Args:
            max_workers: Maximum concurrent threads (default 5)
            rate_limit: Requests per second limit (default 2.0 for OpenRouter)
        """
        self.max_workers = max_workers
        self.rate_limit = rate_limit
        self.rate_limiter = RateLimiter(requests_per_second=rate_limit)

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
        # Acquire rate limit slot before API call
        with self.rate_limiter:
            return extract_ballot_data_with_ai(image_path)

    def process_batch(self, image_paths: list[str]) -> BatchResult:
        """
        Process multiple ballot images concurrently.

        Args:
            image_paths: List of paths to ballot images

        Returns:
            BatchResult with results, errors, total, and processed count
        """
        result = BatchResult(total=len(image_paths))

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all tasks
            future_to_path = {
                executor.submit(self.process_single, path): path
                for path in image_paths
            }

            # Collect results as they complete
            for future in as_completed(future_to_path):
                path = future_to_path[future]
                try:
                    ballot_data = future.result()
                    if ballot_data:
                        result.results.append(ballot_data)
                        result.processed += 1
                    else:
                        # Extraction returned None (no data extracted)
                        result.errors.append({
                            "path": str(path),
                            "error": "No data extracted from image"
                        })
                except Exception as e:
                    result.errors.append({
                        "path": str(path),
                        "error": str(e)
                    })

        return result

    def process_batch_sequential(self, image_paths: list[str]) -> BatchResult:
        """
        Process ballot images sequentially (for comparison testing).

        Uses the same rate limiting and retry logic as parallel processing,
        but processes one image at a time.

        Args:
            image_paths: List of paths to ballot images

        Returns:
            BatchResult with results, errors, total, and processed count
        """
        result = BatchResult(total=len(image_paths))

        for path in image_paths:
            try:
                ballot_data = self.process_single(path)
                if ballot_data:
                    result.results.append(ballot_data)
                    result.processed += 1
                else:
                    result.errors.append({
                        "path": str(path),
                        "error": "No data extracted from image"
                    })
            except Exception as e:
                result.errors.append({
                    "path": str(path),
                    "error": str(e)
                })

        return result


if __name__ == "__main__":
    # Simple test/demo
    print("BatchProcessor module loaded successfully")
    print(f"  RateLimiter: {RateLimiter}")
    print(f"  BatchProcessor: {BatchProcessor}")
    print(f"  BatchResult: {BatchResult}")
