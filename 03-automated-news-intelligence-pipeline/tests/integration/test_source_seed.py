"""Source synchronization checks against migrated PostgreSQL."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.infrastructure.db.models import SourceModel
from app.infrastructure.db.repositories import SourceRepository
from app.infrastructure.db.repositories.source_seed import SourceSeedRepository
from app.infrastructure.feeds.config import FeedConfiguration


def make_configuration(
    *,
    name: str = "Example News",
    enabled: bool = True,
    url: str = "https://example.com/feed.xml",
) -> FeedConfiguration:
    """Build a validated source list for synchronization checks."""
    return FeedConfiguration.model_validate(
        {
            "version": 1,
            "sources": [
                {
                    "key": "example-news",
                    "name": name,
                    "url": url,
                    "allowed_host": "example.com",
                    "category": "artificial_intelligence",
                    "priority": "7.50",
                    "enabled": enabled,
                }
            ],
        }
    )


async def test_repeated_seed_preserves_fetch_metadata(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory.begin() as session:
        await SourceSeedRepository(session).synchronize(make_configuration())

        repository = SourceRepository(session)
        source = await repository.get_by_key("example-news")
        assert source is not None

        checked_at = datetime.now(UTC)
        last_modified = "Tue, 15 Sep 2026 08:00:00 GMT"

        source.record_fetch_success(
            checked_at=checked_at,
            etag='"version-1"',
            last_modified=last_modified,
        )
        source.record_fetch_failure(checked_at=checked_at)
        await repository.save(source)

        source_id = source.id
        created_at = source.created_at

    async with session_factory.begin() as session:
        count = await SourceSeedRepository(session).synchronize(
            make_configuration(name="Updated News", enabled=False)
        )
        assert count == 1

    async with session_factory() as session:
        stored = await SourceRepository(session).get_by_key("example-news")
        assert stored is not None

        assert stored.id == source_id
        assert stored.created_at == created_at
        assert stored.name == "Updated News"
        assert stored.enabled is False
        assert stored.priority == Decimal("7.50")
        assert stored.etag == '"version-1"'
        assert stored.last_modified == last_modified
        assert stored.last_checked_at == checked_at
        assert stored.last_success_at == checked_at
        assert stored.consecutive_failures == 1
        assert await session.scalar(select(func.count()).select_from(SourceModel)) == 1


async def test_seed_updates_feed_url_on_same_allowed_host(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory.begin() as session:
        await SourceSeedRepository(session).synchronize(make_configuration())

    async with session_factory.begin() as session:
        await SourceSeedRepository(session).synchronize(
            make_configuration(url="https://example.com/feed/v2.xml")
        )

    async with session_factory() as session:
        stored = await SourceRepository(session).get_by_key("example-news")
        assert stored is not None
        assert stored.feed_url == "https://example.com/feed/v2.xml"
        assert stored.allowed_host == "example.com"


async def test_seed_rolls_back_when_source_identity_changes(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory.begin() as session:
        await SourceSeedRepository(session).synchronize(make_configuration())

    conflicting = FeedConfiguration.model_validate(
        {
            "version": 1,
            "sources": [
                {
                    "key": "aaa-new",
                    "name": "New Source",
                    "url": "https://example.com/new.xml",
                    "allowed_host": "example.com",
                    "category": "artificial_intelligence",
                },
                {
                    "key": "example-news",
                    "name": "Changed Identity",
                    "url": "https://other.example.com/feed.xml",
                    "allowed_host": "other.example.com",
                    "category": "artificial_intelligence",
                },
            ],
        }
    )

    with pytest.raises(ValueError):
        async with session_factory.begin() as session:
            await SourceSeedRepository(session).synchronize(conflicting)

    async with session_factory() as session:
        repository = SourceRepository(session)

        assert await repository.get_by_key("aaa-new") is None

        stored = await repository.get_by_key("example-news")
        assert stored is not None
        assert stored.feed_url == "https://example.com/feed.xml"
        assert stored.allowed_host == "example.com"
        assert stored.name == "Example News"
