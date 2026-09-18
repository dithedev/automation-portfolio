"""Structured logging with redaction and CR/LF sanitization."""

from __future__ import annotations

import logging
import re
from collections.abc import MutableMapping
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from typing import Any
from uuid import UUID

import structlog

from app.config import Settings

SERVICE_NAME = "news-intelligence-pipeline"


def _app_version() -> str:
    try:
        return package_version("news-intelligence-pipeline")
    except PackageNotFoundError:
        return "0.1.0"


_SECRET_KEY_FRAGMENTS = frozenset(
    {
        "token",
        "password",
        "secret",
        "api_key",
        "apikey",
        "authorization",
        "dsn",
        "database_url",
        "chat_id",
        "bot_token",
        "openai_api_key",
        "admin_api_key",
    }
)

_FORBIDDEN_CONTENT_KEYS = frozenset(
    {
        "title",
        "summary",
        "body",
        "prompt",
        "articles_json",
        "system",
        "rendered_text",
        "feed_body",
        "raw_summary",
        "sanitized_summary",
    }
)

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]+")


def sanitize_log_text(value: str) -> str:
    """Strip CR/LF and other control characters from external/user text."""
    return _CONTROL_CHARS.sub(" ", value).strip()


def _is_secret_key(key: str) -> bool:
    lowered = key.lower().replace("-", "_")
    return any(fragment in lowered for fragment in _SECRET_KEY_FRAGMENTS)


def _redact_value(key: str, value: object) -> object:
    if _is_secret_key(key) or key.lower() in _FORBIDDEN_CONTENT_KEYS:
        return "***"
    if isinstance(value, str):
        return sanitize_log_text(value)
    if isinstance(value, UUID):
        return str(value)
    return value


def redact_event_dict(
    _logger: logging.Logger,
    _method_name: str,
    event_dict: MutableMapping[str, Any],
) -> MutableMapping[str, Any]:
    """Redact secrets and forbidden content; sanitize string values."""
    for key in list(event_dict):
        event_dict[key] = _redact_value(key, event_dict[key])
    return event_dict


def configure_logging(settings: Settings) -> None:
    """Configure structlog for production JSON or development console output."""
    structlog.reset_defaults()
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        redact_event_dict,
        structlog.processors.StackInfoRenderer(),
    ]

    if settings.app_env == "production":
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.app_log_level, logging.INFO),
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(**initial: object) -> Any:
    """Return a bound logger with service metadata."""
    logger = structlog.get_logger()
    return logger.bind(
        service=SERVICE_NAME,
        app_version=_app_version(),
        **initial,
    )


def bind_run(*, run_id: UUID | str) -> None:
    """Bind run_id into contextvars for subsequent log events."""
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(run_id=str(run_id))


def clear_run_context() -> None:
    """Clear bound run context after a pipeline attempt."""
    structlog.contextvars.clear_contextvars()


def log_event(event: str, **fields: object) -> None:
    """Emit one structured event with redaction applied."""
    get_logger().info(event, **fields)
