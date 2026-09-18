"""Integration tests for feed ingestion against PostgreSQL."""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.feed_http_types import FeedHttpError, FeedHttpResponse
from app.application.feed_ingestion import FeedIngestionService, SourceFetchLimits
from app.config import PROJECT_ROOT, Settings
from app.domain import (
    ErrorCode,
    FeedFetchStatus,
    PipelineRun,
    Source,
    TriggerType,
)
from app.infrastructure.db.repositories import (
    FeedFetchRepository,
    PipelineRunRepository,
    SourceRepository,
)
from app.infrastructure.db.session import transaction_scope

FIXTURES = PROJECT_ROOT / "tests" / "fixtures" / "feeds"


def _settings(**overrides: object) -> Settings:
    data: dict[str, object] = {
        "APP_MODE": "demo",
        "DATABASE_URL": "postgresql+asyncpg://news:news@localhost:5432/news",
        "FEEDS_CONFIG_PATH": Path("config/feeds.yaml"),
        "MAX_NEW_ITEMS_PER_RUN": 100,
        "MAX_ARTICLES_PER_SOURCE": 20,
        "FEED_FETCH_CONCURRENCY": 2,
        "ARTICLE_MAX_LENGTH": 12_000,
        "FEED_RESPONSE_MAX_BYTES": 2_097_152,
        "USER_AGENT": "TestPipeline/0.1 (https://example.com)",
    }
    data.update(overrides)
    return Settings(_env_file=None, **data)


@dataclass
class FakeFeedHttpClient:
    responses: dict[str, FeedHttpResponse | FeedHttpError]

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
        outcome = self.responses[feed_url]
        if isinstance(outcome, FeedHttpError):
            raise outcome
        return outcome


@pytest.mark.asyncio
async def test_ingest_inserts_items_and_records_success(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    body = (FIXTURES / "sample_rss.xml").read_bytes()
    source = Source(
        key="example-feed",
        name="Example",
        feed_url="https://example.com/feed.xml",
        allowed_host="example.com",
        category="artificial_intelligence",
    )
    run = PipelineRun(
        trigger_type=TriggerType.MANUAL,
        app_version="0.1.0",
        started_at=datetime(2026, 9, 15, 8, 0, tzinfo=UTC),
    )

    async with transaction_scope(session_factory) as session:
        await SourceRepository(session).add(source)
        await PipelineRunRepository(session).add(run)

    client = FakeFeedHttpClient(
        {
            source.feed_url: FeedHttpResponse(
                status_code=200,
                body=body,
                etag='"v1"',
                last_modified="Wed, 10 Sep 2025 08:00:00 GMT",
                duration_ms=12,
            )
        }
    )
    service = FeedIngestionService(
        session_factory=session_factory,
        http_client=client,
        settings=_settings(),
    )

    result = await service.ingest_sources(
        run_id=run.id,
        sources=(source,),
        limits_by_source_id={
            source.id: SourceFetchLimits(max_entries=20, read_timeout_seconds=15),
        },
    )

    assert result.feeds_succeeded == 1
    assert result.feeds_failed == 0
    assert result.items_inserted == 2

    async with transaction_scope(session_factory) as session:
        stored_source = await SourceRepository(session).get(source.id)
        fetches = await FeedFetchRepository(session).list_for_run(run.id)

    assert stored_source is not None
    assert stored_source.etag == '"v1"'
    assert stored_source.consecutive_failures == 0
    assert len(fetches) == 1
    assert fetches[0].status is FeedFetchStatus.SUCCESS


@pytest.mark.asyncio
async def test_ingest_not_modified_updates_source_without_items(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    source = Source(
        key="example-feed",
        name="Example",
        feed_url="https://example.com/feed.xml",
        allowed_host="example.com",
        category="artificial_intelligence",
        etag='"old"',
    )
    run = PipelineRun(
        trigger_type=TriggerType.MANUAL,
        app_version="0.1.0",
        started_at=datetime(2026, 9, 15, 8, 0, tzinfo=UTC),
    )

    async with transaction_scope(session_factory) as session:
        await SourceRepository(session).add(source)
        await PipelineRunRepository(session).add(run)

    client = FakeFeedHttpClient(
        {
            source.feed_url: FeedHttpResponse(
                status_code=304,
                body=None,
                etag='"old"',
                last_modified=None,
                duration_ms=5,
            )
        }
    )
    service = FeedIngestionService(
        session_factory=session_factory,
        http_client=client,
        settings=_settings(),
    )
    result = await service.ingest_sources(
        run_id=run.id,
        sources=(source,),
        limits_by_source_id={
            source.id: SourceFetchLimits(max_entries=20, read_timeout_seconds=15),
        },
    )

    assert result.items_inserted == 0
    assert result.sources[0].status is FeedFetchStatus.NOT_MODIFIED

    async with transaction_scope(session_factory) as session:
        stored = await SourceRepository(session).get(source.id)
        fetches = await FeedFetchRepository(session).list_for_run(run.id)

    assert stored is not None
    assert stored.last_checked_at is not None
    assert stored.consecutive_failures == 0
    assert fetches[0].http_status == 304


@pytest.mark.asyncio
async def test_ingest_partial_failure_does_not_block_other_source(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
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
    run = PipelineRun(
        trigger_type=TriggerType.MANUAL,
        app_version="0.1.0",
        started_at=datetime(2026, 9, 15, 8, 0, tzinfo=UTC),
    )

    async with transaction_scope(session_factory) as session:
        await SourceRepository(session).add(good)
        await SourceRepository(session).add(bad)
        await PipelineRunRepository(session).add(run)

    body = (FIXTURES / "sample_atom.xml").read_bytes()
    client = FakeFeedHttpClient(
        {
            good.feed_url: FeedHttpResponse(
                status_code=200,
                body=body,
                etag=None,
                last_modified=None,
                duration_ms=8,
            ),
            bad.feed_url: FeedHttpError(
                ErrorCode.FEED_TIMEOUT,
                "Feed request timed out.",
            ),
        }
    )
    service = FeedIngestionService(
        session_factory=session_factory,
        http_client=client,
        settings=_settings(),
    )
    result = await service.ingest_sources(
        run_id=run.id,
        sources=(good, bad),
        limits_by_source_id={
            good.id: SourceFetchLimits(max_entries=20, read_timeout_seconds=15),
            bad.id: SourceFetchLimits(max_entries=20, read_timeout_seconds=15),
        },
    )

    assert result.feeds_succeeded == 1
    assert result.feeds_failed == 1
    assert result.items_inserted == 1

    async with transaction_scope(session_factory) as session:
        bad_stored = await SourceRepository(session).get(bad.id)
        good_stored = await SourceRepository(session).get(good.id)

    assert bad_stored is not None
    assert bad_stored.consecutive_failures == 1
    assert good_stored is not None
    assert good_stored.consecutive_failures == 0


@pytest.mark.asyncio
async def test_ingest_duplicate_url_is_not_reinserted(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    source = Source(
        key="dup-feed",
        name="Dup",
        feed_url="https://example.com/dup.xml",
        allowed_host="example.com",
        category="artificial_intelligence",
    )
    run = PipelineRun(
        trigger_type=TriggerType.MANUAL,
        app_version="0.1.0",
        started_at=datetime(2026, 9, 15, 8, 0, tzinfo=UTC),
    )
    body = (FIXTURES / "duplicate_urls.xml").read_bytes()

    async with transaction_scope(session_factory) as session:
        await SourceRepository(session).add(source)
        await PipelineRunRepository(session).add(run)

    client = FakeFeedHttpClient(
        {
            source.feed_url: FeedHttpResponse(
                status_code=200,
                body=body,
                etag=None,
                last_modified=None,
                duration_ms=4,
            )
        }
    )
    service = FeedIngestionService(
        session_factory=session_factory,
        http_client=client,
        settings=_settings(),
    )

    first = await service.ingest_sources(
        run_id=run.id,
        sources=(source,),
        limits_by_source_id={
            source.id: SourceFetchLimits(max_entries=20, read_timeout_seconds=15),
        },
    )
    assert first.items_inserted == 1
    assert first.items_duplicate == 1

    run2 = PipelineRun(
        trigger_type=TriggerType.MANUAL,
        app_version="0.1.0",
        started_at=datetime(2026, 9, 15, 9, 0, tzinfo=UTC),
        id=uuid4(),
    )
    async with transaction_scope(session_factory) as session:
        await PipelineRunRepository(session).add(run2)

    second = await service.ingest_sources(
        run_id=run2.id,
        sources=(source,),
        limits_by_source_id={
            source.id: SourceFetchLimits(max_entries=20, read_timeout_seconds=15),
        },
    )
    assert second.items_inserted == 0
    assert second.items_duplicate == 2
