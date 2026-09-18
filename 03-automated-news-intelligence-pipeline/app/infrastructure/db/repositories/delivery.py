"""Persistence operations for Telegram delivery attempts."""

from dataclasses import replace
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import DeliveryAttempt, DeliveryStatus
from app.infrastructure.db.models import DeliveryAttemptModel
from app.texts.db import (
    ATTEMPT_IDENTITY_MISMATCH,
    ATTEMPT_NOT_FOUND,
    ATTEMPT_TERMINAL_UPDATE_FORBIDDEN,
)


class DeliveryAttemptRepository:
    """Persist delivery history through a caller-owned session."""

    def __init__(self, session: AsyncSession) -> None:
        """Bind repository operations to one session."""
        self._session = session

    async def add(self, attempt: DeliveryAttempt) -> DeliveryAttempt:
        """Insert a validated attempt without committing the transaction.

        Duplicate attempt identifiers and numbering produce database
        integrity errors. Retrying delivery requires a separate record.
        """
        validated = replace(attempt)
        model = DeliveryAttemptModel(
            id=validated.id,
            digest_id=validated.digest_id,
            part_number=validated.part_number,
            attempt_number=validated.attempt_number,
            status=validated.status,
            telegram_message_id=validated.telegram_message_id,
            http_status=validated.http_status,
            retry_after_seconds=validated.retry_after_seconds,
            error_code=validated.error_code,
            error_summary=validated.error_summary,
            started_at=validated.started_at,
            finished_at=validated.finished_at,
        )
        self._session.add(model)
        await self._session.flush()
        return self._to_domain(model)

    async def get(self, attempt_id: UUID) -> DeliveryAttempt | None:
        """Return an attempt by ID, or None when it does not exist."""
        model = await self._session.get(DeliveryAttemptModel, attempt_id)
        return self._to_domain(model) if model is not None else None

    async def list_for_digest(
        self,
        digest_id: UUID,
    ) -> tuple[DeliveryAttempt, ...]:
        """Return delivery history ordered by part and attempt number."""
        statement = (
            select(DeliveryAttemptModel)
            .where(DeliveryAttemptModel.digest_id == digest_id)
            .order_by(
                DeliveryAttemptModel.part_number.asc(),
                DeliveryAttemptModel.attempt_number.asc(),
            )
        )
        models = await self._session.scalars(statement)
        return tuple(self._to_domain(model) for model in models)

    async def save(self, attempt: DeliveryAttempt) -> DeliveryAttempt:
        """Complete a pending attempt while holding its row lock.

        Identity fields cannot be replaced. An identical terminal result
        can be saved again, but changing a completed result is forbidden.
        The caller owns transaction completion and rollback.
        """
        validated = replace(attempt)
        statement = (
            select(DeliveryAttemptModel)
            .where(DeliveryAttemptModel.id == validated.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        model = await self._session.scalar(statement)

        if model is None:
            raise LookupError(ATTEMPT_NOT_FOUND)

        if (
            model.digest_id != validated.digest_id
            or model.part_number != validated.part_number
            or model.attempt_number != validated.attempt_number
            or model.started_at != validated.started_at
        ):
            raise ValueError(ATTEMPT_IDENTITY_MISMATCH)

        if model.status is not DeliveryStatus.PENDING:
            stored = self._to_domain(model)

            if stored != validated:
                raise ValueError(ATTEMPT_TERMINAL_UPDATE_FORBIDDEN)

            return stored

        model.status = validated.status
        model.telegram_message_id = validated.telegram_message_id
        model.http_status = validated.http_status
        model.retry_after_seconds = validated.retry_after_seconds
        model.error_code = validated.error_code
        model.error_summary = validated.error_summary
        model.finished_at = validated.finished_at

        await self._session.flush()
        return self._to_domain(model)

    @staticmethod
    def _to_domain(model: DeliveryAttemptModel) -> DeliveryAttempt:
        """Restore and validate an attempt from persisted fields."""
        return DeliveryAttempt(
            id=model.id,
            digest_id=model.digest_id,
            part_number=model.part_number,
            attempt_number=model.attempt_number,
            status=model.status,
            telegram_message_id=model.telegram_message_id,
            http_status=model.http_status,
            retry_after_seconds=model.retry_after_seconds,
            error_code=model.error_code,
            error_summary=model.error_summary,
            started_at=model.started_at,
            finished_at=model.finished_at,
        )
