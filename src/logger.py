"""Structured logging configuration."""
import logging
import re
import sys
from typing import Any

import structlog
from structlog.processors import JSONRenderer, TimeStamper
from structlog.stdlib import LoggerFactory, ProcessorFormatter

from config import settings

TOKEN_PATTERN = re.compile(r"\b\d{6,12}:[A-Za-z0-9_-]{20,}\b")
BEARER_PATTERN = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]+=*\b")


def _redact_value(value: Any) -> Any:
    if isinstance(value, str):
        value = TOKEN_PATTERN.sub("[REDACTED_TELEGRAM_TOKEN]", value)
        return BEARER_PATTERN.sub("Bearer [REDACTED]", value)
    if isinstance(value, dict):
        return {key: _redact_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact_value(item) for item in value]
    return value


def redact_sensitive_data(_, __, event_dict):
    """Redact credentials from application and third-party log records."""
    return {key: _redact_value(value) for key, value in event_dict.items()}


def setup_logging():
    """配置结构化日志"""
    level = getattr(logging, settings.log_level)
    timestamper = TimeStamper(fmt="iso", utc=True)
    foreign_processors = [
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        timestamper,
        redact_sensitive_data,
    ]
    formatter = ProcessorFormatter(
        processor=JSONRenderer(),
        foreign_pre_chain=foreign_processors,
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level)

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            timestamper,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            redact_sensitive_data,
            ProcessorFormatter.wrap_for_formatter,
        ],
        context_class=dict,
        logger_factory=LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def get_logger(name: str):
    """获取日志记录器"""
    return structlog.get_logger(name)
