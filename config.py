"""
Configuration module for Thai Election Ballot OCR.

Centralizes all settings and environment variables for easy configuration.

Usage:
    from config import config

    print(config.openrouter_api_key)
    print(config.max_workers)
"""

import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Config:
    """
    Application configuration loaded from environment variables.

    All settings can be overridden via environment variables.
    """

    # API Keys
    openrouter_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None

    # Web UI Settings
    web_ui_host: str = "127.0.0.1"
    web_ui_port: int = 7860

    # Processing Settings
    max_workers: int = 5
    rate_limit: float = 2.0  # requests per second
    api_timeout: int = 60  # seconds

    # File Upload Settings
    max_file_size: int = 10 * 1024 * 1024  # 10MB
    max_batch_size: int = 500
    allowed_extensions: list = field(default_factory=lambda: ['.png', '.jpg', '.jpeg', '.pdf'])

    # Logging Settings
    log_level: str = "INFO"

    # Report Settings
    report_dir: str = "reports"

    def __post_init__(self):
        """Load configuration from environment variables."""
        # API Keys
        self.openrouter_api_key = os.environ.get("OPENROUTER_API_KEY")
        self.anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY")

        # Web UI
        self.web_ui_host = os.environ.get("WEB_UI_HOST", "127.0.0.1")
        self.web_ui_port = int(os.environ.get("WEB_UI_PORT", "7860"))

        # Processing
        self.max_workers = int(os.environ.get("MAX_WORKERS", "5"))
        self.rate_limit = float(os.environ.get("RATE_LIMIT", "2.0"))
        self.api_timeout = int(os.environ.get("API_TIMEOUT", "60"))

        # Logging
        self.log_level = os.environ.get("LOG_LEVEL", "INFO")

        # Reports
        self.report_dir = os.environ.get("REPORT_DIR", "reports")

    @property
    def has_openrouter(self) -> bool:
        """Check if OpenRouter API key is configured."""
        return bool(self.openrouter_api_key)

    @property
    def has_anthropic(self) -> bool:
        """Check if Anthropic API key is configured."""
        return bool(self.anthropic_api_key)

    @property
    def has_any_api_key(self) -> bool:
        """Check if any API key is configured."""
        return self.has_openrouter or self.has_anthropic

    def validate(self) -> list[str]:
        """
        Validate configuration and return list of issues.

        Returns:
            List of configuration issues (empty if valid)
        """
        issues = []

        if not self.has_any_api_key:
            issues.append("No API key configured. Set OPENROUTER_API_KEY or ANTHROPIC_API_KEY.")

        if self.max_workers < 1:
            issues.append(f"MAX_WORKERS must be at least 1, got {self.max_workers}")

        if self.rate_limit <= 0:
            issues.append(f"RATE_LIMIT must be positive, got {self.rate_limit}")

        if self.api_timeout < 10:
            issues.append(f"API_TIMEOUT should be at least 10 seconds, got {self.api_timeout}")

        return issues

    def to_dict(self) -> dict:
        """Convert configuration to dictionary (safe for logging)."""
        return {
            "web_ui_host": self.web_ui_host,
            "web_ui_port": self.web_ui_port,
            "max_workers": self.max_workers,
            "rate_limit": self.rate_limit,
            "api_timeout": self.api_timeout,
            "max_file_size": self.max_file_size,
            "max_batch_size": self.max_batch_size,
            "log_level": self.log_level,
            "report_dir": self.report_dir,
            "has_openrouter": self.has_openrouter,
            "has_anthropic": self.has_anthropic,
            # Note: API keys are NOT included for security
        }


# Global configuration instance
config = Config()


def get_config() -> Config:
    """Get the global configuration instance."""
    return config


def reload_config() -> Config:
    """Reload configuration from environment variables."""
    global config
    config = Config()
    return config
