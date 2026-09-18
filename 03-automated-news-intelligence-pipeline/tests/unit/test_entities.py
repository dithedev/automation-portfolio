import inspect
from copy import deepcopy
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from app.domain import (
    IgnoreReason,
    InvalidStateTransitionError,
    NewsItem,
    NewsItemStatus,
    Source,
)

SHA256_A = "a" * 64
SHA256_B = "b" * 64
CREATED_AT = datetime(2026, 9, 10, 7, 0, tzinfo=UTC)
CHECKED_AT = datetime(2026, 9, 10, 8, 0, tzinfo=UTC)


def make_source(
    *,
    key: str = "openai-news",
    feed_url: str = "https://openai.com/news/rss.xml",
    allowed_host: str = "openai.com",
    priority: Decimal = Decimal("8.50"),
    consecutive_failures: int = 0,
) -> Source:
    return Source(
        key=key,
        name="OpenAI News",
        feed_url=feed_url,
        allowed_host=allowed_host,
        category="artificial_intelligence",
        priority=priority,
        consecutive_failures=consecutive_failures,
        created_at=CREATED_AT,
        updated_at=CREATED_AT,
    )


def make_news_item(
    *,
    title: str = "AI Update",
    url_hash: str = SHA256_A,
    published_at: datetime | None = None,
    status: NewsItemStatus = NewsItemStatus.COLLECTED,
    ignore_reason: IgnoreReason | None = None,
    raw_summary: str | None = None,
) -> NewsItem:
    return NewsItem(
        source_id=uuid4(),
        original_url="https://example.com/articles/ai-update",
        canonical_url="https://example.com/articles/ai-update",
        url_hash=url_hash,
        title=title,
        normalized_title="ai update",
        sanitized_summary="A safe article summary.",
        content_hash=SHA256_B,
        collected_at=CREATED_AT,
        published_at=published_at,
        status=status,
        ignore_reason=ignore_reason,
        raw_summary=raw_summary,
    )


def test_source_accepts_valid_data() -> None:
    source = make_source()

    assert source.key == "openai-news"
    assert source.name == "OpenAI News"
    assert source.allowed_host == "openai.com"
    assert source.language == "en"
    assert source.consecutive_failures == 0


def test_source_normalizes_key_and_allowed_host() -> None:
    source = make_source(
        key="  OpenAI-News  ",
        allowed_host="  OpenAI.COM.  ",
    )

    assert source.key == "openai-news"
    assert source.allowed_host == "openai.com"


@pytest.mark.parametrize(
    "key",
    [
        "",
        "   ",
        "-openai",
        "openai-",
        "openai--news",
        "openai_news",
        "openai news",
        "новости",
        "a" * 65,
    ],
)
def test_source_rejects_invalid_key(key: str) -> None:
    with pytest.raises(ValueError):
        make_source(key=key)


@pytest.mark.parametrize(
    "field_name",
    ["key", "allowed_host", "feed_url"],
)
def test_source_identity_and_allowlist_fields_are_immutable(
    field_name: str,
) -> None:
    source = make_source()
    before = deepcopy(source)

    with pytest.raises(AttributeError, match="cannot be changed"):
        setattr(source, field_name, "replacement")

    assert source == before


def test_source_rejects_non_https_feed_url() -> None:
    with pytest.raises(ValueError, match="feed_url must use HTTPS"):
        make_source(feed_url="http://openai.com/news/rss.xml")


def test_source_rejects_credentials_in_url() -> None:
    with pytest.raises(ValueError, match="URL credentials"):
        make_source(
            feed_url="https://user:password@openai.com/news/rss.xml",
        )


def test_source_rejects_hostname_mismatch() -> None:
    with pytest.raises(ValueError, match="exactly match"):
        make_source(allowed_host="other.example.com")


@pytest.mark.parametrize(
    ("feed_url", "allowed_host"),
    [
        ("https://127.0.0.1/rss", "127.0.0.1"),
        ("https://10.0.0.1/rss", "10.0.0.1"),
        ("https://[::1]/rss", "::1"),
        ("https://[fc00::1]/rss", "fc00::1"),
    ],
)
def test_source_rejects_unsafe_literal_ip(
    feed_url: str,
    allowed_host: str,
) -> None:
    with pytest.raises(ValueError, match="must not use"):
        make_source(
            feed_url=feed_url,
            allowed_host=allowed_host,
        )


@pytest.mark.parametrize(
    "priority",
    [
        Decimal("-0.01"),
        Decimal("10.01"),
        Decimal("NaN"),
        Decimal("Infinity"),
    ],
)
def test_source_rejects_invalid_priority(priority: Decimal) -> None:
    with pytest.raises(ValueError, match="priority must be between"):
        make_source(priority=priority)


@pytest.mark.parametrize("priority", [Decimal("0"), Decimal("10")])
def test_source_accepts_priority_boundaries(priority: Decimal) -> None:
    assert make_source(priority=priority).priority == priority


def test_source_rejects_negative_failure_count() -> None:
    with pytest.raises(ValueError, match="must not be negative"):
        make_source(consecutive_failures=-1)


def test_source_records_fetch_success() -> None:
    source = make_source(consecutive_failures=2)

    source.record_fetch_success(
        checked_at=CHECKED_AT,
        etag='"feed-version"',
        last_modified="Thu, 10 Sep 2026 08:00:00 GMT",
    )

    assert source.last_checked_at == CHECKED_AT
    assert source.last_success_at == CHECKED_AT
    assert source.updated_at == CHECKED_AT
    assert source.consecutive_failures == 0
    assert source.etag == '"feed-version"'


def test_source_records_fetch_failure() -> None:
    source = make_source()

    source.record_fetch_failure(checked_at=CHECKED_AT)

    assert source.last_checked_at == CHECKED_AT
    assert source.last_success_at is None
    assert source.updated_at == CHECKED_AT
    assert source.consecutive_failures == 1


def test_source_failure_preserves_success_metadata() -> None:
    source = make_source()
    source.record_fetch_success(
        checked_at=CHECKED_AT,
        etag='"feed-version"',
        last_modified="Thu, 10 Sep 2026 08:00:00 GMT",
    )

    source.record_fetch_failure(checked_at=CHECKED_AT)

    assert source.last_success_at == CHECKED_AT
    assert source.etag == '"feed-version"'
    assert source.last_modified == "Thu, 10 Sep 2026 08:00:00 GMT"
    assert source.consecutive_failures == 1


def test_source_rejected_success_timestamp_preserves_state() -> None:
    source = make_source(consecutive_failures=2)
    before = deepcopy(source)

    with pytest.raises(ValueError, match="timezone-aware"):
        source.record_fetch_success(
            checked_at=datetime(2026, 9, 10, 8, 0),
            etag=None,
            last_modified=None,
        )

    assert source == before


@pytest.mark.parametrize(
    ("etag", "last_modified"),
    [
        ('"version"\r\nInjected: value', None),
        (None, "invalid\nheader"),
        ("\x00", None),
    ],
)
def test_source_rejected_response_header_preserves_state(
    etag: str | None,
    last_modified: str | None,
) -> None:
    source = make_source(consecutive_failures=2)
    before = deepcopy(source)

    with pytest.raises(ValueError, match="control characters"):
        source.record_fetch_success(
            checked_at=CHECKED_AT,
            etag=etag,
            last_modified=last_modified,
        )

    assert source == before


def test_source_rejected_failure_timestamp_preserves_state() -> None:
    source = make_source()
    before = deepcopy(source)

    with pytest.raises(ValueError, match="timezone-aware"):
        source.record_fetch_failure(
            checked_at=datetime(2026, 9, 10, 8, 0),
        )

    assert source == before


def test_news_item_starts_as_collected() -> None:
    news_item = make_news_item()

    assert news_item.status is NewsItemStatus.COLLECTED
    assert news_item.ignore_reason is None


def test_news_item_normalizes_title() -> None:
    assert make_news_item(title="  AI Update  ").title == "AI Update"


@pytest.mark.parametrize("title", ["", "   ", "a" * 501])
def test_news_item_rejects_invalid_title(title: str) -> None:
    with pytest.raises(ValueError, match="News item title"):
        make_news_item(title=title)


def test_news_item_can_be_selected_and_used() -> None:
    news_item = make_news_item()

    news_item.transition_to(NewsItemStatus.CANDIDATE)
    news_item.transition_to(NewsItemStatus.USED)

    assert news_item.status is NewsItemStatus.USED


def test_ignored_news_item_requires_reason() -> None:
    news_item = make_news_item()
    before = deepcopy(news_item)

    with pytest.raises(ValueError, match="ignore_reason is required"):
        news_item.transition_to(NewsItemStatus.IGNORED)

    assert news_item == before


def test_news_item_can_be_ignored_with_reason() -> None:
    news_item = make_news_item()

    news_item.transition_to(
        NewsItemStatus.IGNORED,
        ignore_reason=IgnoreReason.TOO_OLD,
    )

    assert news_item.status is NewsItemStatus.IGNORED
    assert news_item.ignore_reason is IgnoreReason.TOO_OLD


def test_news_item_rejects_reason_for_non_ignored_status() -> None:
    news_item = make_news_item()
    before = deepcopy(news_item)

    with pytest.raises(ValueError, match="only allowed"):
        news_item.transition_to(
            NewsItemStatus.CANDIDATE,
            ignore_reason=IgnoreReason.TOO_OLD,
        )

    assert news_item == before


def test_news_item_rejected_transition_preserves_state() -> None:
    news_item = make_news_item()
    before = deepcopy(news_item)

    with pytest.raises(InvalidStateTransitionError):
        news_item.transition_to(NewsItemStatus.USED)

    assert news_item == before


def test_news_item_rejects_invalid_initial_ignore_state() -> None:
    with pytest.raises(ValueError, match="ignore_reason is required"):
        make_news_item(status=NewsItemStatus.IGNORED)


def test_news_item_rejects_invalid_sha256_hash() -> None:
    with pytest.raises(ValueError, match="url_hash must be"):
        make_news_item(url_hash="not-a-valid-hash")


def test_news_item_rejects_naive_published_datetime() -> None:
    with pytest.raises(ValueError, match="published_at must be timezone-aware"):
        make_news_item(
            published_at=datetime(2026, 9, 10, 8, 0),
        )


def test_news_item_repr_excludes_raw_summary() -> None:
    news_item = make_news_item(raw_summary="private raw feed content")

    assert "private raw feed content" not in repr(news_item)


def test_public_entity_classes_and_methods_have_docstrings() -> None:
    for entity_class in (Source, NewsItem):
        assert entity_class.__doc__

        for name, method in inspect.getmembers(
            entity_class,
            predicate=inspect.isfunction,
        ):
            if not name.startswith("_"):
                assert method.__doc__, f"{entity_class.__name__}.{name}"
