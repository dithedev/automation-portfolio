from copy import deepcopy
from dataclasses import FrozenInstanceError
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.domain import (
    Digest,
    DigestItem,
    DigestStatus,
    ErrorCode,
    InvalidStateTransitionError,
)

CREATED_AT = datetime(2026, 9, 10, 8, 0, tzinfo=UTC)
EVENT_AT = CREATED_AT + timedelta(seconds=5)

VALID_SUMMARY = (
    "The selected article reports a concrete product or tooling update "
    "with clear implications for automation-focused teams."
)


def make_digest_item(
    *,
    position: int = 1,
    news_item_id: UUID | None = None,
    relevance_score: Decimal = Decimal("0.900"),
    summary: str = VALID_SUMMARY,
) -> DigestItem:
    return DigestItem(
        news_item_id=news_item_id if news_item_id is not None else uuid4(),
        position=position,
        summary=summary,
        tag="PRODUCT",
        relevance_score=relevance_score,
        selection_reason="Highly relevant product update.",
    )


def make_digest(
    *,
    items: tuple[DigestItem, ...] | None = None,
    model: str = "gpt-4o-mini",
    status: DigestStatus = DigestStatus.GENERATED,
    sent_at: datetime | None = None,
    error_code: ErrorCode | None = None,
    error_summary: str | None = None,
) -> Digest:
    return Digest(
        run_id=uuid4(),
        digest_date=date(2026, 9, 10),
        title="AI & Automation Daily Digest",
        rendered_text="1. A useful AI update.",
        prompt_version="v1",
        items=items if items is not None else (make_digest_item(),),
        model=model,
        status=status,
        created_at=CREATED_AT,
        sent_at=sent_at,
        error_code=error_code,
        error_summary=error_summary,
    )


def test_digest_item_normalizes_text() -> None:
    item = make_digest_item(summary=f"  {VALID_SUMMARY}  ")

    assert item.tag == "PRODUCT"
    assert item.summary == VALID_SUMMARY


def test_digest_item_is_immutable() -> None:
    item = make_digest_item()

    with pytest.raises(FrozenInstanceError):
        item.summary = "Replacement"


@pytest.mark.parametrize("position", [0, 8])
def test_digest_item_rejects_invalid_position(position: int) -> None:
    with pytest.raises(ValueError, match="position must be between"):
        make_digest_item(position=position)


@pytest.mark.parametrize("position", [True, 1.5, "1"])
def test_digest_item_rejects_non_integer_position(position: Any) -> None:
    with pytest.raises(TypeError, match="must be an integer"):
        make_digest_item(position=position)


@pytest.mark.parametrize(
    "relevance_score",
    [
        Decimal("-0.001"),
        Decimal("1.001"),
        Decimal("NaN"),
        Decimal("Infinity"),
    ],
)
def test_digest_item_rejects_invalid_relevance(
    relevance_score: Decimal,
) -> None:
    with pytest.raises(ValueError, match="between 0 and 1"):
        make_digest_item(relevance_score=relevance_score)


@pytest.mark.parametrize("relevance_score", [Decimal("0"), Decimal("1")])
def test_digest_item_accepts_relevance_boundaries(
    relevance_score: Decimal,
) -> None:
    item = make_digest_item(relevance_score=relevance_score)

    assert item.relevance_score == relevance_score


@pytest.mark.parametrize("summary", ["", "   ", "a" * 79, "a" * 281])
def test_digest_item_rejects_invalid_summary(summary: str) -> None:
    with pytest.raises(ValueError, match="Digest item summary"):
        make_digest_item(summary=summary)


def test_digest_starts_generated() -> None:
    digest = make_digest()

    assert digest.status is DigestStatus.GENERATED
    assert digest.sent_at is None
    assert digest.error_code is None


def test_digest_rejects_unexpected_model() -> None:
    with pytest.raises(ValueError, match="must be gpt-4o-mini"):
        make_digest(model="gpt-4.1")


@pytest.mark.parametrize("count", [0, 8])
def test_digest_rejects_invalid_item_count(count: int) -> None:
    items = tuple(make_digest_item(position=(index % 7) + 1) for index in range(count))

    with pytest.raises(ValueError, match="between 1 and 7 items"):
        make_digest(items=items)


def test_digest_requires_consecutive_positions() -> None:
    with pytest.raises(ValueError, match="consecutive"):
        make_digest(items=(make_digest_item(position=2),))


def test_digest_rejects_duplicate_positions() -> None:
    with pytest.raises(ValueError, match="positions must be unique"):
        make_digest(
            items=(make_digest_item(), make_digest_item()),
        )


def test_digest_rejects_duplicate_news_items() -> None:
    news_item_id = uuid4()

    with pytest.raises(ValueError, match="news items must be unique"):
        make_digest(
            items=(
                make_digest_item(position=1, news_item_id=news_item_id),
                make_digest_item(position=2, news_item_id=news_item_id),
            ),
        )


def test_digest_can_be_sent() -> None:
    digest = make_digest()

    digest.transition_to(DigestStatus.SENDING, occurred_at=EVENT_AT)
    digest.transition_to(DigestStatus.SENT, occurred_at=EVENT_AT)

    assert digest.status is DigestStatus.SENT
    assert digest.sent_at == EVENT_AT
    assert digest.error_code is None
    assert digest.error_summary is None


def test_failed_digest_requires_error_code() -> None:
    digest = make_digest()
    digest.transition_to(DigestStatus.SENDING, occurred_at=EVENT_AT)
    before = deepcopy(digest)

    with pytest.raises(ValueError, match="requires error_code"):
        digest.transition_to(DigestStatus.FAILED, occurred_at=EVENT_AT)

    assert digest == before


def test_failed_digest_can_be_retried_and_sent() -> None:
    digest = make_digest()

    digest.transition_to(DigestStatus.SENDING, occurred_at=EVENT_AT)
    digest.transition_to(
        DigestStatus.FAILED,
        occurred_at=EVENT_AT,
        error_code=ErrorCode.TELEGRAM_TIMEOUT,
        error_summary="  Telegram request timed out  ",
    )

    assert digest.error_code is ErrorCode.TELEGRAM_TIMEOUT
    assert digest.error_summary == "Telegram request timed out"

    digest.transition_to(DigestStatus.SENDING, occurred_at=EVENT_AT)

    assert digest.error_code is None
    assert digest.error_summary is None

    digest.transition_to(DigestStatus.SENT, occurred_at=EVENT_AT)

    assert digest.status is DigestStatus.SENT
    assert digest.sent_at == EVENT_AT


@pytest.mark.parametrize("error_code", ["   ", "UNKNOWN_ERROR", "A" * 65])
def test_invalid_failure_code_preserves_digest(error_code: Any) -> None:
    digest = make_digest()
    digest.transition_to(DigestStatus.SENDING, occurred_at=EVENT_AT)
    before = deepcopy(digest)

    with pytest.raises(ValueError):
        digest.transition_to(
            DigestStatus.FAILED,
            occurred_at=EVENT_AT,
            error_code=error_code,
        )

    assert digest == before


def test_long_failure_summary_preserves_digest() -> None:
    digest = make_digest()
    digest.transition_to(DigestStatus.SENDING, occurred_at=EVENT_AT)
    before = deepcopy(digest)

    with pytest.raises(ValueError, match="must not exceed 500"):
        digest.transition_to(
            DigestStatus.FAILED,
            occurred_at=EVENT_AT,
            error_code=ErrorCode.TELEGRAM_TIMEOUT,
            error_summary="a" * 501,
        )

    assert digest == before


def test_blank_failure_summary_becomes_none() -> None:
    digest = make_digest()
    digest.transition_to(DigestStatus.SENDING, occurred_at=EVENT_AT)

    digest.transition_to(
        DigestStatus.FAILED,
        occurred_at=EVENT_AT,
        error_code=ErrorCode.TELEGRAM_TIMEOUT,
        error_summary="   ",
    )

    assert digest.error_summary is None


@pytest.mark.parametrize(
    "target_status",
    [DigestStatus.SENDING, DigestStatus.SENT],
)
def test_non_failed_transition_rejects_error_data(
    target_status: DigestStatus,
) -> None:
    digest = make_digest()

    if target_status is DigestStatus.SENT:
        digest.transition_to(DigestStatus.SENDING, occurred_at=EVENT_AT)

    before = deepcopy(digest)

    with pytest.raises(ValueError, match="Only failed digest"):
        digest.transition_to(
            target_status,
            occurred_at=EVENT_AT,
            error_summary="Unexpected error",
        )

    assert digest == before


@pytest.mark.parametrize(
    "occurred_at",
    [
        datetime(2026, 9, 10, 8, 0),
        CREATED_AT - timedelta(seconds=1),
    ],
)
def test_invalid_transition_time_preserves_digest(
    occurred_at: datetime,
) -> None:
    digest = make_digest()
    before = deepcopy(digest)

    with pytest.raises(ValueError):
        digest.transition_to(
            DigestStatus.SENDING,
            occurred_at=occurred_at,
        )

    assert digest == before


def test_sent_digest_is_terminal() -> None:
    digest = make_digest()
    digest.transition_to(DigestStatus.SENDING, occurred_at=EVENT_AT)
    digest.transition_to(DigestStatus.SENT, occurred_at=EVENT_AT)
    before = deepcopy(digest)

    with pytest.raises(
        InvalidStateTransitionError,
        match="Invalid digest state transition",
    ):
        digest.transition_to(DigestStatus.SENDING, occurred_at=EVENT_AT)

    assert digest == before


def test_sent_digest_requires_sent_at() -> None:
    with pytest.raises(ValueError, match="must have sent_at"):
        make_digest(status=DigestStatus.SENT)


def test_non_sent_digest_rejects_sent_at() -> None:
    with pytest.raises(ValueError, match="Only sent digest"):
        make_digest(sent_at=EVENT_AT)


def test_sent_at_cannot_precede_creation() -> None:
    with pytest.raises(ValueError, match="must not be before created_at"):
        make_digest(
            status=DigestStatus.SENT,
            sent_at=CREATED_AT - timedelta(seconds=1),
        )


def test_initial_failed_digest_requires_error_code() -> None:
    with pytest.raises(ValueError, match="requires error_code"):
        make_digest(status=DigestStatus.FAILED)


def test_initial_failed_digest_normalizes_summary() -> None:
    digest = make_digest(
        status=DigestStatus.FAILED,
        error_code=ErrorCode.TELEGRAM_TIMEOUT,
        error_summary="  Telegram request timed out  ",
    )

    assert digest.error_code is ErrorCode.TELEGRAM_TIMEOUT
    assert digest.error_summary == "Telegram request timed out"


def test_generated_digest_rejects_error_data() -> None:
    with pytest.raises(ValueError, match="Only failed digest"):
        make_digest(error_code=ErrorCode.TELEGRAM_TIMEOUT)


def test_digest_repr_excludes_error_summary() -> None:
    digest = make_digest(
        status=DigestStatus.FAILED,
        error_code=ErrorCode.TELEGRAM_TIMEOUT,
        error_summary="Operational failure details",
    )

    assert "Operational failure details" not in repr(digest)


def test_digest_public_api_has_docstrings() -> None:
    assert DigestItem.__doc__
    assert Digest.__doc__
    assert Digest.transition_to.__doc__
