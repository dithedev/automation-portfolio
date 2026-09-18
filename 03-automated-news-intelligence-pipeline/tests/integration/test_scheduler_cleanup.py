"""Integration tests for cleanup and scheduler registration."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.application.cleanup import cleanup_operational_records
from app.config import Settings
from app.domain import (
    FeedFetch,
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
from app.runtime import build_pipeline_runtime
from app.scheduler import JOB_ID, build_scheduler


def _settings(**overrides: object) -> Settings:
    data: dict[str, object] = {
        "APP_MODE": "demo",
        "DATABASE_URL": "postgresql+asyncpg://news:news@localhost:5432/news",
        "TELEGRAM_ENABLED": False,
        "SCHEDULER_ENABLED": True,
        "DIGEST_SCHEDULE_HOUR": 9,
        "DIGEST_SCHEDULE_MINUTE": 30,
        "SCHEDULER_TIMEZONE": "UTC",
        "SCHEDULER_MISFIRE_GRACE_SECONDS": 120,
    }
    data.update(overrides)
    return Settings(_env_file=None, **data)


@pytest.mark.asyncio
async def test_cleanup_dry_run_counts_old_rows(
    db_engine: AsyncEngine,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    run = PipelineRun(trigger_type=TriggerType.MANUAL, app_version="0.1.0")
    source = Source(
        key=f"cleanup-{uuid4().hex[:8]}",
        name="Cleanup",
        feed_url="https://example.com/cleanup.xml",
        allowed_host="example.com",
        category="artificial_intelligence",
    )
    old = datetime.now(UTC) - timedelta(days=40)
    async with transaction_scope(session_factory) as session:
        await PipelineRunRepository(session).add(run)
        await SourceRepository(session).add(source)
        fetch = FeedFetch(
            run_id=run.id,
            source_id=source.id,
            status=FeedFetchStatus.SUCCESS,
            http_status=200,
            started_at=old,
            finished_at=old + timedelta(seconds=1),
            entries_count=1,
            duration_ms=10,
        )
        await FeedFetchRepository(session).add(fetch)

    result = await cleanup_operational_records(
        session_factory,
        older_than_days=30,
        dry_run=True,
    )
    assert result.dry_run is True
    assert result.feed_fetches >= 1


@pytest.mark.asyncio
async def test_scheduler_registers_job_when_enabled() -> None:
    runtime = build_pipeline_runtime(_settings(SCHEDULER_ENABLED=True))
    try:
        scheduler = build_scheduler(runtime)
        job = scheduler.get_job(JOB_ID)
        assert job is not None
        assert job.max_instances == 1
        assert job.coalesce is True
        assert job.misfire_grace_time == 120
    finally:
        await runtime.aclose()


@pytest.mark.asyncio
async def test_scheduler_skips_job_when_disabled() -> None:
    runtime = build_pipeline_runtime(_settings(SCHEDULER_ENABLED=False))
    try:
        scheduler = build_scheduler(runtime)
        assert scheduler.get_job(JOB_ID) is None
    finally:
        await runtime.aclose()
