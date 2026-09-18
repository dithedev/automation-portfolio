from datetime import UTC, datetime
from typing import Any

import pytest

from app.domain import ErrorCode
from app.domain.validators import (
    ensure_http_status,
    ensure_https_url,
    ensure_non_negative_int,
    ensure_sha256,
    ensure_utc_datetime,
    normalize_bounded_string,
    normalize_error_code,
    normalize_error_summary,
    normalize_hostname,
    utc_now,
)


def test_utc_now_returns_timezone_aware_utc_datetime() -> None:
    value = utc_now()

    assert value.tzinfo is UTC
    assert value.utcoffset() is not None


def test_ensure_utc_datetime_accepts_aware_datetime() -> None:
    ensure_utc_datetime(
        datetime(2026, 9, 10, 8, 0, tzinfo=UTC),
        "created_at",
    )


def test_ensure_utc_datetime_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        ensure_utc_datetime(
            datetime(2026, 9, 10, 8, 0),
            "created_at",
        )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Example.COM", "example.com"),
        ("feeds.example.com.", "feeds.example.com"),
        ("  api.example.com  ", "api.example.com"),
    ],
)
def test_normalize_hostname(
    value: str,
    expected: str,
) -> None:
    assert normalize_hostname(value, "allowed_host") == expected


@pytest.mark.parametrize(
    "value",
    [
        "",
        ".example.com",
        "example..com",
        "-example.com",
        "example-.com",
        "exa_mple.com",
    ],
)
def test_normalize_hostname_rejects_invalid_hostnames(value: str) -> None:
    with pytest.raises(ValueError):
        normalize_hostname(value, "allowed_host")


@pytest.mark.parametrize(
    "value",
    [
        "127.0.0.1",
        "10.0.0.1",
        "169.254.1.1",
        "224.0.0.1",
        "0.0.0.0",  # noqa: S104 -- Rejection test; no socket is bound.
        "192.0.2.1",
        "::1",
        "fc00::1",
    ],
)
def test_normalize_hostname_rejects_unsafe_literal_ips(value: str) -> None:
    with pytest.raises(ValueError, match="must not use"):
        normalize_hostname(value, "allowed_host")


def test_ensure_https_url_accepts_matching_hostname() -> None:
    ensure_https_url(
        "https://feeds.example.com/rss?category=ai",
        "feed_url",
        expected_hostname="feeds.example.com",
    )


def test_ensure_https_url_rejects_http() -> None:
    with pytest.raises(ValueError, match="must use HTTPS"):
        ensure_https_url(
            "http://feeds.example.com/rss",
            "feed_url",
        )


def test_ensure_https_url_rejects_embedded_credentials() -> None:
    with pytest.raises(ValueError, match="credentials"):
        ensure_https_url(
            "https://user:password@feeds.example.com/rss",
            "feed_url",
        )


def test_ensure_https_url_rejects_missing_hostname() -> None:
    with pytest.raises(ValueError, match="hostname"):
        ensure_https_url("https:///rss", "feed_url")


def test_ensure_https_url_rejects_hostname_mismatch() -> None:
    with pytest.raises(ValueError, match="exactly match"):
        ensure_https_url(
            "https://other.example.com/rss",
            "feed_url",
            expected_hostname="feeds.example.com",
        )


@pytest.mark.parametrize(
    "value",
    [
        "https://127.0.0.1/rss",
        "https://[::1]/rss",
        "https://[fc00::1]/rss",
    ],
)
def test_ensure_https_url_rejects_unsafe_literal_ip(value: str) -> None:
    with pytest.raises(ValueError, match="must not use"):
        ensure_https_url(value, "feed_url")


def test_ensure_sha256_accepts_valid_digest() -> None:
    ensure_sha256("a" * 64, "content_hash")


@pytest.mark.parametrize(
    "value",
    [
        "a" * 63,
        "a" * 65,
        "g" * 64,
    ],
)
def test_ensure_sha256_rejects_invalid_digest(value: str) -> None:
    with pytest.raises(ValueError, match="SHA-256"):
        ensure_sha256(value, "content_hash")


def test_normalize_bounded_string_trims_value() -> None:
    result = normalize_bounded_string(
        "  Source name  ",
        "name",
        maximum=160,
    )

    assert result == "Source name"


def test_normalize_bounded_string_rejects_empty_value() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        normalize_bounded_string(
            "   ",
            "name",
            maximum=160,
        )


def test_normalize_bounded_string_rejects_short_value() -> None:
    with pytest.raises(ValueError, match="at least 3"):
        normalize_bounded_string(
            "ab",
            "key",
            minimum=3,
            maximum=64,
        )


def test_normalize_bounded_string_rejects_long_value() -> None:
    with pytest.raises(ValueError, match="must not exceed 5"):
        normalize_bounded_string(
            "abcdef",
            "name",
            maximum=5,
        )


@pytest.mark.parametrize("value", [0, 1, 100])
def test_ensure_non_negative_int_accepts_valid_values(value: int) -> None:
    assert ensure_non_negative_int(value, "count") == value


def test_ensure_non_negative_int_rejects_negative_value() -> None:
    with pytest.raises(ValueError, match="must not be negative"):
        ensure_non_negative_int(-1, "count")


@pytest.mark.parametrize("value", [True, 1.5, "1"])
def test_ensure_non_negative_int_rejects_non_integer(
    value: Any,
) -> None:
    with pytest.raises(TypeError, match="must be an integer"):
        ensure_non_negative_int(value, "count")


@pytest.mark.parametrize("value", [100, 200, 304, 429, 599])
def test_ensure_http_status_accepts_valid_values(value: int) -> None:
    assert ensure_http_status(value) == value


@pytest.mark.parametrize("value", [99, 600])
def test_ensure_http_status_rejects_out_of_range_value(
    value: int,
) -> None:
    with pytest.raises(ValueError, match="between 100 and 599"):
        ensure_http_status(value)


@pytest.mark.parametrize("value", [True, 200.0, "200"])
def test_ensure_http_status_rejects_non_integer(value: Any) -> None:
    with pytest.raises(TypeError, match="must be an integer"):
        ensure_http_status(value)


def test_normalize_error_code_accepts_enum() -> None:
    result = normalize_error_code(ErrorCode.FEED_TIMEOUT)

    assert result is ErrorCode.FEED_TIMEOUT


def test_normalize_error_code_accepts_known_external_string() -> None:
    result = normalize_error_code("  TELEGRAM_RATE_LIMITED  ")

    assert result is ErrorCode.TELEGRAM_RATE_LIMITED


def test_normalize_error_code_rejects_whitespace() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        normalize_error_code("   ")


def test_normalize_error_code_rejects_unknown_value() -> None:
    with pytest.raises(ValueError, match="Unsupported error_code"):
        normalize_error_code("SOMETHING_RANDOM")


def test_normalize_error_code_rejects_long_value() -> None:
    with pytest.raises(ValueError, match="must not exceed 64"):
        normalize_error_code("A" * 65)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("", None),
        ("   ", None),
        ("  Request timed out  ", "Request timed out"),
    ],
)
def test_normalize_error_summary(
    value: str | None,
    expected: str | None,
) -> None:
    assert normalize_error_summary(value) == expected


def test_normalize_error_summary_rejects_long_value() -> None:
    with pytest.raises(ValueError, match="must not exceed 500"):
        normalize_error_summary("a" * 501)
