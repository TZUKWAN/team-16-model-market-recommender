"""
Logging configuration for the application.
Provides a reusable logger instance.
"""

import logging
import json
import re
import sys
from datetime import datetime, timezone
from .config import get_settings
from .request_context import get_correlation_id, get_request_id


SENSITIVE_LOG_PATTERNS = (
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/-]+=*", re.I),
    re.compile(r"\b(?:sk-|api[_-]?key\s*[:=]\s*)[A-Za-z0-9._-]{12,}", re.I),
    re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"),
    re.compile(r"(?<!\d)\d{16,19}(?!\d)"),
)


def sanitize_log_text(value: str) -> str:
    rendered = str(value)
    for pattern in SENSITIVE_LOG_PATTERNS:
        rendered = pattern.sub("[REDACTED]", rendered)
    return rendered


class SensitiveDataFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = sanitize_log_text(record.getMessage())
        record.args = ()
        return True


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(
            {
                "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "level": record.levelname,
                "logger": record.name,
                "request_id": get_request_id(),
                "correlation_id": get_correlation_id(),
                "message": record.getMessage(),
            },
            ensure_ascii=False,
        )


def setup_logging() -> logging.Logger:
    """Configure and return the application root logger."""
    settings = get_settings()
    logger = logging.getLogger(settings.APP_NAME)
    logger.setLevel(settings.LOG_LEVEL)

    # Avoid duplicate handlers on reload
    if logger.handlers:
        for existing in logging.getLogger().handlers:
            existing.addFilter(SensitiveDataFilter())
        return logger

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(settings.LOG_LEVEL)

    handler.addFilter(SensitiveDataFilter())
    handler.setFormatter(JsonLogFormatter())
    logger.addHandler(handler)

    root_logger = logging.getLogger()
    root_logger.setLevel(settings.LOG_LEVEL)
    if not root_logger.handlers:
        root_handler = logging.StreamHandler(sys.stdout)
        root_handler.setLevel(settings.LOG_LEVEL)
        root_handler.addFilter(SensitiveDataFilter())
        root_handler.setFormatter(JsonLogFormatter())
        root_logger.addHandler(root_handler)
    else:
        for existing in root_logger.handlers:
            existing.addFilter(SensitiveDataFilter())

    # Prevent propagation to root logger
    logger.propagate = False

    return logger


def get_logger(name: str | None = None) -> logging.Logger:
    """Get a child logger of the app root logger.

    Usage:
        logger = get_logger(__name__)
        logger.info("...")
    """
    settings = get_settings()
    return logging.getLogger(settings.APP_NAME if name is None else f"{settings.APP_NAME}.{name}")
