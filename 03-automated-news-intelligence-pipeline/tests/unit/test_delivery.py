from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.domain import DeliveryAttempt, DeliveryStatus, ErrorCode

STARTED_AT = datetime(2026, 9, 10, 8, 0, tzinfo=UTC)
FINISHED_AT = STARTED_AT + timedelta(seconds=1)


def make_attempt() -> DeliveryAttempt:
    from uuid import uuid4

    return DeliveryAttempt(
        digest_id=uuid4(),
        part_number=1,
        attempt_number=1,
        started_at=STARTED_AT,
    )


def test_delivery_attempt_starts_pending() -> None:
    attempt = make_attempt()

    assert attempt.status is DeliveryStatus.PENDING
    assert attempt.finished_at is None
    assert attempt.telegram_message_id is None
    assert attempt.error_code is None


@pytest.mark.parametrize("field_name", ["part_number", "attempt_number"])
@pytest.mark.parametrize("value", [0, -1])
def test_delivery_rejects_invalid_numbering(
    field_name: str,
    value: int,
) -> None:
    with pytest.raises(ValueError):
        replace(make_attempt(), **{field_name: value})


@pytest.mark.parametrize("value", [True, 1.5, "1"])
def test_delivery_rejects_non_integer_numbering(value: Any) -> None:
    with pytest.raises(TypeError, match="must be an integer"):
        replace(make_attempt(), part_number=value)


def test_delivery_attempt_can_be_marked_sent() -> None:
    attempt = make_attempt()
    attempt_id = attempt.id

    attempt.mark_sent(
        telegram_message_id=123456,
        finished_at=FINISHED_AT,
    )

    assert attempt.id == attempt_id
    assert attempt.status is DeliveryStatus.SENT
    assert attempt.telegram_message_id == 123456
    assert attempt.http_status == 200
    assert attempt.finished_at == FINISHED_AT
    assert attempt.error_code is None
    assert attempt.retry_after_seconds is None


@pytest.mark.parametrize("http_status", [200, 299])
def test_sent_delivery_accepts_success_http_boundaries(
    http_status: int,
) -> None:
    attempt = make_attempt()

    attempt.mark_sent(
        telegram_message_id=123456,
        http_status=http_status,
        finished_at=FINISHED_AT,
    )

    assert attempt.http_status == http_status


@pytest.mark.parametrize("http_status", [199, 300, 429, 500, 999])
def test_invalid_sent_http_status_preserves_state(
    http_status: int,
) -> None:
    attempt = make_attempt()
    before = deepcopy(attempt)

    with pytest.raises(ValueError):
        attempt.mark_sent(
            telegram_message_id=123456,
            http_status=http_status,
            finished_at=FINISHED_AT,
        )

    assert attempt == before


@pytest.mark.parametrize("message_id", [0, -1])
def test_invalid_message_id_preserves_state(message_id: int) -> None:
    attempt = make_attempt()
    before = deepcopy(attempt)

    with pytest.raises(ValueError):
        attempt.mark_sent(
            telegram_message_id=message_id,
            finished_at=FINISHED_AT,
        )

    assert attempt == before


@pytest.mark.parametrize("message_id", [True, 1.5, "123"])
def test_non_integer_message_id_preserves_state(message_id: Any) -> None:
    attempt = make_attempt()
    before = deepcopy(attempt)

    with pytest.raises(TypeError):
        attempt.mark_sent(
            telegram_message_id=message_id,
            finished_at=FINISHED_AT,
        )

    assert attempt == before


def test_delivery_attempt_can_be_marked_failed() -> None:
    attempt = make_attempt()

    attempt.mark_failed(
        error_code=ErrorCode.TELEGRAM_RATE_LIMITED,
        error_summary="  Telegram rate limit exceeded  ",
        http_status=429,
        retry_after_seconds=10,
        finished_at=FINISHED_AT,
    )

    assert attempt.status is DeliveryStatus.FAILED
    assert attempt.error_code is ErrorCode.TELEGRAM_RATE_LIMITED
    assert attempt.error_summary == "Telegram rate limit exceeded"
    assert attempt.http_status == 429
    assert attempt.retry_after_seconds == 10
    assert attempt.telegram_message_id is None
    assert attempt.finished_at == FINISHED_AT


def test_failed_delivery_accepts_absent_http_status() -> None:
    attempt = make_attempt()

    attempt.mark_failed(
        error_code=ErrorCode.TELEGRAM_TIMEOUT,
        finished_at=FINISHED_AT,
    )

    assert attempt.http_status is None


def test_failed_delivery_normalizes_blank_summary() -> None:
    attempt = make_attempt()

    attempt.mark_failed(
        error_code=ErrorCode.TELEGRAM_TIMEOUT,
        error_summary="   ",
        finished_at=FINISHED_AT,
    )

    assert attempt.error_summary is None


@pytest.mark.parametrize("error_code", ["", "   ", "UNKNOWN", "A" * 65])
def test_invalid_failure_code_preserves_state(error_code: Any) -> None:
    attempt = make_attempt()
    before = deepcopy(attempt)

    with pytest.raises(ValueError):
        attempt.mark_failed(
            error_code=error_code,
            finished_at=FINISHED_AT,
        )

    assert attempt == before


def test_long_failure_summary_preserves_state() -> None:
    attempt = make_attempt()
    before = deepcopy(attempt)

    with pytest.raises(ValueError, match="must not exceed 500"):
        attempt.mark_failed(
            error_code=ErrorCode.TELEGRAM_TIMEOUT,
            error_summary="a" * 501,
            finished_at=FINISHED_AT,
        )

    assert attempt == before


@pytest.mark.parametrize("http_status", [99, 600])
def test_invalid_failed_http_status_preserves_state(
    http_status: int,
) -> None:
    attempt = make_attempt()
    before = deepcopy(attempt)

    with pytest.raises(ValueError, match="between 100 and 599"):
        attempt.mark_failed(
            error_code=ErrorCode.TELEGRAM_PERMANENT_FAILURE,
            http_status=http_status,
            finished_at=FINISHED_AT,
        )

    assert attempt == before


def test_negative_retry_after_preserves_state() -> None:
    attempt = make_attempt()
    before = deepcopy(attempt)

    with pytest.raises(ValueError, match="must not be negative"):
        attempt.mark_failed(
            error_code=ErrorCode.TELEGRAM_RATE_LIMITED,
            retry_after_seconds=-1,
            finished_at=FINISHED_AT,
        )

    assert attempt == before


@pytest.mark.parametrize(
    "finished_at",
    [
        datetime(2026, 9, 10, 8, 0),
        STARTED_AT - timedelta(seconds=1),
    ],
)
@pytest.mark.parametrize("result", ["sent", "failed"])
def test_invalid_completion_time_preserves_state(
    finished_at: datetime,
    result: str,
) -> None:
    attempt = make_attempt()
    before = deepcopy(attempt)

    with pytest.raises(ValueError):
        if result == "sent":
            attempt.mark_sent(
                telegram_message_id=123456,
                finished_at=finished_at,
            )
        else:
            attempt.mark_failed(
                error_code=ErrorCode.TELEGRAM_TIMEOUT,
                finished_at=finished_at,
            )

    assert attempt == before


@pytest.mark.parametrize("initial_result", ["sent", "failed"])
@pytest.mark.parametrize("next_result", ["sent", "failed"])
def test_completed_attempt_cannot_be_overwritten(
    initial_result: str,
    next_result: str,
) -> None:
    attempt = make_attempt()

    if initial_result == "sent":
        attempt.mark_sent(
            telegram_message_id=123456,
            finished_at=FINISHED_AT,
        )
    else:
        attempt.mark_failed(
            error_code=ErrorCode.TELEGRAM_TIMEOUT,
            finished_at=FINISHED_AT,
        )

    before = deepcopy(attempt)

    with pytest.raises(ValueError, match="Only pending delivery attempt"):
        if next_result == "sent":
            attempt.mark_sent(
                telegram_message_id=654321,
                finished_at=FINISHED_AT,
            )
        else:
            attempt.mark_failed(
                error_code=ErrorCode.TELEGRAM_TIMEOUT,
                finished_at=FINISHED_AT,
            )

    assert attempt == before


def test_pending_attempt_rejects_result_data() -> None:
    with pytest.raises(ValueError, match="must not have result data"):
        replace(make_attempt(), http_status=200)


def test_completed_attempt_requires_finished_at() -> None:
    with pytest.raises(ValueError, match="must have finished_at"):
        replace(
            make_attempt(),
            status=DeliveryStatus.SENT,
            telegram_message_id=123456,
            http_status=200,
        )


def test_sent_attempt_requires_message_id() -> None:
    with pytest.raises(ValueError, match="must have telegram_message_id"):
        replace(
            make_attempt(),
            status=DeliveryStatus.SENT,
            http_status=200,
            finished_at=FINISHED_AT,
        )


def test_sent_attempt_rejects_retry_data() -> None:
    with pytest.raises(ValueError, match="error or retry information"):
        replace(
            make_attempt(),
            status=DeliveryStatus.SENT,
            telegram_message_id=123456,
            http_status=200,
            retry_after_seconds=1,
            finished_at=FINISHED_AT,
        )


def test_initial_failed_attempt_requires_error_code() -> None:
    with pytest.raises(ValueError, match="requires error_code"):
        replace(
            make_attempt(),
            status=DeliveryStatus.FAILED,
            finished_at=FINISHED_AT,
        )


def test_failed_attempt_rejects_message_id() -> None:
    with pytest.raises(ValueError, match="must not have telegram_message_id"):
        replace(
            make_attempt(),
            status=DeliveryStatus.FAILED,
            telegram_message_id=123456,
            error_code=ErrorCode.TELEGRAM_TIMEOUT,
            finished_at=FINISHED_AT,
        )


def test_delivery_repr_excludes_error_summary() -> None:
    attempt = make_attempt()
    attempt.mark_failed(
        error_code=ErrorCode.TELEGRAM_TIMEOUT,
        error_summary="Operational failure details",
        finished_at=FINISHED_AT,
    )

    assert "Operational failure details" not in repr(attempt)


def test_delivery_public_api_has_docstrings() -> None:
    assert DeliveryAttempt.__doc__
    assert DeliveryAttempt.mark_sent.__doc__
    assert DeliveryAttempt.mark_failed.__doc__
