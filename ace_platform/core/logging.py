"""Structured logging infrastructure for ACE Platform.

This module provides:
- JSON log format for production environments
- Text format with colors for development
- Request correlation ID integration
- Content sanitization to avoid logging sensitive data (playbook content)
- Configurable log levels per environment
- Log truncation utilities

Usage:
    from ace_platform.core.logging import setup_logging, get_logger, sanitize_for_logging

    # At application startup
    setup_logging()

    # In your modules
    logger = get_logger(__name__)
    logger.info("Processing request", extra={"user_id": user_id})

    # Sanitize data before logging
    safe_data = sanitize_for_logging({"content": playbook_content})
"""

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

from ace_platform.config import get_settings

# Fields that should never be logged in full
SENSITIVE_FIELDS = frozenset(
    {
        "content",
        "playbook_content",
        "initial_content",
        "reasoning_trace",
        "hashed_password",
        "password",
        "secret",
        "api_key",
        "access_token",
        "refresh_token",
        "key",
        "token",
    }
)

# Maximum length for truncated content in logs
DEFAULT_TRUNCATE_LENGTH = 100


def truncate_string(value: str, max_length: int = DEFAULT_TRUNCATE_LENGTH) -> str:
    """Truncate a string for logging, preserving useful context.

    Args:
        value: The string to truncate.
        max_length: Maximum length of the output string.

    Returns:
        Truncated string with ellipsis if truncated, or original if short enough.

    Example:
        >>> truncate_string("Hello World", max_length=8)
        'Hello...'
    """
    if len(value) <= max_length:
        return value
    # Leave room for ellipsis
    return value[: max_length - 3] + "..."


def sanitize_value(key: str, value: Any, truncate_length: int = DEFAULT_TRUNCATE_LENGTH) -> Any:
    """Sanitize a single value for safe logging.

    Args:
        key: The field name (used to determine if it's sensitive).
        value: The value to sanitize.
        truncate_length: Maximum length for string values.

    Returns:
        Sanitized value safe for logging.
    """
    # Check if this is a sensitive field
    key_lower = key.lower()
    is_sensitive = any(sensitive in key_lower for sensitive in SENSITIVE_FIELDS)

    if is_sensitive:
        if isinstance(value, str):
            length = len(value)
            if length > 0:
                return f"[REDACTED: {length} chars]"
            return "[REDACTED]"
        elif value is not None:
            return "[REDACTED]"
        return None

    # Truncate long strings
    if isinstance(value, str) and len(value) > truncate_length:
        return truncate_string(value, truncate_length)

    # Recursively sanitize dicts and lists
    if isinstance(value, dict):
        return sanitize_for_logging(value, truncate_length)
    if isinstance(value, list):
        return [sanitize_value(key, item, truncate_length) for item in value]

    return value


def sanitize_for_logging(
    data: dict[str, Any],
    truncate_length: int = DEFAULT_TRUNCATE_LENGTH,
) -> dict[str, Any]:
    """Sanitize a dictionary for safe logging.

    Removes or redacts sensitive fields and truncates long string values.
    This prevents playbook content and other sensitive data from appearing in logs.

    Args:
        data: Dictionary to sanitize.
        truncate_length: Maximum length for string values.

    Returns:
        New dictionary with sensitive data removed/redacted.

    Example:
        >>> sanitize_for_logging({"name": "test", "content": "long playbook..."})
        {'name': 'test', 'content': '[REDACTED: 16 chars]'}
    """
    if not isinstance(data, dict):
        return data

    return {key: sanitize_value(key, value, truncate_length) for key, value in data.items()}


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging in production.

    Outputs logs as single-line JSON objects with consistent field ordering.
    Includes correlation ID, timestamp, and any extra fields passed to the logger.
    """

    def __init__(self, include_extra: bool = True):
        """Initialize the JSON formatter.

        Args:
            include_extra: Whether to include extra fields from log records.
        """
        super().__init__()
        self.include_extra = include_extra
        # Standard fields that are part of LogRecord, not extra data
        self._standard_fields = {
            "name",
            "msg",
            "args",
            "created",
            "filename",
            "funcName",
            "levelname",
            "levelno",
            "lineno",
            "module",
            "msecs",
            "pathname",
            "process",
            "processName",
            "relativeCreated",
            "stack_info",
            "exc_info",
            "exc_text",
            "thread",
            "threadName",
            "taskName",
            "message",
            "correlation_id",
        }

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record as JSON.

        Args:
            record: The log record to format.

        Returns:
            JSON string representation of the log record.
        """
        # Ensure the message is formatted
        message = record.getMessage()

        # Build the log entry
        log_entry: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": message,
            "correlation_id": getattr(record, "correlation_id", None),
        }

        # Add location info
        log_entry["location"] = {
            "file": record.filename,
            "line": record.lineno,
            "function": record.funcName,
        }

        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        # Add extra fields (sanitized)
        if self.include_extra:
            extra = {}
            for key, value in record.__dict__.items():
                if key not in self._standard_fields and not key.startswith("_"):
                    extra[key] = value
            if extra:
                log_entry["extra"] = sanitize_for_logging(extra)

        return json.dumps(log_entry, default=str, ensure_ascii=False)


class DevelopmentFormatter(logging.Formatter):
    """Colored text formatter for development environments.

    Provides readable, colorized output for local development.
    """

    # ANSI color codes
    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"

    def __init__(self, include_correlation_id: bool = True):
        """Initialize the development formatter.

        Args:
            include_correlation_id: Whether to include correlation ID in output.
        """
        super().__init__()
        self.include_correlation_id = include_correlation_id

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record with colors.

        Args:
            record: The log record to format.

        Returns:
            Colored string representation of the log record.
        """
        color = self.COLORS.get(record.levelname, "")
        correlation_id = getattr(record, "correlation_id", "-")

        # Format timestamp
        timestamp = datetime.fromtimestamp(record.created).strftime("%H:%M:%S.%f")[:-3]

        # Build the formatted message
        parts = [
            f"{timestamp}",
            f"{color}{record.levelname:8}{self.RESET}",
        ]

        if self.include_correlation_id and correlation_id != "-":
            parts.append(f"[{correlation_id[:8]}]")

        parts.extend(
            [
                f"{record.name}:{record.lineno}",
                "-",
                record.getMessage(),
            ]
        )

        output = " ".join(parts)

        # Add exception info if present
        if record.exc_info:
            output += "\n" + self.formatException(record.exc_info)

        return output


class SensitiveDataFilter(logging.Filter):
    """Logging filter that sanitizes sensitive data in log records.

    This filter modifies the 'extra' data in log records to remove
    or redact sensitive fields like playbook content.
    """

    def __init__(self, truncate_length: int = DEFAULT_TRUNCATE_LENGTH):
        """Initialize the filter.

        Args:
            truncate_length: Maximum length for truncated values.
        """
        super().__init__()
        self.truncate_length = truncate_length

    def filter(self, record: logging.LogRecord) -> bool:
        """Filter and sanitize the log record.

        Args:
            record: The log record to process.

        Returns:
            Always returns True (doesn't filter out records, just sanitizes them).
        """
        # Sanitize any extra fields in the record
        for key in list(record.__dict__.keys()):
            if key.startswith("_") or key in {
                "name",
                "msg",
                "args",
                "created",
                "filename",
                "funcName",
                "levelname",
                "levelno",
                "lineno",
                "module",
                "msecs",
                "pathname",
                "process",
                "processName",
                "relativeCreated",
                "stack_info",
                "exc_info",
                "exc_text",
                "thread",
                "threadName",
                "taskName",
                "message",
                "correlation_id",
            }:
                continue

            value = getattr(record, key)
            sanitized = sanitize_value(key, value, self.truncate_length)
            setattr(record, key, sanitized)

        return True


def get_log_level(environment: str, debug: bool) -> int:
    """Determine the appropriate log level for the environment.

    Args:
        environment: The environment name (development, staging, production).
        debug: Whether debug mode is enabled.

    Returns:
        The logging level to use.
    """
    if debug:
        return logging.DEBUG

    levels = {
        "development": logging.DEBUG,
        "staging": logging.INFO,
        "production": logging.WARNING,
    }

    return levels.get(environment, logging.INFO)


def setup_logging(
    level: int | None = None,
    json_format: bool | None = None,
    include_correlation_id: bool = True,
) -> None:
    """Configure structured logging for the application.

    This function sets up logging with:
    - JSON format for production, colored text for development
    - Correlation ID integration
    - Sensitive data filtering
    - Appropriate log levels per environment

    Args:
        level: Override the log level. If None, determined by environment.
        json_format: Force JSON format. If None, determined by environment.
        include_correlation_id: Whether to include correlation IDs in logs.

    Example:
        # Auto-configure based on environment
        setup_logging()

        # Force JSON format with DEBUG level
        setup_logging(level=logging.DEBUG, json_format=True)
    """
    settings = get_settings()

    # Determine log level
    if level is None:
        level = get_log_level(settings.environment, settings.debug)

    # Determine format (JSON for production, text for development)
    if json_format is None:
        json_format = settings.is_production

    # Import here to avoid circular imports
    from ace_platform.api.middleware import CorrelationIdFilter

    # Create handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)

    # Add filters
    handler.addFilter(CorrelationIdFilter())
    handler.addFilter(SensitiveDataFilter())

    # Set formatter based on environment
    if json_format:
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(DevelopmentFormatter(include_correlation_id=include_correlation_id))

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove existing handlers to avoid duplicates
    root_logger.handlers.clear()
    root_logger.addHandler(handler)

    # Configure specific loggers for quieter output
    # Reduce noise from third-party libraries in non-debug mode
    if level > logging.DEBUG:
        logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
        logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the given name.

    This is a convenience function that returns a standard logger
    configured to work with the structured logging setup.

    Args:
        name: The logger name (typically __name__).

    Returns:
        A configured logger instance.

    Example:
        logger = get_logger(__name__)
        logger.info("Processing request", extra={"user_id": "123"})
    """
    return logging.getLogger(name)
