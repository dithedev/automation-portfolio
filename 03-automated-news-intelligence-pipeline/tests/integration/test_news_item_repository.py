"""PostgreSQL integration checks for article deduplication."""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain import IgnoreReason, NewsItem, NewsItemStatus, Source
from app.infrastructure.db.repositories import (
    NewsInsertResult,
    NewsItemRepository,
    SourceRepository,
)
from app.infrastructure.db.session import transaction_scope
from app.texts.db import NEWS_DUPLICATE_CONFLICT, NEWS_ID_CONFLICT, NEWS_NOT_FOUND

COLLECTED_AT = datetime(2026, 9, 14, 8, 0, tzinfo=UTC)


def make_source(key: str = "example-feed") -> Source:
    """Create a valid source for article persistence."""
    return Source(
        key=key,
        name="Example Feed",
        feed_url="https://example.com/feed.xml",
        allowed_host="example.com",
        category="artificial_intelligence",
    )


def make_item(
    source_id: UUID,
    *,
    slug: str = "article",
    external_id: str | None = "entry-1",
) -> NewsItem:
    """Create an article whose URL hash matches its canonical URL."""
    url = f"https://example.com/{slug}"
    return NewsItem(
        source_id=source_id,
        external_id=external_id,
        original_url=url,
        canonical_url=url,
        url_hash=sha256(url.encode()).hexdigest(),
        title="A factual product update",
        normalized_title="a factual product update",
        raw_summary="<p>A factual product update.</p>",
        sanitized_summary="A factual product update.",
        author="Example Author",
        published_at=COLLECTED_AT,
        collected_at=COLLECTED_AT,
        content_hash=sha256(b"A factual product update.").hexdigest(),
    )


async def test_article_round_trip(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Restore every persisted article field."""
    source = make_source()
    item = make_item(source.id)

    async with transaction_scope(session_factory) as session:
        await SourceRepository(session).add(source)
        result = await NewsItemRepository(session).add_if_new(item)
        assert result == NewsInsertResult(news_item_id=item.id, inserted=True)

    async with transaction_scope(session_factory) as session:
        assert await NewsItemRepository(session).get(item.id) == item


@pytest.mark.parametrize("duplicate_key", ["url", "external-id"])
async def test_duplicate_preserves_original_content(
    session_factory: async_sessionmaker[AsyncSession],
    duplicate_key: str,
) -> None:
    """Retain the first article when a repeated key carries changed content."""
    source = make_source()
    original = make_item(source.id)

    if duplicate_key == "url":
        duplicate = replace(
            original,
            id=uuid4(),
            external_id="entry-2",
            title="Changed title",
        )
    else:
        duplicate = make_item(source.id, slug="changed-url")
        duplicate.title = "Changed title"

    async with transaction_scope(session_factory) as session:
        await SourceRepository(session).add(source)
        await NewsItemRepository(session).add_if_new(original)

    async with transaction_scope(session_factory) as session:
        result = await NewsItemRepository(session).add_if_new(duplicate)
        assert result == NewsInsertResult(news_item_id=original.id, inserted=False)

    async with transaction_scope(session_factory) as session:
        repository = NewsItemRepository(session)
        assert await repository.get(original.id) == original
        assert await repository.get(duplicate.id) is None


async def test_same_url_from_two_sources_is_one_article(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Deduplicate canonical URL hashes across different feed sources."""
    first_source = make_source("first")
    second_source = make_source("second")
    first = make_item(first_source.id)
    second = make_item(second_source.id, external_id="other-entry")

    async with transaction_scope(session_factory) as session:
        await SourceRepository(session).add(first_source)
        await SourceRepository(session).add(second_source)
        repository = NewsItemRepository(session)
        assert (await repository.add_if_new(first)).inserted
        result = await repository.add_if_new(second)
        assert result.news_item_id == first.id
        assert not result.inserted


async def test_missing_external_ids_allow_distinct_urls(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Keep distinct URLs even when external IDs and content hashes match."""
    source = make_source()
    first = make_item(source.id, slug="first", external_id=None)
    second = make_item(source.id, slug="second", external_id=None)

    async with transaction_scope(session_factory) as session:
        await SourceRepository(session).add(source)
        repository = NewsItemRepository(session)
        assert (await repository.add_if_new(first)).inserted
        assert (await repository.add_if_new(second)).inserted


async def test_conflicting_keys_are_rejected(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Reject an incoming article whose keys identify two different rows."""
    source = make_source()
    first = make_item(source.id, slug="first", external_id="first")
    second = make_item(source.id, slug="second", external_id="second")
    ambiguous = replace(first, id=uuid4(), external_id="second")

    async with transaction_scope(session_factory) as session:
        await SourceRepository(session).add(source)
        repository = NewsItemRepository(session)
        await repository.add_if_new(first)
        await repository.add_if_new(second)

    with pytest.raises(ValueError) as error:
        async with transaction_scope(session_factory) as session:
            await NewsItemRepository(session).add_if_new(ambiguous)

    assert str(error.value) == NEWS_DUPLICATE_CONFLICT


async def test_unrelated_id_collision_is_rejected(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Avoid classifying an unrelated primary-key collision as a duplicate."""
    source = make_source()
    original = make_item(source.id)
    collision = replace(
        make_item(source.id, slug="other", external_id="other"),
        id=original.id,
    )

    async with transaction_scope(session_factory) as session:
        await SourceRepository(session).add(source)
        await NewsItemRepository(session).add_if_new(original)

    with pytest.raises(ValueError) as error:
        async with transaction_scope(session_factory) as session:
            await NewsItemRepository(session).add_if_new(collision)

    assert str(error.value) == NEWS_ID_CONFLICT


async def test_concurrent_duplicates_insert_one_row(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Resolve competing insertions using independent database transactions."""
    source = make_source()
    first = make_item(source.id)
    second = replace(first, id=uuid4())

    async with transaction_scope(session_factory) as session:
        await SourceRepository(session).add(source)

    async def insert_item(item: NewsItem) -> NewsInsertResult:
        """Insert and commit one article using an independent session."""
        async with transaction_scope(session_factory) as session:
            return await NewsItemRepository(session).add_if_new(item)

    results = await asyncio.gather(insert_item(first), insert_item(second))

    assert sum(result.inserted for result in results) == 1
    assert results[0].news_item_id == results[1].news_item_id

    async with transaction_scope(session_factory) as session:
        repository = NewsItemRepository(session)
        stored = [
            await repository.get(first.id),
            await repository.get(second.id),
        ]
        assert sum(item is not None for item in stored) == 1


async def test_ignored_transition_persists_reason(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Persist an ignored status together with its domain-approved reason."""
    source = make_source()
    item = make_item(source.id)

    async with transaction_scope(session_factory) as session:
        await SourceRepository(session).add(source)
        await NewsItemRepository(session).add_if_new(item)

    async with transaction_scope(session_factory) as session:
        await NewsItemRepository(session).transition_to(
            item.id,
            NewsItemStatus.IGNORED,
            ignore_reason=IgnoreReason.IRRELEVANT,
        )

    async with transaction_scope(session_factory) as session:
        stored = await NewsItemRepository(session).get(item.id)
        assert stored is not None
        assert stored.status is NewsItemStatus.IGNORED
        assert stored.ignore_reason is IgnoreReason.IRRELEVANT


async def test_invalid_transition_preserves_article(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Leave a collected article unchanged when ignore metadata is missing."""
    source = make_source()
    item = make_item(source.id)

    async with transaction_scope(session_factory) as session:
        await SourceRepository(session).add(source)
        await NewsItemRepository(session).add_if_new(item)

    with pytest.raises(ValueError):
        async with transaction_scope(session_factory) as session:
            await NewsItemRepository(session).transition_to(
                item.id,
                NewsItemStatus.IGNORED,
            )

    async with transaction_scope(session_factory) as session:
        assert await NewsItemRepository(session).get(item.id) == item


async def test_missing_article_reads_and_transition(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Return None for a missing read and reject its status transition."""
    async with transaction_scope(session_factory) as session:
        assert await NewsItemRepository(session).get(uuid4()) is None

    with pytest.raises(LookupError) as error:
        async with transaction_scope(session_factory) as session:
            await NewsItemRepository(session).transition_to(
                uuid4(),
                NewsItemStatus.CANDIDATE,
            )

    assert str(error.value) == NEWS_NOT_FOUND


async def test_article_insert_rolls_back(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Roll back an executed INSERT when the transaction fails."""
    source = make_source()
    item = make_item(source.id)

    async with transaction_scope(session_factory) as session:
        await SourceRepository(session).add(source)

    with pytest.raises(RuntimeError):
        async with transaction_scope(session_factory) as session:
            await NewsItemRepository(session).add_if_new(item)
            raise RuntimeError

    async with transaction_scope(session_factory) as session:
        assert await NewsItemRepository(session).get(item.id) is None
