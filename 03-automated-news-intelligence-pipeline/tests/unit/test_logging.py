"""Unit tests for structured logging redaction and sanitization."""

from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from uuid import uuid4

from app.config import Settings
from app.observability.logging import (
    bind_run,
    clear_run_context,
    configure_logging,
    get_logger,
    log_event,
    redact_event_dict,
    sanitize_log_text,
)


def _settings(**overrides: object) -> Settings:
    data: dict[str, object] = {
        "APP_MODE": "demo",
        "APP_ENV": "development",
        "DATABASE_URL": "postgresql+asyncpg://news:news@localhost:5432/news",
    }
    data.update(overrides)
    return Settings(_env_file=None, **data)


def test_sanitize_log_text_strips_crlf_and_controls() -> None:
    dirty = "ok\r\ninject\x00evil\nmore"
    assert "\r" not in sanitize_log_text(dirty)
    assert "\n" not in sanitize_log_text(dirty)
    assert "\x00" not in sanitize_log_text(dirty)
    assert "ok" in sanitize_log_text(dirty)
    assert "inject" in sanitize_log_text(dirty)


def test_redact_event_dict_masks_secrets_and_content() -> None:
    event = {
        "event": "pipeline.started",
        "openai_api_key": "sk-secret-value",
        "authorization": "Bearer tok",
        "database_url": "postgresql://u:p@h/db",
        "telegram_bot_token": "123:ABC",
        "chat_id": "-100123",
        "title": "Should not appear",
        "summary": "Should not appear either",
        "safe_count": 3,
        "note": "line1\r\nline2",
    }
    redacted = redact_event_dict(None, "info", event)  # type: ignore[arg-type]
    assert redacted["openai_api_key"] == "***"
    assert redacted["authorization"] == "***"
    assert redacted["database_url"] == "***"
    assert redacted["telegram_bot_token"] == "***"
    assert redacted["chat_id"] == "***"
    assert redacted["title"] == "***"
    assert redacted["summary"] == "***"
    assert redacted["safe_count"] == 3
    assert "\r" not in str(redacted["note"])
    assert "\n" not in str(redacted["note"])


def test_configure_logging_console_and_bind_run() -> None:
    configure_logging(_settings(APP_ENV="development"))
    bind_run(run_id=uuid4())
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        log_event("pipeline.started", trigger_type="manual")
    clear_run_context()
    assert "pipeline.started" in buffer.getvalue()
    configure_logging(
        _settings(
            APP_ENV="production",
            POSTGRES_PASSWORD="strong-database-password-xyz",
            ADMIN_API_KEY="a" * 32,
        )
    )
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        get_logger().info(
            "test.event",
            run_id=uuid4(),
            openai_api_key="sk-leaked-key",
            admin_api_key="admin-secret",
            message="hello\r\nworld",
        )
    output = buffer.getvalue()
    assert "sk-leaked-key" not in output
    assert "admin-secret" not in output
    assert "\r" not in output
    payload = json.loads(output.strip())
    assert payload["event"] == "test.event"
    assert payload["openai_api_key"] == "***"
    assert payload["admin_api_key"] == "***"
    assert "service" in payload
    assert "app_version" in payload
    assert "timestamp" in payload
    assert payload["level"] == "info"
