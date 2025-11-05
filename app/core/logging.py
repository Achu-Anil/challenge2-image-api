"""
Structured logging configuration with request ID tracking.

This module sets up JSON-structured logging with correlation IDs for request tracing.
All logs include contextual information like timestamps, log levels, and request IDs.
"""

import logging
import sys
import uuid
from contextvars import ContextVar
from typing import Any

import orjson

# Context variable to store request ID across async contexts
request_id_var: ContextVar[str] = ContextVar("request_id", default="")


def set_request_id(request_id: str | None = None) -> str:
    """
    Set the request ID for the current context.
    
    Args:
        request_id: Optional request ID. If None, generates a new UUID.
    
    Returns:
        The request ID that was set
    """
    rid = request_id or str(uuid.uuid4())
    request_id_var.set(rid)
    return rid


def get_request_id() -> str:
    """
    Get the request ID for the current context.
    
    Returns:
        Current request ID, or empty string if not set
    """
    return request_id_var.get()


class StructuredFormatter(logging.Formatter):
    """
    Custom JSON formatter for structured logging.
    
    Outputs logs as JSON objects with consistent fields including:
    - timestamp: ISO 8601 formatted time
    - level: Log level name
    - logger: Logger name
    - message: Log message
    - request_id: Current request correlation ID
    - Extra fields from log record
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON string."""
        log_data: dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": get_request_id(),
        }

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add extra fields from record
        for key, value in record.__dict__.items():
            if key not in [
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
                "message",
                "pathname",
                "process",
                "processName",
                "relativeCreated",
                "thread",
                "threadName",
                "exc_info",
                "exc_text",
                "stack_info",
            ]:
                log_data[key] = value

        return orjson.dumps(log_data).decode("utf-8")


def setup_logging(log_level: str = "INFO") -> None:
    """
    Configure application logging with structured JSON output.
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    # Remove existing handlers
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Create console handler with structured formatter
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StructuredFormatter())

    # Configure root logger
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level)

    # Reduce noise from third-party libraries
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance with the specified name.
    
    Args:
        name: Logger name (typically __name__ of the module)
    
    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)
