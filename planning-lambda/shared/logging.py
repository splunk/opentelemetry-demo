# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Structured JSON logging with OpenTelemetry trace correlation."""

import os
import sys
import json
import logging
from datetime import datetime
from typing import Any, Dict

from .tracing import get_current_trace_id, get_current_span_id


class JsonFormatter(logging.Formatter):
    """
    JSON log formatter with OpenTelemetry trace correlation.

    Formats log records as JSON with automatic injection of:
    - trace_id: Current OpenTelemetry trace ID
    - span_id: Current OpenTelemetry span ID
    - timestamp: ISO format timestamp
    - level: Log level
    - message: Log message
    - Extra fields from the log record
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record as JSON."""
        log_data: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "trace_id": get_current_trace_id(),
            "span_id": get_current_span_id(),
        }

        # Add location info
        log_data["location"] = {
            "file": record.filename,
            "line": record.lineno,
            "function": record.funcName,
        }

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add extra fields (excluding standard LogRecord attributes)
        standard_attrs = {
            'name', 'msg', 'args', 'created', 'filename', 'funcName',
            'levelname', 'levelno', 'lineno', 'module', 'msecs',
            'pathname', 'process', 'processName', 'relativeCreated',
            'stack_info', 'exc_info', 'exc_text', 'thread', 'threadName',
            'message', 'taskName'
        }

        for key, value in record.__dict__.items():
            if key not in standard_attrs and not key.startswith('_'):
                log_data[key] = value

        return json.dumps(log_data, default=str)


class LambdaLogger(logging.Logger):
    """Custom logger class with Lambda-specific features."""

    def __init__(self, name: str, level: int = logging.NOTSET):
        super().__init__(name, level)

    def with_context(self, **kwargs) -> 'LoggerAdapter':
        """Create a logger adapter with additional context."""
        return LoggerAdapter(self, kwargs)


class LoggerAdapter(logging.LoggerAdapter):
    """Logger adapter that adds context to all log messages."""

    def process(self, msg, kwargs):
        """Add extra context to the log record."""
        extra = kwargs.get('extra', {})
        extra.update(self.extra)
        kwargs['extra'] = extra
        return msg, kwargs


def get_logger(name: str = None) -> logging.Logger:
    """
    Get a configured JSON logger.

    Args:
        name: Logger name. Defaults to 'planning-lambda'.

    Returns:
        Configured logger instance.
    """
    name = name or os.getenv("OTEL_SERVICE_NAME", "planning-lambda")

    # Use custom logger class
    logging.setLoggerClass(LambdaLogger)
    logger = logging.getLogger(name)

    # Only configure if not already configured
    if not logger.handlers:
        # Set log level from environment
        log_level = os.getenv("LOG_LEVEL", "INFO").upper()
        logger.setLevel(getattr(logging, log_level, logging.INFO))

        # Create console handler with JSON formatter
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)

        # Prevent propagation to root logger
        logger.propagate = False

    return logger
