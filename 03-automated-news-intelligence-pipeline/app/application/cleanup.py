"""Delete aged operational rows without touching dedupe data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.validators import utc_now
from app.infrastructure.db.models import DeliveryAttemptModel, FeedFetchModel
from app.infrastructure.db.session import transaction_scope


@dataclass(frozen=True, slots=True, kw_only=True)
class CleanupResult:
    feed_fetches: int
    delivery_attempts: int
    dry_run: bool
    cutoff: datetime


async def cleanup_operational_records(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    older_than_days: int,
    dry_run: bool,
) -> CleanupResult:
    """Remove feed_fetches and delivery_attempts finished before the cutoff."""
    if older_than_days < 1:
        raise ValueError("older_than_days must be >= 1")

    cutoff = utc_now() - timedelta(days=older_than_days)

    async with transaction_scope(session_factory) as session:
        feed_count = await _count_older_feed_fetches(session, cutoff)
        delivery_count = await _count_older_delivery_attempts(session, cutoff)

        if not dry_run:
            await session.execute(
                delete(FeedFetchModel).where(FeedFetchModel.finished_at < cutoff),
            )
            await session.execute(
                delete(DeliveryAttemptModel).where(
                    DeliveryAttemptModel.finished_at.is_not(None),
                    DeliveryAttemptModel.finished_at < cutoff,
                ),
            )

    return CleanupResult(
        feed_fetches=feed_count,
        delivery_attempts=delivery_count,
        dry_run=dry_run,
        cutoff=cutoff,
    )


async def _count_older_feed_fetches(session: AsyncSession, cutoff: datetime) -> int:
    value = await session.scalar(
        select(func.count())
        .select_from(FeedFetchModel)
        .where(
            FeedFetchModel.finished_at < cutoff,
        ),
    )
    return int(value or 0)


async def _count_older_delivery_attempts(session: AsyncSession, cutoff: datetime) -> int:
    value = await session.scalar(
        select(func.count())
        .select_from(DeliveryAttemptModel)
        .where(
            DeliveryAttemptModel.finished_at.is_not(None),
            DeliveryAttemptModel.finished_at < cutoff,
        ),
    )
    return int(value or 0)
