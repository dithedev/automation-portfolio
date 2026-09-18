"""Collect, normalize, and persist news items from trusted feeds."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.feed_http_types import FeedHttpError, FeedHttpResponse
from app.application.ports import FeedHttpClient
from app.config import Settings
from app.domain import (
    ErrorCode,
    FeedFetch,
    FeedFetchStatus,
    Source,
)
from app.domain.validators import utc_now
from app.infrastructure.db.repositories import (
    FeedFetchRepository,
    NewsItemRepository,
    SourceRepository,
)
from app.infrastructure.db.session import transaction_scope
from app.infrastructure.feeds.normalize import news_item_from_entry
from app.infrastructure.feeds.parser import FeedParseError, parse_feed_bytes
from app.observability import log_event
from app.texts.feeds import FEED_HTTP_CONNECTION_FAILED


@dataclass(frozen=True, slots=True, kw_only=True)
class SourceFetchLimits:
    """Per-source fetch caps resolved from settings and YAML."""

    max_entries: int
    read_timeout_seconds: float


@dataclass(frozen=True, slots=True, kw_only=True)
class IngestSourceResult:
    """Persisted outcome for one source inside an ingest run."""

    source_id: UUID
    status: FeedFetchStatus
    items_fetched: int
    items_inserted: int
    items_duplicate: int
    items_skipped: int
    error_code: ErrorCode | None = None
    error_summary: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class IngestRunResult:
    """Aggregate counters for one multi-source ingest pass."""

    feeds_succeeded: int
    feeds_failed: int
    items_fetched: int
    items_inserted: int
    items_duplicate: int
    sources: tuple[IngestSourceResult, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class _FetchedSource:
    source: Source
    limits: SourceFetchLimits
    started_at: datetime
    finished_at: datetime
    response: FeedHttpResponse | None
    error: FeedHttpError | None


class FeedIngestionService:
    """Fetch feeds outside DB transactions, then persist short per-source txns."""

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        http_client: FeedHttpClient,
        settings: Settings,
    ) -> None:
        self._session_factory = session_factory
        self._http_client = http_client
        self._settings = settings

    async def ingest_sources(
        self,
        *,
        run_id: UUID,
        sources: tuple[Source, ...],
        limits_by_source_id: dict[UUID, SourceFetchLimits],
    ) -> IngestRunResult:
        enabled = tuple(source for source in sources if source.enabled)
        semaphore = asyncio.Semaphore(self._settings.feed_fetch_concurrency)

        async def fetch_one(source: Source) -> _FetchedSource:
            limits = limits_by_source_id[source.id]
            started_at = utc_now()
            async with semaphore:
                try:
                    response = await self._http_client.fetch(
                        feed_url=source.feed_url,
                        allowed_host=source.allowed_host,
                        etag=source.etag,
                        last_modified=source.last_modified,
                        read_timeout_seconds=limits.read_timeout_seconds,
                        max_bytes=self._settings.feed_response_max_bytes,
                    )
                    return _FetchedSource(
                        source=source,
                        limits=limits,
                        started_at=started_at,
                        finished_at=utc_now(),
                        response=response,
                        error=None,
                    )
                except FeedHttpError as error:
                    return _FetchedSource(
                        source=source,
                        limits=limits,
                        started_at=started_at,
                        finished_at=utc_now(),
                        response=None,
                        error=error,
                    )
                except Exception:
                    return _FetchedSource(
                        source=source,
                        limits=limits,
                        started_at=started_at,
                        finished_at=utc_now(),
                        response=None,
                        error=FeedHttpError(
                            ErrorCode.UNEXPECTED_PIPELINE_FAILURE,
                            FEED_HTTP_CONNECTION_FAILED,
                        ),
                    )

        fetched = await asyncio.gather(*(fetch_one(source) for source in enabled))

        remaining_inserts = self._settings.max_new_items_per_run
        source_results: list[IngestSourceResult] = []
        feeds_succeeded = 0
        feeds_failed = 0
        items_fetched = 0
        items_inserted = 0
        items_duplicate = 0

        for item in fetched:
            result, remaining_inserts = await self._persist_fetched(
                run_id=run_id,
                fetched=item,
                remaining_inserts=remaining_inserts,
            )
            source_results.append(result)
            if result.status is FeedFetchStatus.FAILED:
                feeds_failed += 1
            else:
                feeds_succeeded += 1
            items_fetched += result.items_fetched
            items_inserted += result.items_inserted
            items_duplicate += result.items_duplicate

        return IngestRunResult(
            feeds_succeeded=feeds_succeeded,
            feeds_failed=feeds_failed,
            items_fetched=items_fetched,
            items_inserted=items_inserted,
            items_duplicate=items_duplicate,
            sources=tuple(source_results),
        )

    async def _persist_fetched(
        self,
        *,
        run_id: UUID,
        fetched: _FetchedSource,
        remaining_inserts: int,
    ) -> tuple[IngestSourceResult, int]:
        source = fetched.source
        duration_ms = max(
            0,
            int((fetched.finished_at - fetched.started_at).total_seconds() * 1000),
        )
        if fetched.response is not None:
            duration_ms = max(duration_ms, fetched.response.duration_ms)

        if fetched.error is not None:
            async with transaction_scope(self._session_factory) as session:
                source.record_fetch_failure(checked_at=fetched.finished_at)
                await SourceRepository(session).save(source)
                await FeedFetchRepository(session).add(
                    FeedFetch(
                        run_id=run_id,
                        source_id=source.id,
                        status=FeedFetchStatus.FAILED,
                        started_at=fetched.started_at,
                        finished_at=fetched.finished_at,
                        http_status=None,
                        entries_count=0,
                        duration_ms=duration_ms,
                        error_code=fetched.error.error_code,
                        error_summary=fetched.error.summary,
                    )
                )
            log_event(
                "feed.fetch_failed",
                source_id=source.id,
                error_code=fetched.error.error_code.value,
            )
            return (
                IngestSourceResult(
                    source_id=source.id,
                    status=FeedFetchStatus.FAILED,
                    items_fetched=0,
                    items_inserted=0,
                    items_duplicate=0,
                    items_skipped=0,
                    error_code=fetched.error.error_code,
                    error_summary=fetched.error.summary,
                ),
                remaining_inserts,
            )

        assert fetched.response is not None
        response = fetched.response

        if response.status_code == 304:
            async with transaction_scope(self._session_factory) as session:
                source.record_fetch_success(
                    checked_at=fetched.finished_at,
                    etag=response.etag if response.etag is not None else source.etag,
                    last_modified=(
                        response.last_modified
                        if response.last_modified is not None
                        else source.last_modified
                    ),
                )
                await SourceRepository(session).save(source)
                await FeedFetchRepository(session).add(
                    FeedFetch(
                        run_id=run_id,
                        source_id=source.id,
                        status=FeedFetchStatus.NOT_MODIFIED,
                        started_at=fetched.started_at,
                        finished_at=fetched.finished_at,
                        http_status=304,
                        entries_count=0,
                        duration_ms=duration_ms,
                    )
                )
            log_event("feed.not_modified", source_id=source.id)
            return (
                IngestSourceResult(
                    source_id=source.id,
                    status=FeedFetchStatus.NOT_MODIFIED,
                    items_fetched=0,
                    items_inserted=0,
                    items_duplicate=0,
                    items_skipped=0,
                ),
                remaining_inserts,
            )

        body = response.body or b""
        try:
            entries = parse_feed_bytes(body, max_entries=fetched.limits.max_entries)
        except FeedParseError as error:
            async with transaction_scope(self._session_factory) as session:
                source.record_fetch_failure(checked_at=fetched.finished_at)
                await SourceRepository(session).save(source)
                await FeedFetchRepository(session).add(
                    FeedFetch(
                        run_id=run_id,
                        source_id=source.id,
                        status=FeedFetchStatus.FAILED,
                        started_at=fetched.started_at,
                        finished_at=fetched.finished_at,
                        http_status=response.status_code,
                        entries_count=0,
                        duration_ms=duration_ms,
                        error_code=error.error_code,
                        error_summary=error.summary,
                    )
                )
            log_event(
                "feed.fetch_failed",
                source_id=source.id,
                error_code=error.error_code.value,
            )
            return (
                IngestSourceResult(
                    source_id=source.id,
                    status=FeedFetchStatus.FAILED,
                    items_fetched=0,
                    items_inserted=0,
                    items_duplicate=0,
                    items_skipped=0,
                    error_code=error.error_code,
                    error_summary=error.summary,
                ),
                remaining_inserts,
            )

        inserted = 0
        duplicate = 0
        skipped = 0
        fetched_count = 0

        async with transaction_scope(self._session_factory) as session:
            news_repo = NewsItemRepository(session)
            for entry in entries:
                normalized = news_item_from_entry(
                    entry,
                    source_id=source.id,
                    collected_at=fetched.finished_at,
                    article_max_length=self._settings.article_max_length,
                    allowed_host=source.allowed_host,
                )
                if normalized.skipped or normalized.item is None:
                    skipped += 1
                    continue

                fetched_count += 1
                if remaining_inserts <= 0:
                    # Still count as fetched for observability; stop inserting.
                    continue

                result = await news_repo.add_if_new(normalized.item)
                if result.inserted:
                    inserted += 1
                    remaining_inserts -= 1
                else:
                    duplicate += 1

            source.record_fetch_success(
                checked_at=fetched.finished_at,
                etag=response.etag if response.etag is not None else source.etag,
                last_modified=(
                    response.last_modified
                    if response.last_modified is not None
                    else source.last_modified
                ),
            )
            await SourceRepository(session).save(source)
            await FeedFetchRepository(session).add(
                FeedFetch(
                    run_id=run_id,
                    source_id=source.id,
                    status=FeedFetchStatus.SUCCESS,
                    started_at=fetched.started_at,
                    finished_at=fetched.finished_at,
                    http_status=response.status_code,
                    entries_count=fetched_count,
                    duration_ms=duration_ms,
                )
            )

        log_event(
            "feed.fetch_succeeded",
            source_id=source.id,
            http_status=response.status_code,
            entries_count=fetched_count,
        )
        log_event(
            "items.persisted",
            source_id=source.id,
            inserted=inserted,
            duplicate=duplicate,
            skipped=skipped,
        )
        return (
            IngestSourceResult(
                source_id=source.id,
                status=FeedFetchStatus.SUCCESS,
                items_fetched=fetched_count,
                items_inserted=inserted,
                items_duplicate=duplicate,
                items_skipped=skipped,
            ),
            remaining_inserts,
        )
