"""PostgreSQL integration checks for source persistence."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain import Source
from app.infrastructure.db.repositories import SourceRepository
from app.infrastructure.db.session import transaction_scope
from app.texts.db import SOURCE_IDENTITY_MISMATCH, SOURCE_NOT_FOUND

CREATED_AT = datetime(2026, 9, 14, 8, 0, tzinfo=UTC)


def make_source(
    *,
    key: str = "example-feed",
    priority: Decimal = Decimal("5.00"),
    enabled: bool = True,
) -> Source:
    """Create a valid source with deterministic timestamps."""
    return Source(
        key=key,
        name="Example Feed",
        feed_url="https://example.com/feed.xml",
        allowed_host="example.com",
        category="artificial_intelligence",
        priority=priority,
        enabled=enabled,
        created_at=CREATED_AT,
        updated_at=CREATED_AT,
    )


async def test_committed_source_restores_all_fields(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Preserve source configuration, timestamps, and fetch metadata."""
    source = make_source()
    source.record_fetch_success(
        checked_at=CREATED_AT + timedelta(seconds=1),
        etag='"revision-1"',
        last_modified="Mon, 14 Sep 2026 08:00:00 GMT",
    )
    source.record_fetch_failure(
        checked_at=CREATED_AT + timedelta(seconds=2),
    )

    async with transaction_scope(session_factory) as session:
        saved = await SourceRepository(session).add(source)
        assert saved == source

    async with transaction_scope(session_factory) as session:
        repository = SourceRepository(session)
        assert await repository.get(source.id) == source
        assert await repository.get_by_key(" EXAMPLE-FEED ") == source


async def test_flush_does_not_commit(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Keep a flushed insertion invisible to another transaction until commit."""
    source = make_source()

    async with transaction_scope(session_factory) as writer:
        await SourceRepository(writer).add(source)

        async with transaction_scope(session_factory) as reader:
            assert await SourceRepository(reader).get(source.id) is None

    async with transaction_scope(session_factory) as reader:
        assert await SourceRepository(reader).get(source.id) == source


async def test_exception_rolls_back_insert(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Remove flushed changes when the transaction exits with an exception."""
    source = make_source()

    with pytest.raises(RuntimeError):
        async with transaction_scope(session_factory) as session:
            await SourceRepository(session).add(source)
            raise RuntimeError

    async with transaction_scope(session_factory) as session:
        assert await SourceRepository(session).get(source.id) is None


async def test_duplicate_key_is_rejected(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Reject a duplicate source key and retain the original committed source."""
    source = make_source()

    async with transaction_scope(session_factory) as session:
        await SourceRepository(session).add(source)

    duplicate = replace(source, id=uuid4(), name="Duplicate Feed")

    with pytest.raises(IntegrityError):
        async with transaction_scope(session_factory) as session:
            await SourceRepository(session).add(duplicate)

    async with transaction_scope(session_factory) as session:
        repository = SourceRepository(session)
        assert await repository.get_by_key(source.key) == source
        assert await repository.get(duplicate.id) is None


async def test_enabled_sources_have_deterministic_order(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Exclude disabled sources and resolve equal priorities by source key."""
    sources = (
        make_source(key="low", priority=Decimal("1.00")),
        make_source(key="beta", priority=Decimal("8.00")),
        make_source(key="alpha", priority=Decimal("8.00")),
        make_source(
            key="disabled",
            priority=Decimal("10.00"),
            enabled=False,
        ),
    )

    async with transaction_scope(session_factory) as session:
        repository = SourceRepository(session)
        for source in sources:
            await repository.add(source)

    async with transaction_scope(session_factory) as session:
        enabled = await SourceRepository(session).list_enabled()
        assert [source.key for source in enabled] == ["alpha", "beta", "low"]


async def test_save_persists_fetch_changes(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Persist mutable configuration and updated fetch metadata."""
    source = make_source()

    async with transaction_scope(session_factory) as session:
        await SourceRepository(session).add(source)

    source.name = "Updated Feed"
    source.enabled = False
    source.record_fetch_success(
        checked_at=CREATED_AT + timedelta(seconds=5),
        etag='"revision-2"',
        last_modified=None,
    )

    async with transaction_scope(session_factory) as session:
        saved = await SourceRepository(session).save(source)
        assert saved == source

    async with transaction_scope(session_factory) as session:
        assert await SourceRepository(session).get(source.id) == source


@pytest.mark.parametrize(
    "changes",
    [
        {"key": "other-feed"},
        {"feed_url": "https://example.com/other.xml"},
        {
            "feed_url": "https://other.example.com/feed.xml",
            "allowed_host": "other.example.com",
        },
        {"created_at": CREATED_AT - timedelta(seconds=1)},
    ],
    ids=["key", "feed-url", "allowed-host", "created-at"],
)
async def test_save_rejects_identity_changes(
    session_factory: async_sessionmaker[AsyncSession],
    changes: dict[str, object],
) -> None:
    """Reject identity replacement without changing the stored source."""
    source = make_source()

    async with transaction_scope(session_factory) as session:
        await SourceRepository(session).add(source)

    changed = replace(source, name="Rejected Update", **changes)

    with pytest.raises(ValueError) as error:
        async with transaction_scope(session_factory) as session:
            await SourceRepository(session).save(changed)

    assert str(error.value) == SOURCE_IDENTITY_MISMATCH

    async with transaction_scope(session_factory) as session:
        assert await SourceRepository(session).get(source.id) == source


async def test_save_missing_source_is_rejected(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Require a source to exist before updating it."""
    with pytest.raises(LookupError) as error:
        async with transaction_scope(session_factory) as session:
            await SourceRepository(session).save(make_source())

    assert str(error.value) == SOURCE_NOT_FOUND


async def test_missing_source_returns_none(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Return None for unknown source IDs and keys."""
    async with transaction_scope(session_factory) as session:
        repository = SourceRepository(session)
        assert await repository.get(uuid4()) is None
        assert await repository.get_by_key("missing-feed") is None
