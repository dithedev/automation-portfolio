"""Integration tests for PostgreSQL advisory locking."""

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from app.infrastructure.db.advisory_lock import (
    PIPELINE_ADVISORY_LOCK_KEY,
    PipelineAdvisoryLock,
)


@pytest.mark.asyncio
async def test_advisory_lock_contention_and_release(db_engine: AsyncEngine) -> None:
    first = PipelineAdvisoryLock(db_engine, lock_key=PIPELINE_ADVISORY_LOCK_KEY)
    second = PipelineAdvisoryLock(db_engine, lock_key=PIPELINE_ADVISORY_LOCK_KEY)

    assert await first.acquire() is True
    assert await second.acquire() is False

    await first.release()
    assert await second.acquire() is True
    await second.release()
