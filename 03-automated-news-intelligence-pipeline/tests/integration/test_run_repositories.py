"""PostgreSQL integration checks for run and fetch persistence."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain import (
    ErrorCode,
    FeedFetch,
    FeedFetchStatus,
    PipelineRun,
    PipelineRunStatus,
    Source,
    TriggerType,
)
from app.infrastructure.db.repositories import (
    FeedFetchRepository,
    PipelineRunRepository,
    SourceRepository,
)
from app.infrastructure.db.session import transaction_scope
from app.texts.db import (
    RUN_IDENTITY_MISMATCH,
    RUN_NOT_FOUND,
    RUN_TERMINAL_UPDATE_FORBIDDEN,
)

STARTED_AT = datetime(2026, 9, 14, 8, 0, tzinfo=UTC)


def make_run() -> PipelineRun:
    """Create a running pipeline record with a deterministic start time."""
    return PipelineRun(
        trigger_type=TriggerType.MANUAL,
        app_version="0.1.0",
        started_at=STARTED_AT,
    )


def make_source() -> Source:
    """Create a valid source for fetch foreign-key checks."""
    return Source(
        key="example-feed",
        name="Example Feed",
        feed_url="https://example.com/feed.xml",
        allowed_host="example.com",
        category="artificial_intelligence",
    )


async def test_run_counters_and_completion_round_trip(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Persist running counters followed by a completed outcome."""
    run = make_run()

    async with transaction_scope(session_factory) as session:
        assert await PipelineRunRepository(session).add(run) == run

    run.record_feed_attempt()
    run.record_feed_success()
    run.record_items_fetched(2)
    run.record_item_inserted()
    run.record_item_duplicate()
    run.record_candidates(1)
    run.record_selected(1)

    async with transaction_scope(session_factory) as session:
        assert await PipelineRunRepository(session).save(run) == run

    run.complete(
        PipelineRunStatus.SUCCESS,
        finished_at=STARTED_AT + timedelta(seconds=2),
    )

    async with transaction_scope(session_factory) as session:
        assert await PipelineRunRepository(session).save(run) == run

    async with transaction_scope(session_factory) as session:
        stored = await PipelineRunRepository(session).get(run.id)
        assert stored == run
        assert stored is not None
        assert stored.duration_ms == 2000


async def test_failed_run_preserves_error_metadata(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Restore failure code and summary after completion."""
    run = make_run()

    async with transaction_scope(session_factory) as session:
        await PipelineRunRepository(session).add(run)

    run.complete(
        PipelineRunStatus.FAILED,
        finished_at=STARTED_AT + timedelta(seconds=1),
        error_code=ErrorCode.OPENAI_TIMEOUT,
        error_summary="OpenAI request timed out.",
    )

    async with transaction_scope(session_factory) as session:
        await PipelineRunRepository(session).save(run)

    async with transaction_scope(session_factory) as session:
        assert await PipelineRunRepository(session).get(run.id) == run


async def test_terminal_run_cannot_be_rewritten(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Allow identical terminal saves and reject changed completed results."""
    run = make_run()
    run.complete(
        PipelineRunStatus.NO_CONTENT,
        finished_at=STARTED_AT + timedelta(seconds=1),
    )

    async with transaction_scope(session_factory) as session:
        await PipelineRunRepository(session).add(run)

    async with transaction_scope(session_factory) as session:
        assert await PipelineRunRepository(session).save(run) == run

    changed = replace(run, feeds_total=1)

    with pytest.raises(ValueError) as error:
        async with transaction_scope(session_factory) as session:
            await PipelineRunRepository(session).save(changed)

    assert str(error.value) == RUN_TERMINAL_UPDATE_FORBIDDEN

    async with transaction_scope(session_factory) as session:
        assert await PipelineRunRepository(session).get(run.id) == run


async def test_run_identity_cannot_be_replaced(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Reject a different trigger type for an existing run."""
    run = make_run()

    async with transaction_scope(session_factory) as session:
        await PipelineRunRepository(session).add(run)

    changed = replace(run, trigger_type=TriggerType.SCHEDULED)

    with pytest.raises(ValueError) as error:
        async with transaction_scope(session_factory) as session:
            await PipelineRunRepository(session).save(changed)

    assert str(error.value) == RUN_IDENTITY_MISMATCH


async def test_missing_run_reads_and_update(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Return None for missing reads and reject updating a missing run."""
    async with transaction_scope(session_factory) as session:
        repository = PipelineRunRepository(session)
        assert await repository.get(uuid4()) is None
        assert await repository.get_latest() is None

    with pytest.raises(LookupError) as error:
        async with transaction_scope(session_factory) as session:
            await PipelineRunRepository(session).save(make_run())

    assert str(error.value) == RUN_NOT_FOUND


async def test_latest_run_uses_start_time(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Choose the latest started run regardless of insertion order."""
    older = make_run()
    newer = replace(older, id=uuid4(), started_at=STARTED_AT + timedelta(seconds=1))

    async with transaction_scope(session_factory) as session:
        repository = PipelineRunRepository(session)
        await repository.add(newer)
        await repository.add(older)

    async with transaction_scope(session_factory) as session:
        assert await PipelineRunRepository(session).get_latest() == newer


@pytest.mark.parametrize(
    "status",
    [
        FeedFetchStatus.SUCCESS,
        FeedFetchStatus.NOT_MODIFIED,
        FeedFetchStatus.FAILED,
    ],
)
async def test_fetch_result_round_trip(
    session_factory: async_sessionmaker[AsyncSession],
    status: FeedFetchStatus,
) -> None:
    """Restore success, HTTP 304, and failure outcomes without losing fields."""
    run = make_run()
    source = make_source()
    fetch = FeedFetch(
        run_id=run.id,
        source_id=source.id,
        status=status,
        started_at=STARTED_AT,
        finished_at=STARTED_AT + timedelta(seconds=1),
        duration_ms=1000,
        http_status=(
            200
            if status is FeedFetchStatus.SUCCESS
            else 304
            if status is FeedFetchStatus.NOT_MODIFIED
            else None
        ),
        entries_count=2 if status is FeedFetchStatus.SUCCESS else 0,
        error_code=ErrorCode.FEED_TIMEOUT if status is FeedFetchStatus.FAILED else None,
        error_summary="Feed request timed out." if status is FeedFetchStatus.FAILED else None,
    )

    async with transaction_scope(session_factory) as session:
        await PipelineRunRepository(session).add(run)
        await SourceRepository(session).add(source)
        assert await FeedFetchRepository(session).add(fetch) == fetch

    async with transaction_scope(session_factory) as session:
        repository = FeedFetchRepository(session)
        assert await repository.get(fetch.id) == fetch
        assert await repository.list_for_run(run.id) == (fetch,)
        assert await repository.list_for_run(uuid4()) == ()
        assert await repository.get(uuid4()) is None


async def test_duplicate_fetch_pair_is_rejected(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Reject a second result for the same source within one run."""
    run = make_run()
    source = make_source()
    fetch = FeedFetch(
        run_id=run.id,
        source_id=source.id,
        status=FeedFetchStatus.NOT_MODIFIED,
        http_status=304,
        started_at=STARTED_AT,
        finished_at=STARTED_AT,
    )

    async with transaction_scope(session_factory) as session:
        await PipelineRunRepository(session).add(run)
        await SourceRepository(session).add(source)
        await FeedFetchRepository(session).add(fetch)

    with pytest.raises(IntegrityError):
        async with transaction_scope(session_factory) as session:
            await FeedFetchRepository(session).add(replace(fetch, id=uuid4()))

    async with transaction_scope(session_factory) as session:
        assert await FeedFetchRepository(session).list_for_run(run.id) == (fetch,)


async def test_fetch_requires_existing_parents(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Reject a result whose run and source do not exist."""
    fetch = FeedFetch(
        run_id=uuid4(),
        source_id=uuid4(),
        status=FeedFetchStatus.NOT_MODIFIED,
        http_status=304,
        started_at=STARTED_AT,
        finished_at=STARTED_AT,
    )

    with pytest.raises(IntegrityError):
        async with transaction_scope(session_factory) as session:
            await FeedFetchRepository(session).add(fetch)


async def test_run_and_fetch_insert_roll_back_together(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Roll back all flushed records when their shared transaction fails."""
    run = make_run()
    source = make_source()
    fetch = FeedFetch(
        run_id=run.id,
        source_id=source.id,
        status=FeedFetchStatus.NOT_MODIFIED,
        http_status=304,
        started_at=STARTED_AT,
        finished_at=STARTED_AT,
    )

    with pytest.raises(RuntimeError):
        async with transaction_scope(session_factory) as session:
            await PipelineRunRepository(session).add(run)
            await SourceRepository(session).add(source)
            await FeedFetchRepository(session).add(fetch)
            raise RuntimeError

    async with transaction_scope(session_factory) as session:
        assert await PipelineRunRepository(session).get(run.id) is None
        assert await SourceRepository(session).get(source.id) is None
        assert await FeedFetchRepository(session).get(fetch.id) is None
