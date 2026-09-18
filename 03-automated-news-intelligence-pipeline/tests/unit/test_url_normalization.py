"""Tests for canonical URL normalization."""

import pytest

from app.domain.url_normalization import canonicalize_url


def test_canonicalize_strips_tracking_and_fragment() -> None:
    result = canonicalize_url(
        "HTTPS://Example.COM:443/path/article?utm_source=x&b=2&a=1&gclid=1#section"
    )

    assert result == "https://example.com/path/article?a=1&b=2"


def test_canonicalize_empty_path_becomes_root() -> None:
    assert canonicalize_url("https://example.com") == "https://example.com/"


def test_canonicalize_preserves_non_tracking_query() -> None:
    result = canonicalize_url("https://example.com/a?id=42&ref=manual")

    assert result == "https://example.com/a?id=42&ref=manual"


def test_canonicalize_idna_hostname() -> None:
    result = canonicalize_url("https://münchen.example/path")

    assert result.startswith("https://xn--")
    assert result.endswith("/path")


def test_canonicalize_rejects_http() -> None:
    with pytest.raises(ValueError, match="HTTPS"):
        canonicalize_url("http://example.com/a")


def test_canonicalize_rejects_blank() -> None:
    with pytest.raises(ValueError):
        canonicalize_url("   ")
