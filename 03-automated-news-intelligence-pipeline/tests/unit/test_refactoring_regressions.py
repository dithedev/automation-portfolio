import pytest
from pydantic import ValidationError

from app.config import Settings
from app.domain.validators import ensure_https_url


def settings_data() -> dict[str, object]:
    return {
        "APP_ENV": "test",
        "APP_MODE": "demo",
        "APP_TIMEZONE": "UTC",
        "POSTGRES_PASSWORD": "local-database-password",
        "DATABASE_URL": (
            "postgresql+asyncpg://news_pipeline:"
            "local-database-password@localhost:5432/news_pipeline"
        ),
        "MIN_DIGEST_ITEMS": 3,
        "MAX_DIGEST_ITEMS": 7,
        "MAX_LLM_CANDIDATES": 25,
        "DIGEST_TOP_ARTICLES": 5,
        "DIGEST_LANGUAGE": "en",
    }


@pytest.mark.parametrize("count", [3, 7])
def test_settings_accept_digest_count_boundaries(count: int) -> None:
    data = settings_data()
    data["DIGEST_TOP_ARTICLES"] = count
    settings = Settings(_env_file=None, **data)

    assert settings.digest_top_articles == count


@pytest.mark.parametrize("count", [0, 1, 2, 8, 20])
def test_settings_reject_count_outside_generation_limits(count: int) -> None:
    data = settings_data()
    data["DIGEST_TOP_ARTICLES"] = count

    with pytest.raises(ValidationError, match="DIGEST_TOP_ARTICLES"):
        Settings(_env_file=None, **data)


@pytest.mark.parametrize("language", ["ru", "lt", ""])
def test_settings_reject_unsupported_digest_language(language: str) -> None:
    data = settings_data()
    data["DIGEST_LANGUAGE"] = language

    with pytest.raises(ValidationError, match="DIGEST_LANGUAGE"):
        Settings(_env_file=None, **data)


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com:invalid/rss",
        "https://example.com:99999/rss",
        "https://example.com:-1/rss",
        "https://example.com:0/rss",
        "https://example.com:/rss",
    ],
)
def test_https_validator_rejects_invalid_ports(url: str) -> None:
    with pytest.raises(ValueError, match="valid port"):
        ensure_https_url(url, "feed_url")


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/article",
        "https://example.com:443/article",
        "https://example.com:1/article",
        "https://example.com:65535/article",
    ],
)
def test_general_https_validator_accepts_valid_ports(url: str) -> None:
    ensure_https_url(
        url,
        "article_url",
        expected_hostname="example.com",
    )


def test_settings_validators_have_docstrings() -> None:
    assert Settings.validate_timezone.__doc__
    assert Settings.resolve_project_relative_path.__doc__
    assert Settings.validate_database_url.__doc__
    assert Settings.validate_security_settings.__doc__
