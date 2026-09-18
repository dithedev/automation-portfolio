"""Unit tests for the safe feed HTTP client."""

from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

from app.application.feed_http_types import FeedHttpError
from app.config import PROJECT_ROOT, Settings
from app.domain.enums import ErrorCode
from app.infrastructure.feeds.http import SafeFeedHttpClient


def _settings(**overrides: object) -> Settings:
    data: dict[str, object] = {
        "APP_MODE": "demo",
        "DATABASE_URL": "postgresql+asyncpg://news:news@localhost:5432/news",
        "FEEDS_CONFIG_PATH": Path("config/feeds.yaml"),
        "HTTP_MAX_RETRIES": 2,
        "FEED_RESPONSE_MAX_BYTES": 1024,
        "USER_AGENT": "TestPipeline/0.1 (https://example.com)",
    }
    data.update(overrides)
    return Settings(_env_file=None, **data)


@pytest.fixture
def public_dns(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    async def fake_resolve(hostname: str) -> tuple[str, ...]:
        assert hostname == "example.com"
        return ("203.0.113.10",)

    monkeypatch.setattr(
        "app.infrastructure.feeds.http.resolve_public_addresses",
        fake_resolve,
    )
    yield


@pytest.mark.asyncio
async def test_fetch_success_streams_body(public_dns: None) -> None:
    body = b'<?xml version="1.0"?><rss><channel></channel></rss>'

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "203.0.113.10"
        assert request.headers["Host"] == "example.com"
        assert request.headers["If-None-Match"] == '"etag-1"'
        return httpx.Response(
            200,
            content=body,
            headers={
                "Content-Type": "application/rss+xml",
                "ETag": '"etag-2"',
                "Last-Modified": "Wed, 01 Jan 2025 00:00:00 GMT",
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, follow_redirects=False) as client:
        feed_client = SafeFeedHttpClient(_settings(), client=client)
        result = await feed_client.fetch(
            feed_url="https://example.com/feed.xml",
            allowed_host="example.com",
            etag='"etag-1"',
            last_modified=None,
            read_timeout_seconds=5,
            max_bytes=1024,
        )

    assert result.status_code == 200
    assert result.body == body
    assert result.etag == '"etag-2"'


@pytest.mark.asyncio
async def test_fetch_not_modified(public_dns: None) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(304, headers={"ETag": '"same"'})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, follow_redirects=False) as client:
        feed_client = SafeFeedHttpClient(_settings(), client=client)
        result = await feed_client.fetch(
            feed_url="https://example.com/feed.xml",
            allowed_host="example.com",
            etag='"same"',
            last_modified=None,
            read_timeout_seconds=5,
            max_bytes=1024,
        )

    assert result.status_code == 304
    assert result.body is None


@pytest.mark.asyncio
async def test_fetch_rejects_oversized_body(public_dns: None) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"x" * 2048,
            headers={"Content-Type": "application/xml"},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, follow_redirects=False) as client:
        feed_client = SafeFeedHttpClient(_settings(), client=client)
        with pytest.raises(FeedHttpError) as raised:
            await feed_client.fetch(
                feed_url="https://example.com/feed.xml",
                allowed_host="example.com",
                etag=None,
                last_modified=None,
                read_timeout_seconds=5,
                max_bytes=1024,
            )

    assert raised.value.error_code is ErrorCode.FEED_RESPONSE_TOO_LARGE


@pytest.mark.asyncio
async def test_fetch_retries_server_error_then_succeeds(public_dns: None) -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(503, content=b"busy")
        return httpx.Response(
            200,
            content=b"<?xml version='1.0'?><rss></rss>",
            headers={"Content-Type": "application/rss+xml"},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, follow_redirects=False) as client:
        feed_client = SafeFeedHttpClient(_settings(HTTP_MAX_RETRIES=3), client=client)
        result = await feed_client.fetch(
            feed_url="https://example.com/feed.xml",
            allowed_host="example.com",
            etag=None,
            last_modified=None,
            read_timeout_seconds=5,
            max_bytes=1024,
        )

    assert result.status_code == 200
    assert calls["count"] == 2


@pytest.mark.asyncio
async def test_fetch_rejects_private_literal_ip() -> None:
    feed_client = SafeFeedHttpClient(_settings())
    with pytest.raises(FeedHttpError) as raised:
        await feed_client.fetch(
            feed_url="https://127.0.0.1/feed.xml",
            allowed_host="127.0.0.1",
            etag=None,
            last_modified=None,
            read_timeout_seconds=5,
            max_bytes=1024,
        )

    assert raised.value.error_code is ErrorCode.UNSAFE_FEED_URL


@pytest.mark.asyncio
async def test_fetch_does_not_follow_redirect(public_dns: None) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": "https://evil.example/feed"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, follow_redirects=False) as client:
        feed_client = SafeFeedHttpClient(_settings(), client=client)
        with pytest.raises(FeedHttpError):
            await feed_client.fetch(
                feed_url="https://example.com/feed.xml",
                allowed_host="example.com",
                etag=None,
                last_modified=None,
                read_timeout_seconds=5,
                max_bytes=1024,
            )


def test_project_root_available_for_settings_paths() -> None:
    assert (PROJECT_ROOT / "config" / "feeds.yaml").exists()
