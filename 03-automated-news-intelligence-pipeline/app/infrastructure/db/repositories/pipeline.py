"""Persistence operations for pipeline runs."""

from dataclasses import replace
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import PipelineRun, PipelineRunStatus
from app.domain.state_machine import ensure_pipeline_run_transition
from app.infrastructure.db.models import PipelineRunModel
from app.texts.db import (
    RUN_IDENTITY_MISMATCH,
    RUN_NOT_FOUND,
    RUN_TERMINAL_UPDATE_FORBIDDEN,
)


class PipelineRunRepository:
    """Persist run state through a caller-owned session without committing."""

    def __init__(self, session: AsyncSession) -> None:
        """Bind repository operations to one session."""
        self._session = session

    async def add(self, run: PipelineRun) -> PipelineRun:
        """Validate and insert a run, propagating duplicate-ID errors."""
        validated = replace(run)
        model = PipelineRunModel(
            id=validated.id,
            trigger_type=validated.trigger_type,
            app_version=validated.app_version,
            status=validated.status,
            started_at=validated.started_at,
            finished_at=validated.finished_at,
            feeds_total=validated.feeds_total,
            feeds_succeeded=validated.feeds_succeeded,
            items_fetched=validated.items_fetched,
            items_inserted=validated.items_inserted,
            items_duplicate=validated.items_duplicate,
            candidates_count=validated.candidates_count,
            selected_count=validated.selected_count,
            error_code=validated.error_code,
            error_summary=validated.error_summary,
            duration_ms=validated.duration_ms,
        )
        self._session.add(model)
        await self._session.flush()
        return self._to_domain(model)

    async def get(self, run_id: UUID) -> PipelineRun | None:
        """Return a run by ID, or None when it does not exist."""
        model = await self._session.get(PipelineRunModel, run_id)
        return self._to_domain(model) if model is not None else None

    async def get_latest(self) -> PipelineRun | None:
        """Return the latest started run with deterministic ordering."""
        statement = (
            select(PipelineRunModel)
            .order_by(
                PipelineRunModel.started_at.desc(),
                PipelineRunModel.id.desc(),
            )
            .limit(1)
        )
        model = await self._session.scalar(statement)
        return self._to_domain(model) if model is not None else None

    async def save(self, run: PipelineRun) -> PipelineRun:
        """Update counters or complete a run while holding its row lock.

        Identical completed results can be saved again without modification.
        Changed terminal results and replaced identity fields are rejected.
        The caller owns transaction completion and rollback.
        """
        validated = replace(run)
        statement = (
            select(PipelineRunModel)
            .where(PipelineRunModel.id == validated.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        model = await self._session.scalar(statement)

        if model is None:
            raise LookupError(RUN_NOT_FOUND)

        if (
            model.trigger_type != validated.trigger_type
            or model.app_version != validated.app_version
            or model.started_at != validated.started_at
        ):
            raise ValueError(RUN_IDENTITY_MISMATCH)

        if model.status is not PipelineRunStatus.RUNNING:
            stored = self._to_domain(model)

            if stored != validated:
                raise ValueError(RUN_TERMINAL_UPDATE_FORBIDDEN)

            return stored

        if model.status is not validated.status:
            ensure_pipeline_run_transition(model.status, validated.status)

        model.status = validated.status
        model.finished_at = validated.finished_at
        model.feeds_total = validated.feeds_total
        model.feeds_succeeded = validated.feeds_succeeded
        model.items_fetched = validated.items_fetched
        model.items_inserted = validated.items_inserted
        model.items_duplicate = validated.items_duplicate
        model.candidates_count = validated.candidates_count
        model.selected_count = validated.selected_count
        model.error_code = validated.error_code
        model.error_summary = validated.error_summary
        model.duration_ms = validated.duration_ms

        await self._session.flush()
        return self._to_domain(model)

    @staticmethod
    def _to_domain(model: PipelineRunModel) -> PipelineRun:
        """Restore and validate a run from persisted fields."""
        return PipelineRun(
            id=model.id,
            trigger_type=model.trigger_type,
            app_version=model.app_version,
            status=model.status,
            started_at=model.started_at,
            finished_at=model.finished_at,
            feeds_total=model.feeds_total,
            feeds_succeeded=model.feeds_succeeded,
            items_fetched=model.items_fetched,
            items_inserted=model.items_inserted,
            items_duplicate=model.items_duplicate,
            candidates_count=model.candidates_count,
            selected_count=model.selected_count,
            error_code=model.error_code,
            error_summary=model.error_summary,
            duration_ms=model.duration_ms,
        )
