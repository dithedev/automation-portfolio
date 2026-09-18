"""PostgreSQL integration checks for atomic digest persistence."""

import asyncio
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain import (
    Digest,
    DigestItem,
    DigestStatus,
    ErrorCode,
    NewsItem,
    NewsItemStatus,
    PipelineRun,
    Source,
    TriggerType,
)
from app.infrastructure.db.models import DigestItemModel
from app.infrastructure.db.repositories import (
    DigestRepository,
    NewsItemRepository,
    PipelineRunRepository,
    SourceRepository,
)
from app.infrastructure.db.session import transaction_scope
from app.texts.db import DIGEST_CANDIDATES_REQUIRED, DIGEST_NEWS_MISSING

CREATED_AT = datetime(2026, 9, 14, 8, 0, tzinfo=UTC)


async def prepare_candidates(
    session_factory: async_sessionmaker[AsyncSession],
) -> tuple[PipelineRun, tuple[NewsItem, ...]]:
    """Commit one run and three candidate articles for digest tests."""
    run = PipelineRun(
        trigger_type=TriggerType.MANUAL,
        app_version="0.1.0",
        started_at=CREATED_AT,
    )
    source = Source(
        key="example-feed",
        name="Example Feed",
        feed_url="https://example.com/feed.xml",
        allowed_host="example.com",
        category="artificial_intelligence",
    )
    items = tuple(
        NewsItem(
            source_id=source.id,
            original_url=f"https://example.com/article-{number}",
            canonical_url=f"https://example.com/article-{number}",
            url_hash=sha256(f"https://example.com/article-{number}".encode()).hexdigest(),
            title=f"Product update {number}",
            normalized_title=f"product update {number}",
            sanitized_summary=f"A factual product update numbered {number}.",
            content_hash=sha256(f"article-{number}".encode()).hexdigest(),
            collected_at=CREATED_AT,
            status=NewsItemStatus.CANDIDATE,
        )
        for number in range(1, 4)
    )

    async with transaction_scope(session_factory) as session:
        await PipelineRunRepository(session).add(run)
        await SourceRepository(session).add(source)
        for item in items:
            await NewsItemRepository(session).add_if_new(item)

    return run, items


def make_digest(run: PipelineRun, articles: tuple[NewsItem, ...]) -> Digest:
    """Create a generated digest with provider metadata and ordered articles."""
    return Digest(
        run_id=run.id,
        digest_date=date(2026, 9, 14),
        title="AI & Automation Daily Digest — 2026-09-14",
        rendered_text="A rendered digest containing three grounded product updates.",
        prompt_version="v1",
        provider_response_id="response-example",
        input_tokens=500,
        output_tokens=200,
        created_at=CREATED_AT,
        items=tuple(
            DigestItem(
                news_item_id=article.id,
                position=position,
                summary=(
                    "The supplied article describes a product update with "
                    "practical implications for developers and automation teams."
                ),
                tag="PRODUCT",
                relevance_score=Decimal("0.900"),
                selection_reason="Relevant product update.",
            )
            for position, article in enumerate(articles, start=1)
        ),
    )


async def test_digest_and_used_articles_commit_together(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Restore the full aggregate and confirm all selected articles were consumed."""
    run, articles = await prepare_candidates(session_factory)
    digest = make_digest(run, articles)

    async with transaction_scope(session_factory) as session:
        saved = await DigestRepository(session).create_generated(digest)
        assert saved == digest

    async with transaction_scope(session_factory) as session:
        repository = DigestRepository(session)
        assert await repository.get(digest.id) == digest
        assert await repository.get_by_run(run.id) == digest
        assert await repository.get_latest() == digest

        for article in articles:
            stored = await NewsItemRepository(session).get(article.id)
            assert stored is not None
            assert stored.status is NewsItemStatus.USED


async def test_outer_failure_rolls_back_entire_digest(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Roll back the digest, article links, and used statuses together."""
    run, articles = await prepare_candidates(session_factory)
    digest = make_digest(run, articles)

    with pytest.raises(RuntimeError):
        async with transaction_scope(session_factory) as session:
            await DigestRepository(session).create_generated(digest)
            raise RuntimeError

    async with transaction_scope(session_factory) as session:
        assert await DigestRepository(session).get(digest.id) is None
        count = await session.scalar(select(func.count()).select_from(DigestItemModel))
        assert count == 0

        for article in articles:
            assert await NewsItemRepository(session).get(article.id) == article


async def test_missing_article_does_not_consume_candidates(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Reject a digest referencing a missing article without changing candidates."""
    run, articles = await prepare_candidates(session_factory)
    digest = make_digest(run, articles)
    missing_item = replace(digest.items[-1], news_item_id=uuid4())
    digest = replace(digest, items=(*digest.items[:-1], missing_item))

    with pytest.raises(LookupError) as error:
        async with transaction_scope(session_factory) as session:
            await DigestRepository(session).create_generated(digest)

    assert str(error.value) == DIGEST_NEWS_MISSING

    async with transaction_scope(session_factory) as session:
        assert await DigestRepository(session).get(digest.id) is None
        for article in articles:
            assert await NewsItemRepository(session).get(article.id) == article


async def test_database_failure_can_be_caught_without_partial_save(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Keep the outer transaction usable after a digest foreign-key failure."""
    run, articles = await prepare_candidates(session_factory)
    digest = replace(make_digest(run, articles), run_id=uuid4())

    async with transaction_scope(session_factory) as session:
        with pytest.raises(IntegrityError):
            await DigestRepository(session).create_generated(digest)

        assert await DigestRepository(session).get(digest.id) is None
        count = await session.scalar(select(func.count()).select_from(DigestItemModel))
        assert count == 0

        for article in articles:
            assert await NewsItemRepository(session).get(article.id) == article


async def test_concurrent_digests_cannot_reuse_candidates(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Allow only one committed digest to consume a shared candidate set."""
    first_run, articles = await prepare_candidates(session_factory)
    second_run = replace(first_run, id=uuid4())

    async with transaction_scope(session_factory) as session:
        await PipelineRunRepository(session).add(second_run)

    first = make_digest(first_run, articles)
    second = make_digest(second_run, articles)

    async def create(digest: Digest) -> Digest:
        """Create and commit a digest using an independent transaction."""
        async with transaction_scope(session_factory) as session:
            return await DigestRepository(session).create_generated(digest)

    results = await asyncio.gather(
        create(first),
        create(second),
        return_exceptions=True,
    )

    assert sum(isinstance(result, Digest) for result in results) == 1
    failures = [result for result in results if isinstance(result, ValueError)]
    assert len(failures) == 1
    assert str(failures[0]) == DIGEST_CANDIDATES_REQUIRED

    async with transaction_scope(session_factory) as session:
        repository = DigestRepository(session)
        stored = [await repository.get(first.id), await repository.get(second.id)]
        assert sum(item is not None for item in stored) == 1
        count = await session.scalar(select(func.count()).select_from(DigestItemModel))
        assert count == 3


async def test_delivery_retry_preserves_generated_content(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Persist failure and retry transitions without replacing digest content."""
    run, articles = await prepare_candidates(session_factory)
    digest = make_digest(run, articles)

    async with transaction_scope(session_factory) as session:
        await DigestRepository(session).create_generated(digest)

    async with transaction_scope(session_factory) as session:
        await DigestRepository(session).transition_to(
            digest.id,
            DigestStatus.SENDING,
            occurred_at=CREATED_AT + timedelta(seconds=1),
        )

    async with transaction_scope(session_factory) as session:
        failed = await DigestRepository(session).transition_to(
            digest.id,
            DigestStatus.FAILED,
            occurred_at=CREATED_AT + timedelta(seconds=2),
            error_code=ErrorCode.TELEGRAM_TIMEOUT,
            error_summary="Telegram request timed out.",
        )
        assert failed.error_code is ErrorCode.TELEGRAM_TIMEOUT

    async with transaction_scope(session_factory) as session:
        await DigestRepository(session).transition_to(
            digest.id,
            DigestStatus.SENDING,
            occurred_at=CREATED_AT + timedelta(seconds=3),
        )

    sent_at = CREATED_AT + timedelta(seconds=4)

    async with transaction_scope(session_factory) as session:
        await DigestRepository(session).transition_to(
            digest.id,
            DigestStatus.SENT,
            occurred_at=sent_at,
        )

    async with transaction_scope(session_factory) as session:
        stored = await DigestRepository(session).get(digest.id)
        assert stored == replace(digest, status=DigestStatus.SENT, sent_at=sent_at)


async def test_missing_digest_reads(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Return None when no digest matches the requested ID or run."""
    async with transaction_scope(session_factory) as session:
        repository = DigestRepository(session)
        assert await repository.get(uuid4()) is None
        assert await repository.get_by_run(uuid4()) is None
        assert await repository.get_latest() is None
