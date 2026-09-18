"""Tests for news-item hashing helpers."""

from app.domain.hashing import content_hash, sha256_hex, url_hash


def test_sha256_hex_is_stable() -> None:
    assert sha256_hex("hello") == sha256_hex("hello")
    assert len(sha256_hex("hello")) == 64


def test_url_and_content_hashes_differ_for_different_inputs() -> None:
    assert url_hash("https://example.com/a") != url_hash("https://example.com/b")
    assert content_hash("title", "summary") != content_hash("title", "other")
