"""
Failure-injection coverage for TZ §20.6 scenarios.

Checklist (§20.6 → test):
- Timeout feed → test_pipeline_partial_feed_still_generates / test_feed_ingestion timeout paths
- Partial feed failures → test_pipeline_partial_feed_still_generates (test_pipeline.py)
- Malformed feed body → covered in feed ingestion / parser unit tests
- Invalid LLM output → test_pipeline_invalid_llm_output_fails_without_used (test_pipeline.py)
- Telegram 429 then success → test_delivery_retries_rate_limit_then_succeeds
- Telegram permanent 400 → test_delivery_permanent_failure_leaves_digest_failed
- Feed HTTP 429 → test_fetch_retries_429_then_succeeds / test_fetch_429_exhausted
- OpenAI timeout / 429 → test_openai_errors_fail_pipeline_items_not_used
- /health/ready when DB unavailable → test_health_ready_unavailable_when_db_broken
- Cancel between GENERATED and SENT → test_cancel_during_delivery_leaves_digest_unsent
- Concurrent skip → test_pipeline_skipped_locked_avoids_http / advisory lock tests
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.api.main import create_app
from app.application.digest_delivery import DigestDeliveryService
from app.application.feed_http_types import FeedHttpError, FeedHttpResponse
from app.application.llm_types import LlmError
from app.application.pipeline import DigestPipelineService
from app.application.telegram_types import TelegramSendResult
from app.config import Settings
from app.domain import (
    DigestStatus,
    ErrorCode,
    NewsItem,
    NewsItemStatus,
    PipelineRunStatus,
    Source,
    TriggerType,
)
from app.domain.hashing import content_hash, url_hash
from app.domain.text_sanitize import normalize_title
from app.infrastructure.db.repositories import (
    DigestRepository,
    NewsItemRepository,
    SourceRepository,
)
from app.infrastructure.db.session import transaction_scope
from app.infrastructure.feeds.http import SafeFeedHttpClient
from app.infrastructure.telegram.mock_client import MockTelegramClient
from tests.integration.test_digest_delivery import _seed_digest

NOW = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)


def _settings(**overrides: object) -> Settings:
    data: dict[str, object] = {
        "APP_MODE": "demo",
        "APP_ENV": "development",
        "DATABASE_URL": "postgresql+asyncpg://news:news@localhost:5432/news",
        "FEEDS_CONFIG_PATH": Path("config/feeds.yaml"),
        "TOPIC_PROFILE_PATH": Path("config/topic_profile.yaml"),
        "MAX_NEW_ITEMS_PER_RUN": 100,
        "MIN_DIGEST_ITEMS": 3,
        "MAX_DIGEST_ITEMS": 7,
        "DIGEST_TOP_ARTICLES": 5,
        "MAX_LLM_CANDIDATES": 25,
        "FEED_FETCH_CONCURRENCY": 2,
        "ARTICLE_MAX_LENGTH": 12_000,
        "MAX_ITEM_AGE_HOURS": 720,
        "USER_AGENT": "TestPipeline/0.1 (https://example.com)",
        "TELEGRAM_ENABLED": False,
        "TELEGRAM_CHAT_ID": "123456789",
        "HTTP_MAX_RETRIES": 2,
    }
    data.update(overrides)
    return Settings(_env_file=None, **data)


class _FailingLlm:
    def __init__(self, error: LlmError) -> None:
        self._error = error
        self.calls = 0

    async def generate_digest(self, **_kwargs: object) -> object:
        self.calls += 1
        raise self._error


class _FakeFeed:
    async def fetch(self, **_kwargs: object) -> FeedHttpResponse:
        return FeedHttpResponse(
            status_code=304,
            body=b"",
            etag=None,
            last_modified=None,
            duration_ms=1,
        )


@pytest.fixture
def public_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_resolve(hostname: str) -> tuple[str, ...]:
        assert hostname == "example.com"
        return ("203.0.113.10",)

    monkeypatch.setattr(
        "app.infrastructure.feeds.http.resolve_public_addresses",
        fake_resolve,
    )


@pytest.mark.asyncio
async def test_fetch_retries_429_then_succeeds(public_dns: None) -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(429, content=b"slow down")
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
async def test_fetch_429_exhausted(public_dns: None) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, content=b"slow down")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, follow_redirects=False) as client:
        feed_client = SafeFeedHttpClient(_settings(HTTP_MAX_RETRIES=2), client=client)
        with pytest.raises(FeedHttpError) as raised:
            await feed_client.fetch(
                feed_url="https://example.com/feed.xml",
                allowed_host="example.com",
                etag=None,
                last_modified=None,
                read_timeout_seconds=5,
                max_bytes=1024,
            )

    assert raised.value.error_code is ErrorCode.FEED_CONNECTION_FAILED


async def _seed_candidates(
    session_factory: async_sessionmaker[AsyncSession],
) -> Source:
    source = Source(
        key=f"fail-inj-{uuid4().hex[:8]}",
        name="Failure Injection",
        feed_url="https://example.com/fail-inj.xml",
        allowed_host="example.com",
        category="artificial_intelligence",
    )
    async with transaction_scope(session_factory) as session:
        await SourceRepository(session).add(source)
        news = NewsItemRepository(session)
        for index in range(3):
            title = f"AI automation product update number {index} for teams"
            summary = (
                "A long enough summary about AI automation and product delivery "
                f"practices for item {index}."
            )
            url = f"https://example.com/fail-inj-{index}-{source.key}"
            normalized = normalize_title(title)
            await news.add_if_new(
                NewsItem(
                    source_id=source.id,
                    original_url=url,
                    canonical_url=url,
                    url_hash=url_hash(url),
                    title=title,
                    normalized_title=normalized,
                    sanitized_summary=summary,
                    content_hash=content_hash(normalized, summary),
                    published_at=NOW,
                    collected_at=NOW,
                )
            )
    return source


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error_code", "summary"),
    [
        (ErrorCode.OPENAI_TIMEOUT, "openai timed out"),
        (ErrorCode.OPENAI_RATE_LIMITED, "openai rate limited"),
    ],
)
async def test_openai_errors_fail_pipeline_items_not_used(
    db_engine: AsyncEngine,
    session_factory: async_sessionmaker[AsyncSession],
    error_code: ErrorCode,
    summary: str,
) -> None:
    await _seed_candidates(session_factory)
    llm = _FailingLlm(LlmError(error_code, summary))
    service = DigestPipelineService(
        engine=db_engine,
        session_factory=session_factory,
        http_client=_FakeFeed(),  # type: ignore[arg-type]
        llm_client=llm,  # type: ignore[arg-type]
        telegram_client=MockTelegramClient(),
        settings=_settings(),
    )
    outcome = await service.run(trigger_type=TriggerType.MANUAL, app_version="0.1.0")

    assert outcome.run.status is PipelineRunStatus.FAILED
    assert outcome.run.error_code is error_code
    assert outcome.digest_id is None
    assert llm.calls >= 1
    assert outcome.candidate_ids

    async with transaction_scope(session_factory) as session:
        for candidate_id in outcome.candidate_ids:
            item = await NewsItemRepository(session).get(candidate_id)
            assert item is not None
            assert item.status is not NewsItemStatus.USED


@pytest.mark.asyncio
async def test_health_ready_unavailable_when_db_broken() -> None:
    class BrokenSession:
        async def scalar(self, *_args: object, **_kwargs: object) -> int:
            raise RuntimeError("db down")

    class BrokenBegin:
        async def __aenter__(self) -> BrokenSession:
            return BrokenSession()

        async def __aexit__(self, *_args: object) -> None:
            return None

    class BrokenFactory:
        def begin(self) -> BrokenBegin:
            return BrokenBegin()

    app = create_app(
        settings=_settings(),
        engine=object(),  # type: ignore[arg-type]
        session_factory=BrokenFactory(),  # type: ignore[arg-type]
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        ready = await client.get("/health/ready")
    assert ready.status_code == 503
    assert ready.json()["status"] == "unavailable"


@pytest.mark.asyncio
async def test_cancel_during_delivery_leaves_digest_unsent(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    digest = await _seed_digest(session_factory)

    class CancelTelegram:
        def __init__(self) -> None:
            self.calls = 0

        async def send_message(self, *, chat_id: str, text: str) -> TelegramSendResult:
            self.calls += 1
            raise asyncio.CancelledError

    telegram = CancelTelegram()
    service = DigestDeliveryService(
        session_factory=session_factory,
        telegram_client=telegram,  # type: ignore[arg-type]
        settings=_settings(TELEGRAM_ENABLED=True),
    )
    with pytest.raises(asyncio.CancelledError):
        await service.deliver(digest.id)

    async with transaction_scope(session_factory) as session:
        stored = await DigestRepository(session).get(digest.id)
    assert stored is not None
    assert stored.status is not DigestStatus.SENT
    assert telegram.calls == 1
