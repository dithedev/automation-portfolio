"""Unit tests for demo fixture feed client."""

from pathlib import Path

import pytest

from app.application.feed_http_types import FeedHttpError
from app.config import Settings
from app.domain.enums import ErrorCode
from app.infrastructure.feeds.demo_client import DemoFixtureFeedHttpClient
from app.infrastructure.feeds.factory import build_feed_http_client
from app.infrastructure.feeds.http import SafeFeedHttpClient


def _settings(**overrides: object) -> Settings:
    data: dict[str, object] = {
        "APP_MODE": "demo",
        "DATABASE_URL": "postgresql+asyncpg://news:news@localhost:5432/news",
        "FEEDS_CONFIG_PATH": Path("config/feeds.yaml"),
    }
    data.update(overrides)
    return Settings(_env_file=None, **data)


@pytest.mark.asyncio
async def test_demo_fixture_client_returns_fresh_rss() -> None:
    client = DemoFixtureFeedHttpClient(_settings())
    result = await client.fetch(
        feed_url="https://openai.com/news/rss.xml",
        allowed_host="openai.com",
        etag=None,
        last_modified=None,
        read_timeout_seconds=5,
        max_bytes=1_000_000,
    )
    assert result.status_code == 200
    assert result.body is not None
    assert b"<rss" in result.body
    assert b"{{PUB_DATE" not in result.body
    assert result.etag is not None


@pytest.mark.asyncio
async def test_demo_fixture_client_supports_not_modified() -> None:
    client = DemoFixtureFeedHttpClient(_settings())
    first = await client.fetch(
        feed_url="https://blog.google/innovation-and-ai/technology/ai/rss/",
        allowed_host="blog.google",
        etag=None,
        last_modified=None,
        read_timeout_seconds=5,
        max_bytes=1_000_000,
    )
    second = await client.fetch(
        feed_url="https://blog.google/innovation-and-ai/technology/ai/rss/",
        allowed_host="blog.google",
        etag=first.etag,
        last_modified=None,
        read_timeout_seconds=5,
        max_bytes=1_000_000,
    )
    assert second.status_code == 304
    assert second.body is None


@pytest.mark.asyncio
async def test_demo_fixture_client_rejects_unsafe_url() -> None:
    client = DemoFixtureFeedHttpClient(_settings())
    with pytest.raises(FeedHttpError) as raised:
        await client.fetch(
            feed_url="https://evil.example/feed.xml",
            allowed_host="openai.com",
            etag=None,
            last_modified=None,
            read_timeout_seconds=5,
            max_bytes=1_000_000,
        )
    assert raised.value.error_code is ErrorCode.UNSAFE_FEED_URL


def test_factory_selects_demo_vs_live_client() -> None:
    demo = build_feed_http_client(_settings(APP_MODE="demo"))
    live = build_feed_http_client(
        _settings(
            APP_MODE="live",
            OPENAI_API_KEY="sk-test-key-1234567890",
            MANUAL_RUN_ENABLED=False,
        )
    )
    assert isinstance(demo, DemoFixtureFeedHttpClient)
    assert isinstance(live, SafeFeedHttpClient)
