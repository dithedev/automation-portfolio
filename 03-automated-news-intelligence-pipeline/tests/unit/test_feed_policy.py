from datetime import UTC, datetime

import pytest

from app.domain import ErrorCode, PipelineRun, PipelineRunStatus, Source, TriggerType
from app.domain.feed_policy import ensure_feed_url, ensure_public_ip
from app.domain.validators import ensure_https_url

TIMESTAMP = datetime(2026, 9, 10, 8, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/feed",
        "https://example.com:443/feed",
    ],
)
def test_feed_policy_accepts_https_default_port(url: str) -> None:
    ensure_feed_url(url, allowed_host="example.com")


@pytest.mark.parametrize("port", [1, 80, 444, 8080, 65535])
def test_feed_policy_rejects_nonstandard_ports(port: int) -> None:
    with pytest.raises(ValueError, match="port 443"):
        ensure_feed_url(
            f"https://example.com:{port}/feed",
            allowed_host="example.com",
        )


@pytest.mark.parametrize(
    ("url", "allowed_host"),
    [
        ("https://localhost/feed", "localhost"),
        ("https://service.localhost/feed", "service.localhost"),
    ],
)
def test_feed_policy_rejects_localhost(
    url: str,
    allowed_host: str,
) -> None:
    with pytest.raises(ValueError, match="localhost"):
        ensure_feed_url(url, allowed_host=allowed_host)


def test_feed_policy_rejects_http() -> None:
    with pytest.raises(ValueError, match="HTTPS"):
        ensure_feed_url(
            "http://example.com/feed",
            allowed_host="example.com",
        )


def test_feed_policy_rejects_host_mismatch() -> None:
    with pytest.raises(ValueError, match="exactly match"):
        ensure_feed_url(
            "https://other.example.com/feed",
            allowed_host="example.com",
        )


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.1",
        "169.254.1.1",
        "100.64.0.1",
        "100.127.255.254",
        "192.0.2.1",
        "224.0.0.1",
        "::1",
        "fc00::1",
        "fe80::1",
        "ff02::1",
        "2001:db8::1",
        "::ffff:127.0.0.1",
        "::ffff:100.64.0.1",
        "fe80::1%eth0",
    ],
)
def test_ip_policy_rejects_nonpublic_addresses(address: str) -> None:
    with pytest.raises(ValueError, match="public unicast"):
        ensure_public_ip(address)


@pytest.mark.parametrize(
    "address",
    [
        "8.8.8.8",
        "2606:4700:4700::1111",
        "::ffff:8.8.8.8",
    ],
)
def test_ip_policy_accepts_public_addresses(address: str) -> None:
    ensure_public_ip(address)


@pytest.mark.parametrize("address", ["", "not-an-ip", "999.999.999.999"])
def test_ip_policy_rejects_malformed_addresses(address: str) -> None:
    with pytest.raises(ValueError, match="valid IP address"):
        ensure_public_ip(address)


def test_feed_policy_rejects_shared_address_range() -> None:
    with pytest.raises(ValueError, match="public unicast"):
        ensure_feed_url(
            "https://100.64.0.1/feed",
            allowed_host="100.64.0.1",
        )


def test_source_uses_strict_feed_port_policy() -> None:
    with pytest.raises(ValueError, match="port 443"):
        Source(
            key="example-feed",
            name="Example Feed",
            feed_url="https://example.com:8080/feed",
            allowed_host="example.com",
            category="artificial_intelligence",
        )


def test_source_rejects_shared_address_range() -> None:
    with pytest.raises(ValueError, match="public unicast"):
        Source(
            key="example-feed",
            name="Example Feed",
            feed_url="https://100.64.0.1/feed",
            allowed_host="100.64.0.1",
            category="artificial_intelligence",
        )


def test_general_article_url_validation_remains_separate() -> None:
    ensure_https_url(
        "https://example.com:8080/article",
        "article_url",
    )


def test_pipeline_repr_excludes_error_summary() -> None:
    run = PipelineRun(
        trigger_type=TriggerType.MANUAL,
        app_version="0.1.0",
        started_at=TIMESTAMP,
    )
    run.complete(
        PipelineRunStatus.FAILED,
        finished_at=TIMESTAMP,
        error_code=ErrorCode.FEED_TIMEOUT,
        error_summary="Operational failure details",
    )

    assert run.error_summary == "Operational failure details"
    assert "Operational failure details" not in repr(run)
    assert "error_summary=" not in repr(run)


def test_feed_policy_helpers_have_docstrings() -> None:
    assert ensure_feed_url.__doc__
    assert ensure_public_ip.__doc__
