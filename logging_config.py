"""
Centralized logging configuration for Thai Election Ballot OCR.

Usage:
    from logging_config import setup_logging, get_logger

    # Setup logging at application start
    setup_logging(level="INFO")

    # Get a logger in any module
    logger = get_logger(__name__)
    logger.info("Processing ballot...")
"""

import logging
import sys
import os
from datetime import datetime


# Log format with timestamp, level, module, and message
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(level: str = None, log_file: str = None) -> None:
    """
    Configure logging for the application.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR). Defaults to env var LOG_LEVEL or INFO.
        log_file: Optional path to log file. If provided, logs will also be written to file.
    """
    # Determine log level
    if level is None:
        level = os.environ.get("LOG_LEVEL", "INFO")

    level = getattr(logging, level.upper(), logging.INFO)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove existing handlers
    root_logger.handlers = []

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    root_logger.addHandler(console_handler)

    # File handler (optional)
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(level)
        file_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
        root_logger.addHandler(file_handler)

    # Reduce noise from third-party libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("gradio").setLevel(logging.WARNING)
    logging.getLogger("httpomo").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger with the given name.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)


class LogContext:
    """
    Context manager for timing operations.

    Usage:
        with LogContext(logger, "Processing batch"):
            # ... code to time ...
    """

    def __init__(self, logger: logging.Logger, operation: str):
        self.logger = logger
        self.operation = operation
        self.start_time = None

    def __enter__(self):
        self.start_time = datetime.now()
        self.logger.debug(f"Starting: {self.operation}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        elapsed = (datetime.now() - self.start_time).total_seconds()
        if exc_type is None:
            self.logger.debug(f"Completed: {self.operation} ({elapsed:.2f}s)")
        else:
            self.logger.error(f"Failed: {self.operation} ({elapsed:.2f}s) - {exc_val}")
        return False  # Don't suppress exceptions


def log_function_call(func):
    """
    Decorator to log function entry and exit.

    Usage:
        @log_function_call
        def process_ballot(path):
            ...
    """
    def wrapper(*args, **kwargs):
        logger = get_logger(func.__module__)
        func_name = func.__name__
        logger.debug(f"Calling: {func_name}()")
        try:
            result = func(*args, **kwargs)
            logger.debug(f"Returned: {func_name}()")
            return result
        except Exception as e:
            logger.error(f"Error in {func_name}(): {e}")
            raise
    return wrapper


# Initialize logging on import if not already configured
if not logging.getLogger().handlers:
    setup_logging()
