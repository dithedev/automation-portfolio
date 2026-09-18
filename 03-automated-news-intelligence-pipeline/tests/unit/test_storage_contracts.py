"""Domain validation for stored hashes and source category boundaries."""

from hashlib import sha256
from uuid import uuid4

import pytest

from app.domain import NewsItem, Source
from app.domain.validators import ensure_sha256


def test_sha256_accepts_generated_lowercase_digest() -> None:
    digest = sha256(b"article").hexdigest()

    ensure_sha256(digest, "content_hash")


@pytest.mark.parametrize(
    "digest",
    [
        "A" * 64,
        "a" * 63 + "B",
        "0" * 63 + "F",
    ],
    ids=["uppercase", "mixed-case", "uppercase-final-character"],
)
def test_sha256_rejects_non_lowercase_digest(digest: str) -> None:
    with pytest.raises(ValueError):
        ensure_sha256(digest, "content_hash")


@pytest.mark.parametrize("field_name", ["url_hash", "content_hash"])
def test_news_item_rejects_uppercase_hash(field_name: str) -> None:
    digest = sha256(b"article").hexdigest()

    with pytest.raises(ValueError):
        NewsItem(
            source_id=uuid4(),
            original_url="https://example.com/article",
            canonical_url="https://example.com/article",
            url_hash=digest.upper() if field_name == "url_hash" else digest,
            title="Product update",
            normalized_title="product update",
            sanitized_summary="A factual product update.",
            content_hash=digest.upper() if field_name == "content_hash" else digest,
        )


def test_source_accepts_category_at_storage_limit() -> None:
    source = Source(
        key="example",
        name="Example",
        feed_url="https://example.com/feed",
        allowed_host="example.com",
        category="a" * 64,
    )

    assert source.category == "a" * 64


def test_source_trims_category_before_checking_storage_limit() -> None:
    source = Source(
        key="example",
        name="Example",
        feed_url="https://example.com/feed",
        allowed_host="example.com",
        category=f"  {'a' * 64}  ",
    )

    assert source.category == "a" * 64


def test_source_rejects_category_above_storage_limit() -> None:
    with pytest.raises(ValueError):
        Source(
            key="example",
            name="Example",
            feed_url="https://example.com/feed",
            allowed_host="example.com",
            category="a" * 65,
        )
