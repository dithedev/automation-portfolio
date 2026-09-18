from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest

from app.domain import (
    DeliveryAttempt,
    DeliveryStatus,
    DigestStatus,
    FeedFetch,
    FeedFetchStatus,
)
from app.domain.enum_validation import ensure_enum_member

TIMESTAMP = datetime(2026, 9, 10, 8, 0, tzinfo=UTC)


def make_fetch() -> FeedFetch:
    return FeedFetch(
        run_id=uuid4(),
        source_id=uuid4(),
        status=FeedFetchStatus.SUCCESS,
        started_at=TIMESTAMP,
        finished_at=TIMESTAMP,
        http_status=200,
    )


def make_attempt() -> DeliveryAttempt:
    return DeliveryAttempt(
        digest_id=uuid4(),
        part_number=1,
        attempt_number=1,
        started_at=TIMESTAMP,
    )


@pytest.mark.parametrize("status", list(FeedFetchStatus))
def test_enum_validator_returns_original_member(
    status: FeedFetchStatus,
) -> None:
    assert ensure_enum_member(status, FeedFetchStatus, "status") is status


@pytest.mark.parametrize(
    "status",
    ["success", "failed", "not_modified", "", None, True, 1],
)
def test_enum_validator_rejects_non_members(status: Any) -> None:
    with pytest.raises(TypeError, match="must be a member of FeedFetchStatus"):
        ensure_enum_member(status, FeedFetchStatus, "status")


def test_enum_validator_rejects_member_of_another_enum() -> None:
    with pytest.raises(TypeError, match="FeedFetchStatus"):
        ensure_enum_member(
            DeliveryStatus.FAILED,
            FeedFetchStatus,
            "status",
        )


@pytest.mark.parametrize("status", [member.value for member in FeedFetchStatus])
def test_feed_fetch_rejects_raw_string_status(status: Any) -> None:
    with pytest.raises(TypeError, match="FeedFetchStatus"):
        replace(make_fetch(), status=status)


def test_feed_fetch_rejects_success_string_with_http_500() -> None:
    status: Any = "success"

    with pytest.raises(TypeError, match="FeedFetchStatus"):
        replace(
            make_fetch(),
            status=status,
            http_status=500,
        )


@pytest.mark.parametrize("status", [member.value for member in DeliveryStatus])
def test_delivery_attempt_rejects_raw_string_status(status: Any) -> None:
    with pytest.raises(TypeError, match="DeliveryStatus"):
        replace(make_attempt(), status=status)


def test_delivery_rejects_sent_string_without_success_result() -> None:
    status: Any = "sent"

    with pytest.raises(TypeError, match="DeliveryStatus"):
        replace(
            make_attempt(),
            status=status,
            http_status=500,
            finished_at=TIMESTAMP,
            telegram_message_id=None,
        )


def test_delivery_rejects_different_enum_with_matching_value() -> None:
    status: Any = DigestStatus.SENT

    assert status == DeliveryStatus.SENT

    with pytest.raises(TypeError, match="DeliveryStatus"):
        replace(make_attempt(), status=status)


def test_feed_fetch_rejects_different_enum_with_matching_value() -> None:
    status: Any = DeliveryStatus.FAILED

    assert status == FeedFetchStatus.FAILED

    with pytest.raises(TypeError, match="FeedFetchStatus"):
        replace(
            make_fetch(),
            status=status,
        )


def test_enum_validator_has_docstring() -> None:
    assert ensure_enum_member.__doc__
