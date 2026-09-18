"""Tests for feed byte parsing and news-item normalization."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from app.config import PROJECT_ROOT
from app.infrastructure.feeds.normalize import news_item_from_entry
from app.infrastructure.feeds.parser import FeedParseError, ParsedFeedEntry, parse_feed_bytes

FIXTURES = PROJECT_ROOT / "tests" / "fixtures" / "feeds"


def test_parse_sample_rss() -> None:
    body = (FIXTURES / "sample_rss.xml").read_bytes()
    entries = parse_feed_bytes(body, max_entries=10)

    assert len(entries) == 2
    assert entries[0].external_id == "guid-article-1"
    assert entries[0].link is not None
    assert "utm_source" in entries[0].link
    assert entries[0].title is not None


def test_parse_sample_atom() -> None:
    body = (FIXTURES / "sample_atom.xml").read_bytes()
    entries = parse_feed_bytes(body, max_entries=10)

    assert len(entries) == 1
    assert entries[0].external_id == "tag:example.com,2025:atom-1"
    assert entries[0].link == "https://example.com/atom/one"


def test_parse_bozo_without_usable_entries_fails() -> None:
    body = (FIXTURES / "bozo_feed.xml").read_bytes()

    with pytest.raises(FeedParseError):
        parse_feed_bytes(body, max_entries=10)


def test_parse_bozo_with_entries_keeps_usable_rows() -> None:
    body = (FIXTURES / "bozo_with_entries.xml").read_bytes()
    entries = parse_feed_bytes(body, max_entries=10)

    assert len(entries) == 1
    assert entries[0].external_id == "ok-1"


def test_parse_respects_max_entries() -> None:
    body = (FIXTURES / "sample_rss.xml").read_bytes()
    entries = parse_feed_bytes(body, max_entries=1)

    assert len(entries) == 1


def test_normalize_builds_news_item_and_strips_tracking() -> None:
    entry = ParsedFeedEntry(
        external_id="guid-1",
        link="https://example.com/a?utm_source=rss&id=1",
        title="A concrete product update for automation teams",
        summary="<p>Useful summary with <script>x</script>markup</p>",
        author="Editor",
        published_at=datetime(2025, 9, 10, 8, 0, tzinfo=UTC),
    )

    result = news_item_from_entry(
        entry,
        source_id=uuid4(),
        collected_at=datetime(2025, 9, 10, 9, 0, tzinfo=UTC),
        article_max_length=12_000,
        allowed_host="example.com",
    )

    assert result.skipped is False
    assert result.item is not None
    assert result.item.canonical_url == "https://example.com/a?id=1"
    assert "script" not in result.item.sanitized_summary.lower()
    assert result.item.sanitized_summary


def test_normalize_skips_http_links() -> None:
    entry = ParsedFeedEntry(
        external_id=None,
        link="http://example.com/a",
        title="Title that should be skipped for insecure transport",
        summary="Summary text",
        author=None,
        published_at=None,
    )

    result = news_item_from_entry(
        entry,
        source_id=uuid4(),
        collected_at=datetime(2025, 9, 10, 9, 0, tzinfo=UTC),
        article_max_length=12_000,
        allowed_host="example.com",
    )

    assert result.skipped is True
    assert result.item is None


def test_normalize_skips_off_host_article_links() -> None:
    entry = ParsedFeedEntry(
        external_id="guid-off-host",
        link="https://evil.example/phish",
        title="A concrete product update for automation teams",
        summary="Useful summary about AI automation for product teams.",
        author="Editor",
        published_at=datetime(2025, 9, 10, 8, 0, tzinfo=UTC),
    )

    result = news_item_from_entry(
        entry,
        source_id=uuid4(),
        collected_at=datetime(2025, 9, 10, 9, 0, tzinfo=UTC),
        article_max_length=12_000,
        allowed_host="example.com",
    )

    assert result.skipped is True
    assert result.item is None


def test_demo_feed_fixtures_exist() -> None:
    demo = PROJECT_ROOT / "demo" / "feeds"
    assert (demo / "sample_rss.xml").is_file()
    assert Path(FIXTURES / "duplicate_urls.xml").is_file()
