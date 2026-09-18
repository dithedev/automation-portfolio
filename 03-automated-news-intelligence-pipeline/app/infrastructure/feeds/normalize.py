"""Map parsed feed entries onto domain NewsItem values."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlsplit
from uuid import UUID

from app.domain.entities import NewsItem
from app.domain.hashing import content_hash, url_hash
from app.domain.text_sanitize import normalize_title, sanitize_feed_text
from app.domain.url_normalization import canonicalize_url
from app.domain.validators import normalize_hostname
from app.infrastructure.feeds.parser import ParsedFeedEntry


@dataclass(frozen=True, slots=True, kw_only=True)
class NormalizeResult:
    """Outcome of normalizing one parsed entry."""

    item: NewsItem | None
    skipped: bool


def news_item_from_entry(
    entry: ParsedFeedEntry,
    *,
    source_id: UUID,
    collected_at: datetime,
    article_max_length: int,
    allowed_host: str,
) -> NormalizeResult:
    """Build a collected NewsItem or mark the entry as skipped."""
    title = (entry.title or "").strip()
    link = (entry.link or "").strip()

    if not title or not link:
        return NormalizeResult(item=None, skipped=True)

    try:
        canonical = canonicalize_url(link)
        article_host = normalize_hostname(urlsplit(canonical).hostname or "", "canonical_url")
        expected_host = normalize_hostname(allowed_host, "allowed_host")
    except ValueError:
        return NormalizeResult(item=None, skipped=True)

    if article_host != expected_host:
        return NormalizeResult(item=None, skipped=True)

    raw_summary = entry.summary
    sanitized = sanitize_feed_text(
        raw_summary if raw_summary else title,
        maximum_length=article_max_length,
    )
    if not sanitized:
        sanitized = sanitize_feed_text(title, maximum_length=article_max_length)

    if not sanitized:
        return NormalizeResult(item=None, skipped=True)

    normalized = normalize_title(title)
    if not normalized:
        return NormalizeResult(item=None, skipped=True)

    bounded_title = title[:500]
    item = NewsItem(
        source_id=source_id,
        original_url=link if link.lower().startswith("https://") else canonical,
        canonical_url=canonical,
        url_hash=url_hash(canonical),
        title=bounded_title,
        normalized_title=normalized[:500],
        sanitized_summary=sanitized,
        content_hash=content_hash(normalized[:500], sanitized),
        external_id=entry.external_id,
        raw_summary=raw_summary,
        author=entry.author[:255] if entry.author else None,
        published_at=entry.published_at,
        collected_at=collected_at,
    )
    return NormalizeResult(item=item, skipped=False)
