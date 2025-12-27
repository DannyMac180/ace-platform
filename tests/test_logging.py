"""Tests for structured logging infrastructure.

These tests verify:
1. JSON formatter produces valid JSON
2. Sensitive data is redacted
3. Content truncation works correctly
4. Log levels are determined correctly by environment
5. Correlation ID integration works
"""

import json
import logging
from unittest.mock import patch

import pytest

from ace_platform.core.logging import (
    DEFAULT_TRUNCATE_LENGTH,
    DevelopmentFormatter,
    JSONFormatter,
    SensitiveDataFilter,
    get_log_level,
    sanitize_for_logging,
    sanitize_value,
    truncate_string,
)


class TestTruncateString:
    """Tests for string truncation utility."""

    def test_short_string_unchanged(self):
        """Test that short strings are not truncated."""
        result = truncate_string("hello", max_length=10)
        assert result == "hello"

    def test_exact_length_unchanged(self):
        """Test that strings at exact max length are unchanged."""
        result = truncate_string("hello", max_length=5)
        assert result == "hello"

    def test_long_string_truncated(self):
        """Test that long strings are truncated with ellipsis."""
        result = truncate_string("hello world", max_length=8)
        assert result == "hello..."
        assert len(result) == 8

    def test_very_short_max_length(self):
        """Test truncation with very short max length."""
        result = truncate_string("hello", max_length=4)
        assert result == "h..."

    def test_default_truncate_length(self):
        """Test truncation with default length."""
        long_string = "x" * 200
        result = truncate_string(long_string)
        assert len(result) == DEFAULT_TRUNCATE_LENGTH
        assert result.endswith("...")


class TestSanitizeValue:
    """Tests for value sanitization."""

    def test_sensitive_field_redacted(self):
        """Test that sensitive fields are redacted."""
        result = sanitize_value("password", "secret123")
        assert result == "[REDACTED: 9 chars]"

    def test_sensitive_field_case_insensitive(self):
        """Test that sensitive field detection is case-insensitive."""
        result = sanitize_value("API_KEY", "sk-123456")
        assert "[REDACTED" in result

    def test_content_field_redacted(self):
        """Test that content field is redacted (playbook content protection)."""
        result = sanitize_value("content", "# My Playbook\n- Step 1\n- Step 2")
        assert "[REDACTED" in result

    def test_playbook_content_redacted(self):
        """Test that playbook_content field is redacted."""
        result = sanitize_value("playbook_content", "long content here")
        assert "[REDACTED" in result

    def test_reasoning_trace_redacted(self):
        """Test that reasoning_trace field is redacted."""
        result = sanitize_value("reasoning_trace", "agent reasoning output")
        assert "[REDACTED" in result

    def test_non_sensitive_field_preserved(self):
        """Test that non-sensitive fields are preserved."""
        result = sanitize_value("user_id", "123-456")
        assert result == "123-456"

    def test_long_non_sensitive_truncated(self):
        """Test that long non-sensitive strings are truncated."""
        long_value = "x" * 200
        result = sanitize_value("description", long_value, truncate_length=50)
        assert len(result) == 50
        assert result.endswith("...")

    def test_sensitive_none_value(self):
        """Test that None sensitive values are handled."""
        result = sanitize_value("password", None)
        assert result is None

    def test_sensitive_empty_string(self):
        """Test that empty sensitive strings are handled."""
        result = sanitize_value("password", "")
        assert result == "[REDACTED]"

    def test_nested_dict_sanitized(self):
        """Test that nested dictionaries are recursively sanitized."""
        data = {"user": {"password": "secret", "name": "test"}}
        result = sanitize_value("data", data)  # Non-sensitive key wrapping sensitive data
        assert result["user"]["password"].startswith("[REDACTED")
        assert result["user"]["name"] == "test"

    def test_list_values_in_sensitive_field_redacted(self):
        """Test that list values in sensitive field are fully redacted."""
        data = ["secret1", "secret2"]
        result = sanitize_value("secrets", data)  # "secrets" contains "secret"
        # Entire list is redacted since the field is sensitive
        assert result == "[REDACTED]"

    def test_list_values_in_non_sensitive_field_preserved(self):
        """Test that list values in non-sensitive field are preserved."""
        data = ["item1", "item2"]
        result = sanitize_value("items", data)
        assert result == ["item1", "item2"]


class TestSanitizeForLogging:
    """Tests for dictionary sanitization."""

    def test_mixed_fields(self):
        """Test sanitization of mixed sensitive and non-sensitive fields."""
        data = {
            "user_id": "123",
            "email": "test@example.com",
            "password": "secret",
            "api_key": "sk-12345",
        }
        result = sanitize_for_logging(data)

        assert result["user_id"] == "123"
        assert result["email"] == "test@example.com"
        assert "[REDACTED" in result["password"]
        assert "[REDACTED" in result["api_key"]

    def test_playbook_data_sanitized(self):
        """Test that playbook-related data is properly sanitized."""
        data = {
            "playbook_id": "abc-123",
            "name": "My Playbook",
            "content": "# Full playbook content\n- Step 1\n- Step 2\n- Step 3",
            "initial_content": "# Initial content here",
        }
        result = sanitize_for_logging(data)

        assert result["playbook_id"] == "abc-123"
        assert result["name"] == "My Playbook"
        assert "[REDACTED" in result["content"]
        assert "[REDACTED" in result["initial_content"]

    def test_nested_structure(self):
        """Test sanitization of nested structures."""
        data = {
            "request": {
                "headers": {
                    "authorization": "Bearer token123",
                    "content-type": "application/json",
                },
                "body": {
                    "secret": "mysecret",
                },
            }
        }
        result = sanitize_for_logging(data)

        # Check nested sanitization
        assert result["request"]["body"]["secret"].startswith("[REDACTED")

    def test_non_dict_input(self):
        """Test that non-dict input is returned unchanged."""
        result = sanitize_for_logging("not a dict")
        assert result == "not a dict"

    def test_empty_dict(self):
        """Test sanitization of empty dictionary."""
        result = sanitize_for_logging({})
        assert result == {}


class TestJSONFormatter:
    """Tests for JSON log formatter."""

    @pytest.fixture
    def formatter(self):
        """Create a JSON formatter instance."""
        return JSONFormatter()

    @pytest.fixture
    def log_record(self):
        """Create a sample log record."""
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        record.correlation_id = "abc-123"
        return record

    def test_output_is_valid_json(self, formatter, log_record):
        """Test that formatter outputs valid JSON."""
        output = formatter.format(log_record)
        parsed = json.loads(output)
        assert isinstance(parsed, dict)

    def test_required_fields_present(self, formatter, log_record):
        """Test that required fields are in the output."""
        output = formatter.format(log_record)
        parsed = json.loads(output)

        assert "timestamp" in parsed
        assert "level" in parsed
        assert "logger" in parsed
        assert "message" in parsed
        assert "correlation_id" in parsed
        assert "location" in parsed

    def test_correlation_id_included(self, formatter, log_record):
        """Test that correlation ID is included."""
        output = formatter.format(log_record)
        parsed = json.loads(output)
        assert parsed["correlation_id"] == "abc-123"

    def test_message_formatted(self, formatter, log_record):
        """Test that message is properly formatted."""
        output = formatter.format(log_record)
        parsed = json.loads(output)
        assert parsed["message"] == "Test message"

    def test_level_included(self, formatter, log_record):
        """Test that log level is included."""
        output = formatter.format(log_record)
        parsed = json.loads(output)
        assert parsed["level"] == "INFO"

    def test_location_info(self, formatter, log_record):
        """Test that location info is included."""
        output = formatter.format(log_record)
        parsed = json.loads(output)
        assert parsed["location"]["file"] == "test.py"
        assert parsed["location"]["line"] == 42

    def test_extra_fields_sanitized(self, formatter, log_record):
        """Test that extra fields are sanitized."""
        log_record.content = "sensitive playbook content"
        log_record.user_id = "user-123"

        output = formatter.format(log_record)
        parsed = json.loads(output)

        extra = parsed.get("extra", {})
        if "content" in extra:
            assert "[REDACTED" in extra["content"]
        assert extra.get("user_id") == "user-123"


class TestDevelopmentFormatter:
    """Tests for development formatter."""

    @pytest.fixture
    def formatter(self):
        """Create a development formatter instance."""
        return DevelopmentFormatter()

    @pytest.fixture
    def log_record(self):
        """Create a sample log record."""
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        record.correlation_id = "abc-12345678"
        return record

    def test_output_is_string(self, formatter, log_record):
        """Test that formatter outputs a string."""
        output = formatter.format(log_record)
        assert isinstance(output, str)

    def test_message_included(self, formatter, log_record):
        """Test that message is in output."""
        output = formatter.format(log_record)
        assert "Test message" in output

    def test_level_included(self, formatter, log_record):
        """Test that log level is in output."""
        output = formatter.format(log_record)
        assert "INFO" in output

    def test_correlation_id_truncated(self, formatter, log_record):
        """Test that correlation ID is truncated to 8 chars."""
        output = formatter.format(log_record)
        # Should contain first 8 chars of correlation ID
        assert "[abc-1234" in output

    def test_no_correlation_id_when_disabled(self, log_record):
        """Test formatter without correlation ID."""
        formatter = DevelopmentFormatter(include_correlation_id=False)
        log_record.correlation_id = "-"
        output = formatter.format(log_record)
        # Should not have brackets for correlation ID
        assert "[-]" not in output


class TestSensitiveDataFilter:
    """Tests for sensitive data filter."""

    @pytest.fixture
    def filter_instance(self):
        """Create a filter instance."""
        return SensitiveDataFilter()

    @pytest.fixture
    def log_record(self):
        """Create a sample log record with sensitive data."""
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        record.content = "sensitive content"
        record.user_id = "user-123"
        return record

    def test_filter_returns_true(self, filter_instance, log_record):
        """Test that filter always allows records through."""
        result = filter_instance.filter(log_record)
        assert result is True

    def test_sensitive_fields_redacted(self, filter_instance, log_record):
        """Test that sensitive fields are redacted in place."""
        filter_instance.filter(log_record)
        assert "[REDACTED" in log_record.content
        assert log_record.user_id == "user-123"


class TestGetLogLevel:
    """Tests for log level determination."""

    def test_debug_mode_returns_debug(self):
        """Test that debug mode always returns DEBUG level."""
        assert get_log_level("production", debug=True) == logging.DEBUG
        assert get_log_level("development", debug=True) == logging.DEBUG

    def test_development_level(self):
        """Test development environment log level."""
        assert get_log_level("development", debug=False) == logging.DEBUG

    def test_staging_level(self):
        """Test staging environment log level."""
        assert get_log_level("staging", debug=False) == logging.INFO

    def test_production_level(self):
        """Test production environment log level."""
        assert get_log_level("production", debug=False) == logging.WARNING

    def test_unknown_environment_defaults_to_info(self):
        """Test that unknown environment defaults to INFO."""
        assert get_log_level("unknown", debug=False) == logging.INFO


class TestSetupLogging:
    """Tests for logging setup function."""

    def test_setup_logging_does_not_raise(self):
        """Test that setup_logging completes without error."""
        from ace_platform.core.logging import setup_logging

        # Should not raise
        with patch("ace_platform.core.logging.get_settings") as mock_settings:
            mock_settings.return_value.environment = "development"
            mock_settings.return_value.debug = False
            mock_settings.return_value.is_production = False
            setup_logging(level=logging.DEBUG, json_format=False)

    def test_get_logger_returns_logger(self):
        """Test that get_logger returns a logger instance."""
        from ace_platform.core.logging import get_logger

        logger = get_logger("test.module")
        assert isinstance(logger, logging.Logger)
        assert logger.name == "test.module"
