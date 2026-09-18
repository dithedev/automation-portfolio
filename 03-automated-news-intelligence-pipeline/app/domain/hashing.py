"""Stable SHA-256 helpers for news-item deduplication keys."""

from hashlib import sha256


def sha256_hex(value: str) -> str:
    """Return the lowercase hex digest of a UTF-8 string."""
    return sha256(value.encode("utf-8")).hexdigest()


def url_hash(canonical_url: str) -> str:
    """Hash a canonical article URL."""
    return sha256_hex(canonical_url)


def content_hash(normalized_title: str, sanitized_summary: str) -> str:
    """Hash normalized title plus sanitized summary as an exact-match signal."""
    return sha256_hex(f"{normalized_title}\n{sanitized_summary}")
