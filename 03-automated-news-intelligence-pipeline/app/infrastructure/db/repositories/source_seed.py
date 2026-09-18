"""Synchronize trusted source settings while preserving fetch metadata."""

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import Source
from app.domain.validators import utc_now
from app.infrastructure.db.models import SourceModel
from app.infrastructure.feeds.config import FeedConfiguration
from app.texts.feeds import FEEDS_IDENTITY_MISMATCH


class SourceSeedRepository:
    """Synchronize source configuration through a caller-owned transaction."""

    def __init__(self, session: AsyncSession) -> None:
        """Bind synchronization operations to one database session."""
        self._session = session

    async def synchronize(self, configuration: FeedConfiguration) -> int:
        """Upsert source settings without changing source identity or history.

        The caller must roll back the transaction if synchronization fails.
        Sources missing from configuration are left unchanged.

        Raises:
            ValueError: If an existing key would change its allowed host.
        """
        sources = tuple(
            configured.to_source(configuration.defaults) for configured in configuration.sources
        )

        # A consistent lock order reduces deadlock risk between concurrent seeds.
        for source in sorted(sources, key=lambda item: item.key):
            await self._upsert(source)

        return len(sources)

    async def _upsert(self, source: Source) -> None:
        """Insert a source or update only its mutable configuration fields."""
        insert_statement = insert(SourceModel).values(
            id=source.id,
            key=source.key,
            name=source.name,
            feed_url=source.feed_url,
            allowed_host=source.allowed_host,
            category=source.category,
            language=source.language,
            enabled=source.enabled,
            priority=source.priority,
            created_at=source.created_at,
            updated_at=source.updated_at,
        )
        incoming = insert_statement.excluded

        upsert_statement = insert_statement.on_conflict_do_update(
            index_elements=[SourceModel.key],
            set_={
                "name": incoming.name,
                "feed_url": incoming.feed_url,
                "category": incoming.category,
                "language": incoming.language,
                "enabled": incoming.enabled,
                "priority": incoming.priority,
                "updated_at": utc_now(),
            },
            where=(SourceModel.allowed_host == incoming.allowed_host),
        ).returning(SourceModel.id)

        source_id = await self._session.scalar(upsert_statement)

        if source_id is None:
            raise ValueError(FEEDS_IDENTITY_MISMATCH)
