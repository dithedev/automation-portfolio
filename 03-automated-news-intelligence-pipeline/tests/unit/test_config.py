from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import PROJECT_ROOT, Settings


def valid_settings_data() -> dict[str, object]:
    return {
        "APP_ENV": "development",
        "APP_MODE": "demo",
        "APP_TIMEZONE": "Europe/Vilnius",
        "POSTGRES_PASSWORD": "local-database-password",
        "DATABASE_URL": (
            "postgresql+asyncpg://news_pipeline:"
            "local-database-password@localhost:5432/news_pipeline"
        ),
        "OPENAI_API_KEY": "sk-local-placeholder",
        "OPENAI_MODEL": "gpt-4o-mini",
        "TELEGRAM_BOT_TOKEN": "local-telegram-token",
        "TELEGRAM_CHAT_ID": "123456789",
        "TELEGRAM_ENABLED": False,
        "ADMIN_API_KEY": "local-admin-key",
        "MIN_DIGEST_ITEMS": 3,
        "MAX_DIGEST_ITEMS": 7,
        "MAX_LLM_CANDIDATES": 25,
        "DIGEST_TOP_ARTICLES": 5,
        "DIGEST_LANGUAGE": "en",
    }


def test_settings_load_expected_values() -> None:
    settings = Settings(_env_file=None, **valid_settings_data())

    assert settings.app_name == "Automated News Intelligence Pipeline"
    assert settings.app_mode == "demo"
    assert settings.app_timezone == "Europe/Vilnius"
    assert settings.openai_model == "gpt-4o-mini"
    assert settings.telegram_enabled is False


def test_secrets_are_masked_in_string_representation() -> None:
    settings = Settings(_env_file=None, **valid_settings_data())
    representation = repr(settings)

    assert "sk-local-placeholder" not in representation
    assert "local-database-password" not in representation
    assert "local-telegram-token" not in representation
    assert "123456789" not in representation
    assert "**********" in representation


def test_relative_feeds_path_is_resolved_from_project_root() -> None:
    data = valid_settings_data()
    data["FEEDS_CONFIG_PATH"] = Path("config/feeds.yaml")
    settings = Settings(_env_file=None, **data)

    assert settings.feeds_config_path == PROJECT_ROOT / "config/feeds.yaml"


def test_unknown_timezone_is_rejected() -> None:
    data = valid_settings_data()
    data["APP_TIMEZONE"] = "Unknown/Timezone"

    with pytest.raises(ValidationError, match="Unknown IANA timezone"):
        Settings(_env_file=None, **data)


def test_model_other_than_gpt_4o_mini_is_rejected() -> None:
    data = valid_settings_data()
    data["OPENAI_MODEL"] = "gpt-4.1"

    with pytest.raises(ValidationError, match="OPENAI_MODEL must be gpt-4o-mini"):
        Settings(_env_file=None, **data)


def test_production_rejects_placeholder_secrets() -> None:
    data = valid_settings_data()
    data.update(
        {
            "APP_ENV": "production",
            "POSTGRES_PASSWORD": "change-me-in-production",
            "ADMIN_API_KEY": "a" * 32,
        }
    )

    with pytest.raises(
        ValidationError,
        match="POSTGRES_PASSWORD contains an unsafe placeholder",
    ):
        Settings(_env_file=None, **data)


def test_production_requires_long_admin_api_key() -> None:
    data = valid_settings_data()
    data.update(
        {
            "APP_ENV": "production",
            "POSTGRES_PASSWORD": "strong-database-password",
            "ADMIN_API_KEY": "too-short",
        }
    )

    with pytest.raises(
        ValidationError,
        match="ADMIN_API_KEY must contain at least 32 characters",
    ):
        Settings(_env_file=None, **data)


def test_demo_does_not_require_external_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        "OPENAI_API_KEY",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID",
        "ADMIN_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)

    data = valid_settings_data()

    for name in (
        "OPENAI_API_KEY",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID",
        "ADMIN_API_KEY",
    ):
        data.pop(name)

    settings = Settings(_env_file=None, **data)

    assert settings.openai_api_key is None
    assert settings.telegram_bot_token is None
    assert settings.telegram_chat_id is None
    assert settings.admin_api_key is None


@pytest.mark.parametrize(
    "field_name",
    ["OPENAI_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "ADMIN_API_KEY"],
)
@pytest.mark.parametrize("value", ["", "   "])
def test_live_rejects_blank_required_credentials(
    field_name: str,
    value: str,
) -> None:
    data = valid_settings_data()
    data.update(
        {
            "APP_MODE": "live",
            "TELEGRAM_ENABLED": True,
            field_name: value,
        }
    )

    with pytest.raises(ValidationError, match=field_name):
        Settings(_env_file=None, **data)


def test_live_without_delivery_does_not_require_telegram_credentials() -> None:
    data = valid_settings_data()
    data.update(
        {
            "APP_MODE": "live",
            "TELEGRAM_ENABLED": False,
            "TELEGRAM_BOT_TOKEN": None,
            "TELEGRAM_CHAT_ID": None,
        }
    )

    settings = Settings(_env_file=None, **data)

    assert settings.telegram_enabled is False


@pytest.mark.parametrize("value", ["", "   "])
def test_blank_postgres_password_is_rejected(value: str) -> None:
    data = valid_settings_data()
    data["POSTGRES_PASSWORD"] = value

    with pytest.raises(ValidationError, match="POSTGRES_PASSWORD"):
        Settings(_env_file=None, **data)


@pytest.mark.parametrize(
    "database_url",
    [
        "",
        "postgresql://user:password@localhost/database",
        "postgresql+asyncpg://localhost/database",
        "postgresql+asyncpg://user:@localhost/database",
        "postgresql+asyncpg://user:password@localhost/",
        "postgresql+asyncpg://user:password@localhost:99999/database",
        "postgresql+asyncpg://user:password@localhost:invalid/database",
    ],
)
def test_invalid_database_url_is_rejected(database_url: str) -> None:
    data = valid_settings_data()
    data["DATABASE_URL"] = database_url

    with pytest.raises(ValidationError, match="valid postgresql\\+asyncpg DSN"):
        Settings(_env_file=None, **data)


def test_database_validation_error_does_not_expose_password() -> None:
    data = valid_settings_data()
    data["DATABASE_URL"] = (
        "postgresql+asyncpg://user:private-database-password@localhost:invalid/db"
    )

    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None, **data)

    assert "private-database-password" not in str(error.value)


def test_production_checks_password_inside_database_url() -> None:
    data = valid_settings_data()
    data.update(
        {
            "APP_ENV": "production",
            "ADMIN_API_KEY": "a" * 32,
            "DATABASE_URL": ("postgresql+asyncpg://user:change-me@localhost/database"),
        }
    )

    with pytest.raises(
        ValidationError,
        match="DATABASE_URL contains an unsafe placeholder",
    ):
        Settings(_env_file=None, **data)


def test_declared_feed_and_selection_limits() -> None:
    settings = Settings(_env_file=None, **valid_settings_data())

    assert settings.min_digest_items == 3
    assert settings.max_digest_items == 7
    assert settings.max_llm_candidates == 25
    assert settings.max_item_age_hours == 72
    assert settings.feed_fetch_concurrency == 3
    assert settings.feed_response_max_bytes == 2_097_152
    assert settings.max_new_items_per_run == 100


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("MAX_ARTICLES_PER_SOURCE", 51),
        ("MAX_NEW_ITEMS_PER_RUN", 101),
        ("MAX_LLM_CANDIDATES", 26),
        ("MIN_DIGEST_ITEMS", 2),
        ("FEED_FETCH_CONCURRENCY", 0),
        ("FEED_RESPONSE_MAX_BYTES", 0),
        ("MAX_ITEM_AGE_HOURS", 0),
    ],
)
def test_invalid_collection_limits_are_rejected(
    field_name: str,
    value: int,
) -> None:
    data = valid_settings_data()
    data[field_name] = value

    with pytest.raises(ValidationError, match=field_name):
        Settings(_env_file=None, **data)


def test_digest_target_must_fit_configured_limits() -> None:
    data = valid_settings_data()
    data["MIN_DIGEST_ITEMS"] = 6

    with pytest.raises(ValidationError, match="Digest limits"):
        Settings(_env_file=None, **data)


def test_llm_candidate_limit_must_cover_maximum_digest_size() -> None:
    data = valid_settings_data()
    data["MAX_LLM_CANDIDATES"] = 6

    with pytest.raises(ValidationError, match="MAX_LLM_CANDIDATES"):
        Settings(_env_file=None, **data)
