"""Integration tests for DigestPipelineService orchestration."""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.application.feed_http_types import FeedHttpError, FeedHttpResponse
from app.application.pipeline import DigestPipelineService
from app.config import PROJECT_ROOT, Settings
from app.domain import (
    ErrorCode,
    NewsItem,
    NewsItemStatus,
    PipelineRunStatus,
    Source,
    TriggerType,
)
from app.domain.hashing import content_hash, url_hash
from app.domain.text_sanitize import normalize_title
from app.infrastructure.db.advisory_lock import PipelineAdvisoryLock
from app.infrastructure.db.repositories import (
    NewsItemRepository,
    PipelineRunRepository,
    SourceRepository,
)
from app.infrastructure.db.session import transaction_scope
from app.infrastructure.llm.mock_client import MockDigestClient
from app.infrastructure.telegram.mock_client import MockTelegramClient

FIXTURES = PROJECT_ROOT / "tests" / "fixtures" / "feeds"
OPENAI_FIXTURES = PROJECT_ROOT / "demo" / "openai"


def _settings(**overrides: object) -> Settings:
    data: dict[str, object] = {
        "APP_MODE": "demo",
        "DATABASE_URL": "postgresql+asyncpg://news:news@localhost:5432/news",
        "FEEDS_CONFIG_PATH": Path("config/feeds.yaml"),
        "TOPIC_PROFILE_PATH": Path("config/topic_profile.yaml"),
        "MAX_NEW_ITEMS_PER_RUN": 100,
        "MAX_ARTICLES_PER_SOURCE": 20,
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
    }
    data.update(overrides)
    return Settings(_env_file=None, **data)


def _mock_llm() -> MockDigestClient:
    return MockDigestClient(
        happy_path=OPENAI_FIXTURES / "happy_path.json",
        invalid_candidate=OPENAI_FIXTURES / "invalid_candidate.json",
        repair_ok=OPENAI_FIXTURES / "repair_ok.json",
    )


@dataclass
class FakeFeedHttpClient:
    responses: dict[str, FeedHttpResponse | FeedHttpError]
    calls: int = 0

    async def fetch(
        self,
        *,
        feed_url: str,
        allowed_host: str,
        etag: str | None,
        last_modified: str | None,
        read_timeout_seconds: float,
        max_bytes: int,
    ) -> FeedHttpResponse:
        self.calls += 1
        outcome = self.responses[feed_url]
        if isinstance(outcome, FeedHttpError):
            raise outcome
        return outcome


def _pipeline(
    *,
    engine: AsyncEngine,
    session_factory: async_sessionmaker[AsyncSession],
    http_client: FakeFeedHttpClient,
    llm_client: MockDigestClient | None = None,
    telegram_client: MockTelegramClient | None = None,
    settings: Settings | None = None,
) -> DigestPipelineService:
    return DigestPipelineService(
        engine=engine,
        session_factory=session_factory,
        http_client=http_client,
        llm_client=llm_client or _mock_llm(),
        telegram_client=telegram_client or MockTelegramClient(),
        settings=settings or _settings(),
    )


@pytest.mark.asyncio
async def test_pipeline_skipped_locked_avoids_http(
    db_engine: AsyncEngine,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    holder = PipelineAdvisoryLock(db_engine)
    assert await holder.acquire() is True

    client = FakeFeedHttpClient(responses={})
    llm = _mock_llm()
    service = _pipeline(
        engine=db_engine,
        session_factory=session_factory,
        http_client=client,
        llm_client=llm,
        settings=_settings(),
    )

    try:
        outcome = await service.run(
            trigger_type=TriggerType.MANUAL,
            app_version="0.1.0",
        )
    finally:
        await holder.release()

    assert outcome.lock_acquired is False
    assert outcome.run.status is PipelineRunStatus.SKIPPED_LOCKED
    assert client.calls == 0
    assert llm.calls == 0


@pytest.mark.asyncio
async def test_pipeline_selects_candidates_on_success(
    db_engine: AsyncEngine,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    now = datetime.now(UTC)
    stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    sources = (
        Source(
            key="feed-a",
            name="Feed A",
            feed_url="https://example.com/a.xml",
            allowed_host="example.com",
            category="artificial_intelligence",
        ),
        Source(
            key="feed-b",
            name="Feed B",
            feed_url="https://example.com/b.xml",
            allowed_host="example.com",
            category="artificial_intelligence",
        ),
        Source(
            key="feed-c",
            name="Feed C",
            feed_url="https://example.com/c.xml",
            allowed_host="example.com",
            category="artificial_intelligence",
        ),
    )

    async with transaction_scope(session_factory) as session:
        repo = SourceRepository(session)
        for source in sources:
            await repo.add(source)

    bodies = {
        sources[0].feed_url: (
            '<?xml version="1.0"?>'
            '<rss version="2.0"><channel><title>A</title>'
            "<item><guid>a-1</guid>"
            "<title>AI automation product update one for teams</title>"
            "<link>https://example.com/a-1</link>"
            "<description>"
            "A long enough summary about AI automation and product delivery for item one."
            f"</description><pubDate>{stamp}</pubDate></item>"
            "<item><guid>a-2</guid>"
            "<title>AI automation product update two for teams</title>"
            "<link>https://example.com/a-2</link>"
            "<description>"
            "A long enough summary about AI automation and product delivery for item two."
            f"</description><pubDate>{stamp}</pubDate></item>"
            "</channel></rss>"
        ).encode(),
        sources[1].feed_url: (
            '<?xml version="1.0"?>'
            '<feed xmlns="http://www.w3.org/2005/Atom"><title>B</title>'
            "<entry><id>b-1</id>"
            "<title>AI developer tools release for product teams</title>"
            '<link href="https://example.com/b-1"/>'
            "<summary>"
            "A long enough summary about AI automation and product delivery for item three."
            f"</summary><updated>{stamp}</updated></entry></feed>"
        ).encode(),
        sources[2].feed_url: (
            '<?xml version="1.0"?>'
            '<rss version="2.0"><channel><title>C</title>'
            "<item><guid>c-1</guid>"
            "<title>AI product automation note for operators</title>"
            "<link>https://example.com/c-1</link>"
            "<description>"
            "A long enough summary about AI automation and product delivery for item four."
            f"</description><pubDate>{stamp}</pubDate></item>"
            "</channel></rss>"
        ).encode(),
    }
    client = FakeFeedHttpClient(
        {
            url: FeedHttpResponse(
                status_code=200,
                body=body,
                etag=None,
                last_modified=None,
                duration_ms=5,
            )
            for url, body in bodies.items()
        }
    )
    service = _pipeline(
        engine=db_engine,
        session_factory=session_factory,
        http_client=client,
        llm_client=_mock_llm(),
        settings=_settings(),
    )
    outcome = await service.run(trigger_type=TriggerType.MANUAL, app_version="0.1.0")

    assert outcome.lock_acquired is True
    assert outcome.run.status is PipelineRunStatus.SUCCESS
    assert outcome.run.selected_count is not None
    assert outcome.run.selected_count >= 3
    assert outcome.digest_id is not None

    async with transaction_scope(session_factory) as session:
        stored = await PipelineRunRepository(session).get(outcome.run.id)

    assert stored is not None
    assert stored.status is PipelineRunStatus.SUCCESS


@pytest.mark.asyncio
async def test_pipeline_partial_success_with_feed_failure(
    db_engine: AsyncEngine,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Seed enough collected AI items directly, then run with one failing feed.
    good = Source(
        key="good-feed",
        name="Good",
        feed_url="https://example.com/good.xml",
        allowed_host="example.com",
        category="artificial_intelligence",
    )
    bad = Source(
        key="bad-feed",
        name="Bad",
        feed_url="https://example.com/bad.xml",
        allowed_host="example.com",
        category="artificial_intelligence",
    )

    now = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)
    async with transaction_scope(session_factory) as session:
        await SourceRepository(session).add(good)
        await SourceRepository(session).add(bad)
        news = NewsItemRepository(session)
        for index in range(3):
            title = f"AI automation product update number {index} for teams"
            summary = (
                "A long enough summary about AI automation and product delivery "
                f"practices for item {index}."
            )
            url = f"https://example.com/seed-{index}"
            normalized = normalize_title(title)
            await news.add_if_new(
                NewsItem(
                    source_id=good.id,
                    original_url=url,
                    canonical_url=url,
                    url_hash=url_hash(url),
                    title=title,
                    normalized_title=normalized,
                    sanitized_summary=summary,
                    content_hash=content_hash(normalized, summary),
                    published_at=now,
                    collected_at=now,
                )
            )

    body = (FIXTURES / "sample_atom.xml").read_bytes()
    client = FakeFeedHttpClient(
        {
            good.feed_url: FeedHttpResponse(
                status_code=200,
                body=body,
                etag=None,
                last_modified=None,
                duration_ms=3,
            ),
            bad.feed_url: FeedHttpError(ErrorCode.FEED_TIMEOUT, "Feed request timed out."),
        }
    )
    service = _pipeline(
        engine=db_engine,
        session_factory=session_factory,
        http_client=client,
        llm_client=_mock_llm(),
        settings=_settings(),
    )
    outcome = await service.run(trigger_type=TriggerType.MANUAL, app_version="0.1.0")

    assert outcome.ingest is not None
    assert outcome.ingest.feeds_failed == 1
    assert len(outcome.candidate_ids) >= 3
    assert outcome.run.status is PipelineRunStatus.PARTIAL_SUCCESS
    assert outcome.digest_id is not None

    async with transaction_scope(session_factory) as session:
        for candidate_id in outcome.candidate_ids[:3]:
            item = await NewsItemRepository(session).get(candidate_id)
            assert item is not None
            assert item.status is NewsItemStatus.USED


@pytest.mark.asyncio
async def test_pipeline_invalid_llm_output_fails_without_used(
    db_engine: AsyncEngine,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    source = Source(
        key="fail-llm-feed",
        name="Fail LLM",
        feed_url="https://example.com/fail-llm.xml",
        allowed_host="example.com",
        category="artificial_intelligence",
    )
    now = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)
    async with transaction_scope(session_factory) as session:
        await SourceRepository(session).add(source)
        news = NewsItemRepository(session)
        for index in range(3):
            title = f"AI automation product update number {index} for teams"
            summary = (
                "A long enough summary about AI automation and product delivery "
                f"practices for item {index}."
            )
            url = f"https://example.com/fail-llm-{index}"
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
                    published_at=now,
                    collected_at=now,
                )
            )

    bad = OPENAI_FIXTURES / "invalid_candidate.json"
    llm = MockDigestClient(
        happy_path=bad,
        invalid_candidate=bad,
        repair_ok=bad,
    )
    client = FakeFeedHttpClient(
        {
            source.feed_url: FeedHttpResponse(
                status_code=304,
                body=b"",
                etag=None,
                last_modified=None,
                duration_ms=1,
            )
        }
    )
    service = _pipeline(
        engine=db_engine,
        session_factory=session_factory,
        http_client=client,
        llm_client=llm,
        settings=_settings(),
    )
    outcome = await service.run(trigger_type=TriggerType.MANUAL, app_version="0.1.0")

    assert outcome.run.status is PipelineRunStatus.FAILED
    assert outcome.run.error_code is ErrorCode.OUTPUT_POST_VALIDATION_FAILED
    assert outcome.digest_id is None
    assert llm.calls == 2

    async with transaction_scope(session_factory) as session:
        for candidate_id in outcome.candidate_ids:
            item = await NewsItemRepository(session).get(candidate_id)
            assert item is not None
            assert item.status is NewsItemStatus.CANDIDATE


@pytest.mark.asyncio
async def test_pipeline_creates_digest_with_usage(
    db_engine: AsyncEngine,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    source = Source(
        key="digest-happy-feed",
        name="Digest Happy",
        feed_url="https://example.com/digest-happy.xml",
        allowed_host="example.com",
        category="artificial_intelligence",
    )
    now = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)
    async with transaction_scope(session_factory) as session:
        await SourceRepository(session).add(source)
        news = NewsItemRepository(session)
        for index in range(3):
            title = f"AI automation product update number {index} for teams"
            summary = (
                "A long enough summary about AI automation and product delivery "
                f"practices for item {index}."
            )
            url = f"https://example.com/digest-happy-{index}"
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
                    published_at=now,
                    collected_at=now,
                )
            )

    llm = _mock_llm()
    client = FakeFeedHttpClient(
        {
            source.feed_url: FeedHttpResponse(
                status_code=304,
                body=b"",
                etag=None,
                last_modified=None,
                duration_ms=1,
            )
        }
    )
    service = _pipeline(
        engine=db_engine,
        session_factory=session_factory,
        http_client=client,
        llm_client=llm,
        settings=_settings(),
    )
    outcome = await service.run(trigger_type=TriggerType.MANUAL, app_version="0.1.0")

    assert outcome.run.status is PipelineRunStatus.SUCCESS
    assert outcome.digest_id is not None
    assert llm.calls == 1

    async with transaction_scope(session_factory) as session:
        from app.infrastructure.db.repositories import DigestRepository

        digest = await DigestRepository(session).get(outcome.digest_id)
        assert digest is not None
        assert digest.provider_response_id == "mock-happy-1"
        assert digest.input_tokens == 400
        assert digest.output_tokens == 220
        assert digest.prompt_version
        for candidate_id in outcome.candidate_ids[:3]:
            item = await NewsItemRepository(session).get(candidate_id)
            assert item is not None
            assert item.status is NewsItemStatus.USED


@pytest.mark.asyncio
async def test_pipeline_no_content_when_below_minimum(
    db_engine: AsyncEngine,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    source = Source(
        key="sparse-feed",
        name="Sparse",
        feed_url="https://example.com/sparse.xml",
        allowed_host="example.com",
        category="artificial_intelligence",
    )
    async with transaction_scope(session_factory) as session:
        await SourceRepository(session).add(source)

    client = FakeFeedHttpClient(
        {
            source.feed_url: FeedHttpResponse(
                status_code=200,
                body=(FIXTURES / "sample_atom.xml").read_bytes(),
                etag=None,
                last_modified=None,
                duration_ms=2,
            )
        }
    )
    llm = _mock_llm()
    service = _pipeline(
        engine=db_engine,
        session_factory=session_factory,
        http_client=client,
        llm_client=llm,
        settings=_settings(MIN_DIGEST_ITEMS=3),
    )
    outcome = await service.run(trigger_type=TriggerType.MANUAL, app_version="0.1.0")

    assert outcome.run.status is PipelineRunStatus.NO_CONTENT
    assert len(outcome.candidate_ids) < 3
    assert llm.calls == 0
    assert outcome.digest_id is None


async def _seed_three_candidates(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    key: str,
) -> Source:
    source = Source(
        key=key,
        name=key,
        feed_url=f"https://example.com/{key}.xml",
        allowed_host="example.com",
        category="artificial_intelligence",
    )
    now = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)
    async with transaction_scope(session_factory) as session:
        await SourceRepository(session).add(source)
        news = NewsItemRepository(session)
        for index in range(3):
            title = f"AI automation product update number {index} for teams"
            summary = (
                "A long enough summary about AI automation and product delivery "
                f"practices for item {index}."
            )
            url = f"https://example.com/{key}-{index}"
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
                    published_at=now,
                    collected_at=now,
                )
            )
    return source


@pytest.mark.asyncio
async def test_pipeline_delivers_digest_when_telegram_enabled(
    db_engine: AsyncEngine,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    source = await _seed_three_candidates(session_factory, key="tg-enabled")
    telegram = MockTelegramClient()
    client = FakeFeedHttpClient(
        {
            source.feed_url: FeedHttpResponse(
                status_code=304,
                body=b"",
                etag=None,
                last_modified=None,
                duration_ms=1,
            )
        }
    )
    service = _pipeline(
        engine=db_engine,
        session_factory=session_factory,
        http_client=client,
        telegram_client=telegram,
        settings=_settings(TELEGRAM_ENABLED=True),
    )
    outcome = await service.run(trigger_type=TriggerType.MANUAL, app_version="0.1.0")

    assert outcome.run.status is PipelineRunStatus.SUCCESS
    assert outcome.digest_id is not None
    assert outcome.delivery is not None
    assert outcome.delivery.status.value == "sent"
    assert len(telegram.calls) >= 1

    async with transaction_scope(session_factory) as session:
        from app.domain import DigestStatus
        from app.infrastructure.db.repositories import DigestRepository

        digest = await DigestRepository(session).get(outcome.digest_id)
        assert digest is not None
        assert digest.status is DigestStatus.SENT


@pytest.mark.asyncio
async def test_pipeline_skips_delivery_when_telegram_disabled(
    db_engine: AsyncEngine,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    source = await _seed_three_candidates(session_factory, key="tg-disabled")
    telegram = MockTelegramClient()
    client = FakeFeedHttpClient(
        {
            source.feed_url: FeedHttpResponse(
                status_code=304,
                body=b"",
                etag=None,
                last_modified=None,
                duration_ms=1,
            )
        }
    )
    service = _pipeline(
        engine=db_engine,
        session_factory=session_factory,
        http_client=client,
        telegram_client=telegram,
        settings=_settings(TELEGRAM_ENABLED=False),
    )
    outcome = await service.run(trigger_type=TriggerType.MANUAL, app_version="0.1.0")

    assert outcome.run.status is PipelineRunStatus.SUCCESS
    assert outcome.delivery is None
    assert telegram.calls == []

    async with transaction_scope(session_factory) as session:
        from app.domain import DigestStatus
        from app.infrastructure.db.repositories import DigestRepository

        digest = await DigestRepository(session).get(outcome.digest_id)
        assert digest is not None
        assert digest.status is DigestStatus.GENERATED


@pytest.mark.asyncio
async def test_pipeline_delivery_failure_keeps_run_success_and_items_used(
    db_engine: AsyncEngine,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    source = await _seed_three_candidates(session_factory, key="tg-fail")
    telegram = MockTelegramClient()
    telegram.force_permanent_failure()
    client = FakeFeedHttpClient(
        {
            source.feed_url: FeedHttpResponse(
                status_code=304,
                body=b"",
                etag=None,
                last_modified=None,
                duration_ms=1,
            )
        }
    )
    service = _pipeline(
        engine=db_engine,
        session_factory=session_factory,
        http_client=client,
        telegram_client=telegram,
        settings=_settings(TELEGRAM_ENABLED=True),
    )
    outcome = await service.run(trigger_type=TriggerType.MANUAL, app_version="0.1.0")

    assert outcome.run.status is PipelineRunStatus.SUCCESS
    assert outcome.delivery is not None
    assert outcome.delivery.status.value == "failed"

    async with transaction_scope(session_factory) as session:
        from app.domain import DigestStatus
        from app.infrastructure.db.repositories import DigestRepository

        digest = await DigestRepository(session).get(outcome.digest_id)
        assert digest is not None
        assert digest.status is DigestStatus.FAILED
        for candidate_id in outcome.candidate_ids[:3]:
            item = await NewsItemRepository(session).get(candidate_id)
            assert item is not None
            assert item.status is NewsItemStatus.USED
