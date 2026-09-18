"""PostgreSQL integration checks for delivery attempt history."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain import (
    DeliveryAttempt,
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
from app.infrastructure.db.repositories import (
    DeliveryAttemptRepository,
    DigestRepository,
    NewsItemRepository,
    PipelineRunRepository,
    SourceRepository,
)
from app.infrastructure.db.session import transaction_scope
from app.texts.db import (
    ATTEMPT_IDENTITY_MISMATCH,
    ATTEMPT_NOT_FOUND,
    ATTEMPT_TERMINAL_UPDATE_FORBIDDEN,
)

STARTED_AT = datetime(2026, 9, 14, 8, 0, tzinfo=UTC)


async def prepare_digest(
    session_factory: async_sessionmaker[AsyncSession],
) -> UUID:
    """Commit a generated digest for delivery persistence tests."""
    run = PipelineRun(
        trigger_type=TriggerType.MANUAL,
        app_version="0.1.0",
        started_at=STARTED_AT,
    )
    source = Source(
        key="example-feed",
        name="Example Feed",
        feed_url="https://example.com/feed.xml",
        allowed_host="example.com",
        category="artificial_intelligence",
    )
    url = "https://example.com/article"
    article = NewsItem(
        source_id=source.id,
        original_url=url,
        canonical_url=url,
        url_hash=sha256(url.encode()).hexdigest(),
        title="Product update",
        normalized_title="product update",
        sanitized_summary="A factual product update.",
        content_hash=sha256(b"A factual product update.").hexdigest(),
        collected_at=STARTED_AT,
        status=NewsItemStatus.CANDIDATE,
    )
    digest = Digest(
        run_id=run.id,
        digest_date=date(2026, 9, 14),
        title="Daily Digest",
        rendered_text="A rendered product update.",
        prompt_version="v1",
        created_at=STARTED_AT,
        items=(
            DigestItem(
                news_item_id=article.id,
                position=1,
                summary=(
                    "The supplied article describes a product update with "
                    "practical implications for developers and automation teams."
                ),
                tag="PRODUCT",
                relevance_score=Decimal("0.900"),
                selection_reason="Relevant product update.",
            ),
        ),
    )

    async with transaction_scope(session_factory) as session:
        await PipelineRunRepository(session).add(run)
        await SourceRepository(session).add(source)
        await NewsItemRepository(session).add_if_new(article)
        await DigestRepository(session).create_generated(digest)

    return digest.id


def make_attempt(digest_id: UUID, number: int = 1) -> DeliveryAttempt:
    """Create a pending attempt with a deterministic start time."""
    return DeliveryAttempt(
        digest_id=digest_id,
        part_number=1,
        attempt_number=number,
        started_at=STARTED_AT,
    )


async def test_sent_attempt_round_trip(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Persist a pending attempt and its successful response metadata."""
    digest_id = await prepare_digest(session_factory)
    attempt = make_attempt(digest_id)

    async with transaction_scope(session_factory) as session:
        assert await DeliveryAttemptRepository(session).add(attempt) == attempt

    attempt.mark_sent(
        telegram_message_id=123456,
        finished_at=STARTED_AT + timedelta(seconds=1),
    )

    async with transaction_scope(session_factory) as session:
        assert await DeliveryAttemptRepository(session).save(attempt) == attempt

    async with transaction_scope(session_factory) as session:
        repository = DeliveryAttemptRepository(session)
        assert await repository.get(attempt.id) == attempt
        assert await repository.list_for_digest(digest_id) == (attempt,)


async def test_retry_retains_failed_attempt(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Keep failure metadata when a new attempt succeeds."""
    digest_id = await prepare_digest(session_factory)
    first = make_attempt(digest_id)
    first.mark_failed(
        error_code=ErrorCode.TELEGRAM_RATE_LIMITED,
        error_summary="Telegram rate limit exceeded.",
        http_status=429,
        retry_after_seconds=10,
        finished_at=STARTED_AT + timedelta(seconds=1),
    )
    second = make_attempt(digest_id, number=2)
    second.mark_sent(
        telegram_message_id=654321,
        finished_at=STARTED_AT + timedelta(seconds=12),
    )

    async with transaction_scope(session_factory) as session:
        repository = DeliveryAttemptRepository(session)
        await repository.add(second)
        await repository.add(first)

    async with transaction_scope(session_factory) as session:
        history = await DeliveryAttemptRepository(session).list_for_digest(digest_id)
        assert history == (first, second)


async def test_completed_attempt_cannot_be_rewritten(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Allow identical terminal saves and reject replacement message IDs."""
    digest_id = await prepare_digest(session_factory)
    attempt = make_attempt(digest_id)
    attempt.mark_sent(
        telegram_message_id=123456,
        finished_at=STARTED_AT + timedelta(seconds=1),
    )

    async with transaction_scope(session_factory) as session:
        await DeliveryAttemptRepository(session).add(attempt)

    async with transaction_scope(session_factory) as session:
        assert await DeliveryAttemptRepository(session).save(attempt) == attempt

    changed = replace(attempt, telegram_message_id=654321)

    with pytest.raises(ValueError) as error:
        async with transaction_scope(session_factory) as session:
            await DeliveryAttemptRepository(session).save(changed)

    assert str(error.value) == ATTEMPT_TERMINAL_UPDATE_FORBIDDEN

    async with transaction_scope(session_factory) as session:
        assert await DeliveryAttemptRepository(session).get(attempt.id) == attempt


@pytest.mark.parametrize(
    "changes",
    [
        {"digest_id": uuid4()},
        {"part_number": 2},
        {"attempt_number": 2},
        {"started_at": STARTED_AT + timedelta(seconds=1)},
    ],
    ids=["digest-id", "part-number", "attempt-number", "started-at"],
)
async def test_attempt_identity_is_immutable(
    session_factory: async_sessionmaker[AsyncSession],
    changes: dict[str, object],
) -> None:
    """Reject changes to attempt ownership, numbering, or start time."""
    digest_id = await prepare_digest(session_factory)
    attempt = make_attempt(digest_id)

    async with transaction_scope(session_factory) as session:
        await DeliveryAttemptRepository(session).add(attempt)

    with pytest.raises(ValueError) as error:
        async with transaction_scope(session_factory) as session:
            await DeliveryAttemptRepository(session).save(replace(attempt, **changes))

    assert str(error.value) == ATTEMPT_IDENTITY_MISMATCH


async def test_duplicate_numbering_is_rejected(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Require unique attempt numbering within each digest part."""
    digest_id = await prepare_digest(session_factory)
    attempt = make_attempt(digest_id)

    async with transaction_scope(session_factory) as session:
        await DeliveryAttemptRepository(session).add(attempt)

    with pytest.raises(IntegrityError):
        async with transaction_scope(session_factory) as session:
            await DeliveryAttemptRepository(session).add(replace(attempt, id=uuid4()))

    async with transaction_scope(session_factory) as session:
        assert await DeliveryAttemptRepository(session).list_for_digest(digest_id) == (attempt,)


async def test_missing_attempt_reads_and_save(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Return empty reads and reject saving an unknown attempt."""
    async with transaction_scope(session_factory) as session:
        repository = DeliveryAttemptRepository(session)
        assert await repository.get(uuid4()) is None
        assert await repository.list_for_digest(uuid4()) == ()

    with pytest.raises(LookupError) as error:
        async with transaction_scope(session_factory) as session:
            await DeliveryAttemptRepository(session).save(make_attempt(uuid4()))

    assert str(error.value) == ATTEMPT_NOT_FOUND


async def test_attempt_requires_existing_digest(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Reject an attempt referring to a missing digest."""
    with pytest.raises(IntegrityError):
        async with transaction_scope(session_factory) as session:
            await DeliveryAttemptRepository(session).add(make_attempt(uuid4()))


async def test_message_id_and_digest_status_roll_back_together(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Roll back delivery confirmation and digest completion atomically."""
    digest_id = await prepare_digest(session_factory)
    pending = make_attempt(digest_id)

    async with transaction_scope(session_factory) as session:
        await DeliveryAttemptRepository(session).add(pending)
        await DigestRepository(session).transition_to(
            digest_id,
            DigestStatus.SENDING,
            occurred_at=STARTED_AT,
        )

    completed = replace(pending)
    completed.mark_sent(
        telegram_message_id=123456,
        finished_at=STARTED_AT + timedelta(seconds=1),
    )

    with pytest.raises(RuntimeError):
        async with transaction_scope(session_factory) as session:
            await DeliveryAttemptRepository(session).save(completed)
            await DigestRepository(session).transition_to(
                digest_id,
                DigestStatus.SENT,
                occurred_at=STARTED_AT + timedelta(seconds=1),
            )
            raise RuntimeError

    async with transaction_scope(session_factory) as session:
        assert await DeliveryAttemptRepository(session).get(pending.id) == pending
        digest = await DigestRepository(session).get(digest_id)
        assert digest is not None
        assert digest.status is DigestStatus.SENDING
        assert digest.sent_at is None
