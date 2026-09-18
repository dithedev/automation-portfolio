"""Persistence operations for feed sources."""

from dataclasses import replace
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import Source
from app.infrastructure.db.models import SourceModel
from app.texts.db import SOURCE_IDENTITY_MISMATCH, SOURCE_NOT_FOUND


class SourceRepository:
    """Read and persist source entities through a caller-owned session.

    Write methods flush changes without committing. Database exceptions
    propagate to the caller, which owns the transaction and rollback.
    """

    def __init__(self, session: AsyncSession) -> None:
        """Bind repository operations to one session."""
        self._session = session

    async def add(self, source: Source) -> Source:
        """Insert a source and return its persisted domain representation.

        Raises:
            ValueError: If the supplied entity fails domain validation.
            IntegrityError: If the source ID or key already exists.
        """
        validated = replace(source)
        model = self._to_model(validated)

        self._session.add(model)
        await self._session.flush()

        return self._to_domain(model)

    async def get(self, source_id: UUID) -> Source | None:
        """Return a source by ID, or None when it does not exist."""
        model = await self._session.get(SourceModel, source_id)

        if model is None:
            return None

        return self._to_domain(model)

    async def get_by_key(self, key: str) -> Source | None:
        """Return a source by its normalized configuration key."""
        statement = select(SourceModel).where(
            SourceModel.key == key.strip().lower(),
        )
        model = await self._session.scalar(statement)

        if model is None:
            return None

        return self._to_domain(model)

    async def list_enabled(self) -> tuple[Source, ...]:
        """Return enabled sources ordered by priority, then source key."""
        statement = (
            select(SourceModel)
            .where(SourceModel.enabled.is_(True))
            .order_by(SourceModel.priority.desc(), SourceModel.key.asc())
        )
        models = await self._session.scalars(statement)

        return tuple(self._to_domain(model) for model in models)

    async def list_all(self) -> tuple[Source, ...]:
        """Return all sources ordered by key."""
        statement = select(SourceModel).order_by(SourceModel.key.asc())
        models = await self._session.scalars(statement)
        return tuple(self._to_domain(model) for model in models)

    async def save(self, source: Source) -> Source:
        """Update mutable fields of an existing source under a row lock.

        Raises:
            ValueError: If domain validation fails or source identity differs.
            LookupError: If the source does not exist.

        The row lock remains held until the caller completes the transaction.
        """
        validated = replace(source)
        statement = (
            select(SourceModel)
            .where(SourceModel.id == validated.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        model = await self._session.scalar(statement)

        if model is None:
            raise LookupError(SOURCE_NOT_FOUND)

        if (
            model.key != validated.key
            or model.feed_url != validated.feed_url
            or model.allowed_host != validated.allowed_host
            or model.created_at != validated.created_at
        ):
            raise ValueError(SOURCE_IDENTITY_MISMATCH)

        model.name = validated.name
        model.category = validated.category
        model.language = validated.language
        model.enabled = validated.enabled
        model.priority = validated.priority
        model.etag = validated.etag
        model.last_modified = validated.last_modified
        model.last_checked_at = validated.last_checked_at
        model.last_success_at = validated.last_success_at
        model.consecutive_failures = validated.consecutive_failures
        model.updated_at = validated.updated_at

        await self._session.flush()

        return self._to_domain(model)

    @staticmethod
    def _to_model(source: Source) -> SourceModel:
        """Map a validated domain source to a new persistence model."""
        return SourceModel(
            id=source.id,
            key=source.key,
            name=source.name,
            feed_url=source.feed_url,
            allowed_host=source.allowed_host,
            category=source.category,
            language=source.language,
            enabled=source.enabled,
            priority=source.priority,
            etag=source.etag,
            last_modified=source.last_modified,
            last_checked_at=source.last_checked_at,
            last_success_at=source.last_success_at,
            consecutive_failures=source.consecutive_failures,
            created_at=source.created_at,
            updated_at=source.updated_at,
        )

    @staticmethod
    def _to_domain(model: SourceModel) -> Source:
        """Restore and validate a domain source from persisted fields."""
        return Source(
            id=model.id,
            key=model.key,
            name=model.name,
            feed_url=model.feed_url,
            allowed_host=model.allowed_host,
            category=model.category,
            language=model.language,
            enabled=model.enabled,
            priority=model.priority,
            etag=model.etag,
            last_modified=model.last_modified,
            last_checked_at=model.last_checked_at,
            last_success_at=model.last_success_at,
            consecutive_failures=model.consecutive_failures,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
