"""Security-focused unit checks for logging sanitization and secret redaction."""

from __future__ import annotations

import io
import json
from contextlib import redirect_stdout

from app.config import Settings
from app.observability.logging import configure_logging, get_logger, sanitize_log_text


def _settings(**overrides: object) -> Settings:
    data: dict[str, object] = {
        "APP_MODE": "demo",
        "APP_ENV": "development",
        "DATABASE_URL": "postgresql+asyncpg://news:news@localhost:5432/news",
    }
    data.update(overrides)
    return Settings(_env_file=None, **data)


def test_logging_neutralizes_crlf_injection() -> None:
    configure_logging(
        _settings(
            APP_ENV="production",
            POSTGRES_PASSWORD="strong-database-password-xyz",
            ADMIN_API_KEY="b" * 32,
        )
    )
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        get_logger().info(
            "security.crlf",
            detail="prefix\r\nINFO forged-level attacker",
        )
    output = buffer.getvalue()
    assert "\r" not in output
    payload = json.loads(output.strip())
    assert "\n" not in payload["detail"]
    assert "\r" not in payload["detail"]
    assert "forged-level" in payload["detail"]


def test_secret_like_values_never_appear_in_log_output() -> None:
    configure_logging(
        _settings(
            APP_ENV="production",
            POSTGRES_PASSWORD="strong-database-password-xyz",
            ADMIN_API_KEY="c" * 32,
        )
    )
    secrets = {
        "openai_api_key": "sk-proj-super-secret-key-value",
        "telegram_bot_token": "7123456789:AAHsecretTokenValueHere",
        "admin_api_key": "admin-secret-key-zzzz",
        "authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.secret",
        "database_url": "postgresql+asyncpg://user:pass@db:5432/news",
        "chat_id": "-1009876543210",
    }
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        get_logger().info("security.secrets", **secrets)
    output = buffer.getvalue()
    for value in secrets.values():
        assert value not in output
    payload = json.loads(output.strip())
    for key in secrets:
        assert payload[key] == "***"


def test_sanitize_log_text_public_helper() -> None:
    assert sanitize_log_text("a\nb\rc") == "a b c"
