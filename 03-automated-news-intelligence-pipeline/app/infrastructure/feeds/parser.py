"""Parse feed bytes into structured entries without fetching URLs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from time import struct_time
from typing import Any

import feedparser

from app.domain.enums import ErrorCode
from app.texts.feeds import FEED_PARSE_FAILED


class FeedParseError(Exception):
    """Signal that feed bytes could not produce usable entries."""

    def __init__(self, summary: str = FEED_PARSE_FAILED) -> None:
        self.error_code = ErrorCode.FEED_PARSE_FAILED
        self.summary = summary
        super().__init__(summary)


@dataclass(frozen=True, slots=True, kw_only=True)
class ParsedFeedEntry:
    """One feed entry before domain normalization."""

    external_id: str | None
    link: str | None
    title: str | None
    summary: str | None
    author: str | None
    published_at: datetime | None


def _coerce_datetime(value: Any) -> datetime | None:
    if value is None:
        return None

    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    if isinstance(value, struct_time):
        return datetime(*value[:6], tzinfo=UTC)

    if isinstance(value, str):
        try:
            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError, IndexError, OverflowError):
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

    return None


def _entry_link(entry: Any) -> str | None:
    link = getattr(entry, "link", None)
    if isinstance(link, str) and link.strip():
        return link.strip()

    links = getattr(entry, "links", None)
    if isinstance(links, list):
        for item in links:
            href = item.get("href") if isinstance(item, dict) else getattr(item, "href", None)
            if isinstance(href, str) and href.strip():
                return href.strip()
    return None


def _entry_summary(entry: Any) -> str | None:
    for attribute in ("summary", "description"):
        value = getattr(entry, attribute, None)
        if isinstance(value, str) and value.strip():
            return value

    content = getattr(entry, "content", None)
    if isinstance(content, list) and content:
        first = content[0]
        value = first.get("value") if isinstance(first, dict) else getattr(first, "value", None)
        if isinstance(value, str) and value.strip():
            return value
    return None


def parse_feed_bytes(body: bytes, *, max_entries: int) -> tuple[ParsedFeedEntry, ...]:
    """Parse RSS/Atom bytes and return up to max_entries usable-looking rows.

    Raises:
        FeedParseError: When the document yields no entries.
    """
    if max_entries < 1:
        raise FeedParseError()

    parsed = feedparser.parse(body)
    entries = list(getattr(parsed, "entries", []) or [])

    if not entries:
        raise FeedParseError()

    results: list[ParsedFeedEntry] = []
    for entry in entries[:max_entries]:
        title = getattr(entry, "title", None)
        external_id = getattr(entry, "id", None) or getattr(entry, "guid", None)
        author = getattr(entry, "author", None)
        published = _coerce_datetime(
            getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
        )
        if published is None:
            published = _coerce_datetime(
                getattr(entry, "published", None) or getattr(entry, "updated", None)
            )

        results.append(
            ParsedFeedEntry(
                external_id=external_id.strip() if isinstance(external_id, str) else None,
                link=_entry_link(entry),
                title=title.strip() if isinstance(title, str) else None,
                summary=_entry_summary(entry),
                author=author.strip() if isinstance(author, str) else None,
                published_at=published,
            )
        )

    if not results:
        raise FeedParseError()

    return tuple(results)
