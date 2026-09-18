"""Unit tests for Stage 6 CLI helpers and API gates."""

from datetime import UTC, datetime

from app.api.main import _next_scheduled_run
from app.cli.app import _redacted_settings_lines, exit_code_for_run_status
from app.config import Settings
from app.domain import PipelineRunStatus


def _settings(**overrides: object) -> Settings:
    data: dict[str, object] = {
        "APP_MODE": "demo",
        "DATABASE_URL": "postgresql+asyncpg://news:news@localhost:5432/news",
        "TELEGRAM_ENABLED": False,
        "SCHEDULER_ENABLED": True,
        "DIGEST_SCHEDULE_HOUR": 8,
        "DIGEST_SCHEDULE_MINUTE": 0,
        "SCHEDULER_TIMEZONE": "UTC",
    }
    data.update(overrides)
    return Settings(_env_file=None, **data)


def test_exit_code_for_success_statuses() -> None:
    assert exit_code_for_run_status(PipelineRunStatus.SUCCESS) == 0
    assert exit_code_for_run_status(PipelineRunStatus.PARTIAL_SUCCESS) == 0
    assert exit_code_for_run_status(PipelineRunStatus.NO_CONTENT) == 0
    assert exit_code_for_run_status(PipelineRunStatus.SKIPPED_LOCKED) == 0
    assert exit_code_for_run_status(PipelineRunStatus.FAILED) == 1


def test_check_config_redacts_secrets() -> None:
    settings = _settings(
        OPENAI_API_KEY="sk-test-secret-value-123456",
        TELEGRAM_BOT_TOKEN="tg-secret",
        TELEGRAM_CHAT_ID="999",
        ADMIN_API_KEY="a" * 32,
    )
    lines = "\n".join(_redacted_settings_lines(settings))
    assert "sk-test-secret" not in lines
    assert "tg-secret" not in lines
    assert "openai_api_key=***" in lines
    assert "telegram_bot_token=***" in lines
    assert "database_url=***" in lines


def test_next_scheduled_run_none_when_disabled() -> None:
    settings = _settings(SCHEDULER_ENABLED=False)
    assert _next_scheduled_run(settings, now=datetime(2026, 9, 15, 7, 0, tzinfo=UTC)) is None


def test_next_scheduled_run_when_enabled() -> None:
    settings = _settings(SCHEDULER_ENABLED=True)
    nxt = _next_scheduled_run(settings, now=datetime(2026, 9, 15, 7, 0, tzinfo=UTC))
    assert nxt is not None
    assert nxt.startswith("2026-09-15T08:00:00")
