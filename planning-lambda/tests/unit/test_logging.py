# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for shared/logging.py."""

import json
import logging
import pytest
from io import StringIO

from shared.logging import get_logger, JsonFormatter, LambdaLogger
from shared.tracing import init_tracer, create_span


class TestGetLogger:
    """Tests for get_logger function."""

    def test_get_logger_returns_logger(self):
        """Returns configured logger with correct name."""
        logger = get_logger("test-logger")
        assert logger.name == "test-logger"
        assert isinstance(logger, logging.Logger)

    def test_get_logger_default_name(self, env_vars):
        """Uses default name from env var."""
        logger = get_logger()
        assert logger.name == "test-planning-lambda"

    def test_get_logger_has_handler(self):
        """Logger has StreamHandler attached."""
        logger = get_logger("test-handler-logger")
        assert len(logger.handlers) > 0
        assert any(isinstance(h, logging.StreamHandler) for h in logger.handlers)

    def test_get_logger_idempotent(self):
        """Getting same logger twice doesn't add duplicate handlers."""
        logger1 = get_logger("test-idempotent-logger")
        handler_count = len(logger1.handlers)

        logger2 = get_logger("test-idempotent-logger")
        assert len(logger2.handlers) == handler_count


class TestJsonFormatter:
    """Tests for JsonFormatter class."""

    def test_json_formatter_output(self):
        """Log output is valid JSON."""
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test message",
            args=(),
            exc_info=None
        )

        output = formatter.format(record)
        parsed = json.loads(output)

        assert parsed["message"] == "Test message"
        assert parsed["level"] == "INFO"
        assert parsed["logger"] == "test"

    def test_json_formatter_includes_timestamp(self):
        """Log output includes timestamp."""
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test",
            args=(),
            exc_info=None
        )

        output = formatter.format(record)
        parsed = json.loads(output)

        assert "timestamp" in parsed
        assert parsed["timestamp"].endswith("Z")

    def test_json_formatter_includes_location(self):
        """Log output includes file location."""
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="/path/to/test.py",
            lineno=42,
            msg="Test",
            args=(),
            exc_info=None
        )

        output = formatter.format(record)
        parsed = json.loads(output)

        assert "location" in parsed
        assert parsed["location"]["line"] == 42
        assert "function" in parsed["location"]


class TestTraceCorrelation:
    """Tests for trace ID correlation in logs."""

    def test_log_includes_trace_id(self):
        """Log entries include trace_id field."""
        formatter = JsonFormatter()

        init_tracer("test-service")
        with create_span("test-span"):
            record = logging.LogRecord(
                name="test",
                level=logging.INFO,
                pathname="test.py",
                lineno=10,
                msg="Test",
                args=(),
                exc_info=None
            )

            output = formatter.format(record)
            parsed = json.loads(output)

            assert "trace_id" in parsed
            assert len(parsed["trace_id"]) == 32

    def test_log_includes_span_id(self):
        """Log entries include span_id field."""
        formatter = JsonFormatter()

        init_tracer("test-service")
        with create_span("test-span"):
            record = logging.LogRecord(
                name="test",
                level=logging.INFO,
                pathname="test.py",
                lineno=10,
                msg="Test",
                args=(),
                exc_info=None
            )

            output = formatter.format(record)
            parsed = json.loads(output)

            assert "span_id" in parsed
            assert len(parsed["span_id"]) == 16

    def test_log_zero_ids_no_span(self):
        """Log shows zero IDs when no active span."""
        formatter = JsonFormatter()
        init_tracer("test-service")

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test",
            args=(),
            exc_info=None
        )

        output = formatter.format(record)
        parsed = json.loads(output)

        assert parsed["trace_id"] == "0" * 32
        assert parsed["span_id"] == "0" * 16


class TestExtraFields:
    """Tests for extra fields in log records."""

    def test_log_extra_fields(self):
        """Extra fields passed to logger appear in output."""
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test",
            args=(),
            exc_info=None
        )
        record.custom_field = "custom_value"
        record.order_id = "ORD-123"

        output = formatter.format(record)
        parsed = json.loads(output)

        assert parsed["custom_field"] == "custom_value"
        assert parsed["order_id"] == "ORD-123"


class TestLogLevels:
    """Tests for different log levels."""

    def test_log_level_info(self):
        """INFO level works correctly."""
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Info message",
            args=(),
            exc_info=None
        )

        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["level"] == "INFO"

    def test_log_level_warning(self):
        """WARNING level works correctly."""
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.WARNING,
            pathname="test.py",
            lineno=10,
            msg="Warning message",
            args=(),
            exc_info=None
        )

        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["level"] == "WARNING"

    def test_log_level_error(self):
        """ERROR level works correctly."""
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="test.py",
            lineno=10,
            msg="Error message",
            args=(),
            exc_info=None
        )

        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["level"] == "ERROR"

    def test_log_with_exception(self):
        """Exception info is included in output."""
        formatter = JsonFormatter()

        try:
            raise ValueError("test error")
        except ValueError:
            import sys
            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="test.py",
            lineno=10,
            msg="Error occurred",
            args=(),
            exc_info=exc_info
        )

        output = formatter.format(record)
        parsed = json.loads(output)

        assert "exception" in parsed
        assert "ValueError" in parsed["exception"]
