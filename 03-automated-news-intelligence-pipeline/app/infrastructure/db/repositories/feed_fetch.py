"""Persistence operations for completed feed fetches."""

from dataclasses import replace
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import FeedFetch
from app.infrastructure.db.models import FeedFetchModel


class FeedFetchRepository:
    """Append and read fetch results through a caller-owned session."""

    def __init__(self, session: AsyncSession) -> None:
        """Bind repository operations to one session."""
        self._session = session

    async def add(self, fetch: FeedFetch) -> FeedFetch:
        """Insert a validated result without committing the transaction.

        Duplicate run/source pairs and missing parent records produce
        database integrity errors that propagate to the caller.
        """
        validated = replace(fetch)
        model = FeedFetchModel(
            id=validated.id,
            run_id=validated.run_id,
            source_id=validated.source_id,
            status=validated.status,
            http_status=validated.http_status,
            entries_count=validated.entries_count,
            duration_ms=validated.duration_ms,
            error_code=validated.error_code,
            error_summary=validated.error_summary,
            started_at=validated.started_at,
            finished_at=validated.finished_at,
        )
        self._session.add(model)
        await self._session.flush()
        return self._to_domain(model)

    async def get(self, fetch_id: UUID) -> FeedFetch | None:
        """Return a fetch result by ID, or None when it does not exist."""
        model = await self._session.get(FeedFetchModel, fetch_id)
        return self._to_domain(model) if model is not None else None

    async def list_for_run(self, run_id: UUID) -> tuple[FeedFetch, ...]:
        """Return a run's fetch results ordered by start time and ID."""
        statement = (
            select(FeedFetchModel)
            .where(FeedFetchModel.run_id == run_id)
            .order_by(FeedFetchModel.started_at.asc(), FeedFetchModel.id.asc())
        )
        models = await self._session.scalars(statement)
        return tuple(self._to_domain(model) for model in models)

    @staticmethod
    def _to_domain(model: FeedFetchModel) -> FeedFetch:
        """Restore and validate a fetch result from persisted fields."""
        return FeedFetch(
            id=model.id,
            run_id=model.run_id,
            source_id=model.source_id,
            status=model.status,
            http_status=model.http_status,
            entries_count=model.entries_count,
            duration_ms=model.duration_ms,
            error_code=model.error_code,
            error_summary=model.error_summary,
            started_at=model.started_at,
            finished_at=model.finished_at,
        )
