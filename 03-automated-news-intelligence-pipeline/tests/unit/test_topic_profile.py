"""Unit tests for topic profile loading and source limit resolution."""

from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest

from app.application.source_limits import resolve_source_limits
from app.config import PROJECT_ROOT, Settings
from app.domain import Source
from app.infrastructure.feeds.config import FeedConfiguration, load_feed_configuration
from app.infrastructure.topic_profile import TopicProfileError, load_topic_profile


def _settings(**overrides: object) -> Settings:
    data: dict[str, object] = {
        "APP_MODE": "demo",
        "DATABASE_URL": "postgresql+asyncpg://news:news@localhost:5432/news",
        "MAX_ARTICLES_PER_SOURCE": 20,
        "HTTP_TIMEOUT_SECONDS": 15,
    }
    data.update(overrides)
    return Settings(_env_file=None, **data)


def test_load_default_topic_profile() -> None:
    profile = load_topic_profile(PROJECT_ROOT / "config" / "topic_profile.yaml")

    assert profile.name.startswith("AI")
    assert "ai" in profile.include_keywords
    assert profile.min_title_length == 12


def test_topic_profile_rejects_invalid_file(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("version: 1\nname: x\ninclude_keywords: []\n", encoding="utf-8")

    with pytest.raises(TopicProfileError):
        load_topic_profile(path)


def test_resolve_source_limits_caps_at_fifty() -> None:
    settings = _settings(MAX_ARTICLES_PER_SOURCE=50)
    config = load_feed_configuration(PROJECT_ROOT / "config" / "feeds.yaml")
    source = Source(
        id=uuid4(),
        key="openai-news",
        name="OpenAI News",
        feed_url="https://openai.com/news/rss.xml",
        allowed_host="openai.com",
        category="artificial_intelligence",
        priority=Decimal("5.00"),
    )

    limits = resolve_source_limits(
        settings=settings,
        feed_configuration=config,
        sources=(source,),
    )

    assert limits[source.id].max_entries == 20  # yaml default wins under min()
    assert limits[source.id].read_timeout_seconds == 15.0


def test_feed_configuration_loads() -> None:
    config = load_feed_configuration(PROJECT_ROOT / "config" / "feeds.yaml")
    assert isinstance(config, FeedConfiguration)
    assert len(config.sources) >= 3
