from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest

from app.domain import ErrorCode, FeedFetch, FeedFetchStatus

STARTED_AT = datetime(2026, 9, 10, 8, 0, tzinfo=UTC)
FINISHED_AT = STARTED_AT + timedelta(milliseconds=250)


def make_fetch() -> FeedFetch:
    return FeedFetch(
        run_id=uuid4(),
        source_id=uuid4(),
        status=FeedFetchStatus.SUCCESS,
        started_at=STARTED_AT,
        finished_at=FINISHED_AT,
        http_status=200,
        entries_count=5,
        duration_ms=250,
    )


def test_successful_feed_fetch_accepts_valid_data() -> None:
    fetch = make_fetch()

    assert fetch.status is FeedFetchStatus.SUCCESS
    assert fetch.http_status == 200
    assert fetch.entries_count == 5
    assert fetch.duration_ms == 250
    assert fetch.error_code is None
    assert fetch.error_summary is None


@pytest.mark.parametrize("http_status", [200, 299])
def test_success_accepts_http_boundaries(http_status: int) -> None:
    fetch = replace(make_fetch(), http_status=http_status)

    assert fetch.http_status == http_status


@pytest.mark.parametrize("http_status", [None, 199, 300, 304, 500])
def test_success_rejects_non_success_http_status(
    http_status: int | None,
) -> None:
    with pytest.raises(ValueError, match="between 200 and 299"):
        replace(make_fetch(), http_status=http_status)


def test_not_modified_fetch_accepts_http_304() -> None:
    fetch = replace(
        make_fetch(),
        status=FeedFetchStatus.NOT_MODIFIED,
        http_status=304,
        entries_count=0,
    )

    assert fetch.status is FeedFetchStatus.NOT_MODIFIED
    assert fetch.entries_count == 0
    assert fetch.error_code is None


@pytest.mark.parametrize("http_status", [None, 200, 302])
def test_not_modified_requires_http_304(
    http_status: int | None,
) -> None:
    with pytest.raises(ValueError, match="requires HTTP 304"):
        replace(
            make_fetch(),
            status=FeedFetchStatus.NOT_MODIFIED,
            http_status=http_status,
            entries_count=0,
        )


def test_not_modified_rejects_entries() -> None:
    with pytest.raises(ValueError, match="zero entries"):
        replace(
            make_fetch(),
            status=FeedFetchStatus.NOT_MODIFIED,
            http_status=304,
            entries_count=1,
        )


def test_failed_fetch_accepts_controlled_error() -> None:
    fetch = replace(
        make_fetch(),
        status=FeedFetchStatus.FAILED,
        http_status=None,
        entries_count=0,
        error_code=ErrorCode.FEED_TIMEOUT,
        error_summary="  Feed request timed out  ",
    )

    assert fetch.error_code is ErrorCode.FEED_TIMEOUT
    assert fetch.error_summary == "Feed request timed out"
    assert fetch.http_status is None


def test_failed_fetch_can_store_http_error_status() -> None:
    fetch = replace(
        make_fetch(),
        status=FeedFetchStatus.FAILED,
        http_status=503,
        entries_count=0,
        error_code=ErrorCode.FEED_CONNECTION_FAILED,
    )

    assert fetch.http_status == 503


def test_failed_fetch_requires_error_code() -> None:
    with pytest.raises(ValueError, match="requires error_code"):
        replace(
            make_fetch(),
            status=FeedFetchStatus.FAILED,
        )


@pytest.mark.parametrize("error_code", ["", "   ", "UNKNOWN", "A" * 65])
def test_failed_fetch_rejects_invalid_error_code(error_code: Any) -> None:
    with pytest.raises(ValueError):
        replace(
            make_fetch(),
            status=FeedFetchStatus.FAILED,
            error_code=error_code,
        )


def test_failed_fetch_normalizes_blank_summary() -> None:
    fetch = replace(
        make_fetch(),
        status=FeedFetchStatus.FAILED,
        error_code=ErrorCode.FEED_PARSE_FAILED,
        error_summary="   ",
    )

    assert fetch.error_summary is None


def test_failed_fetch_rejects_long_summary() -> None:
    with pytest.raises(ValueError, match="must not exceed 500"):
        replace(
            make_fetch(),
            status=FeedFetchStatus.FAILED,
            error_code=ErrorCode.FEED_PARSE_FAILED,
            error_summary="a" * 501,
        )


@pytest.mark.parametrize(
    "status",
    [FeedFetchStatus.SUCCESS, FeedFetchStatus.NOT_MODIFIED],
)
@pytest.mark.parametrize(
    ("error_code", "error_summary"),
    [
        (ErrorCode.FEED_TIMEOUT, None),
        (None, "Unexpected error"),
        (None, "   "),
    ],
)
def test_non_failed_fetch_rejects_error_information(
    status: FeedFetchStatus,
    error_code: ErrorCode | None,
    error_summary: str | None,
) -> None:
    with pytest.raises(ValueError, match="Only failed feed fetch"):
        replace(
            make_fetch(),
            status=status,
            http_status=304 if status is FeedFetchStatus.NOT_MODIFIED else 200,
            entries_count=0,
            error_code=error_code,
            error_summary=error_summary,
        )


@pytest.mark.parametrize("field_name", ["entries_count", "duration_ms"])
def test_fetch_rejects_negative_counters(field_name: str) -> None:
    with pytest.raises(ValueError, match="must not be negative"):
        replace(make_fetch(), **{field_name: -1})


@pytest.mark.parametrize("value", [True, 1.5, "1"])
def test_fetch_rejects_non_integer_entries(value: Any) -> None:
    with pytest.raises(TypeError, match="must be an integer"):
        replace(make_fetch(), entries_count=value)


@pytest.mark.parametrize("http_status", [99, 600])
def test_fetch_rejects_out_of_range_http_status(http_status: int) -> None:
    with pytest.raises(ValueError, match="between 100 and 599"):
        replace(make_fetch(), http_status=http_status)


@pytest.mark.parametrize("field_name", ["started_at", "finished_at"])
def test_fetch_rejects_naive_timestamps(field_name: str) -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        replace(
            make_fetch(),
            **{field_name: datetime(2026, 9, 10, 8, 0)},
        )


def test_fetch_rejects_completion_before_start() -> None:
    with pytest.raises(ValueError, match="must not be before started_at"):
        replace(
            make_fetch(),
            finished_at=STARTED_AT - timedelta(seconds=1),
        )


def test_fetch_accepts_zero_duration_and_entries() -> None:
    fetch = replace(
        make_fetch(),
        finished_at=STARTED_AT,
        duration_ms=0,
        entries_count=0,
    )

    assert fetch.duration_ms == 0
    assert fetch.entries_count == 0


def test_fetch_is_immutable() -> None:
    fetch = make_fetch()

    with pytest.raises(FrozenInstanceError):
        fetch.entries_count = 10


def test_fetch_repr_excludes_error_summary() -> None:
    fetch = replace(
        make_fetch(),
        status=FeedFetchStatus.FAILED,
        error_code=ErrorCode.FEED_TIMEOUT,
        error_summary="Operational failure details",
    )

    assert "Operational failure details" not in repr(fetch)


def test_feed_fetch_has_docstrings() -> None:
    assert FeedFetch.__doc__
    assert FeedFetch.__post_init__.__doc__
