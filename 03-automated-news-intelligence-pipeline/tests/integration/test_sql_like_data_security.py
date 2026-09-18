"""Security checks that require a live database (SQL-like payloads as data)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain import NewsItem, Source
from app.domain.hashing import content_hash, url_hash
from app.domain.text_sanitize import normalize_title, sanitize_feed_text
from app.infrastructure.db.repositories import NewsItemRepository, SourceRepository
from app.infrastructure.db.session import transaction_scope

COLLECTED_AT = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)
SQL_LIKE_TITLE = "UPDATE news; DROP TABLE news_items;--"
SQL_LIKE_SUMMARY = (
    "Teams should treat '; DROP TABLE digests;--' as plain text when summarizing "
    "automation product updates for operators."
)


@pytest.mark.asyncio
async def test_sql_like_title_and_summary_persist_as_data(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    source = Source(
        key=f"sql-data-{uuid4().hex[:8]}",
        name="SQL Data Source",
        feed_url="https://example.com/sql-data.xml",
        allowed_host="example.com",
        category="artificial_intelligence",
    )
    title = SQL_LIKE_TITLE
    raw_summary = f"<p>{SQL_LIKE_SUMMARY}</p>"
    sanitized = sanitize_feed_text(raw_summary, maximum_length=12_000)
    normalized = normalize_title(title)
    url = f"https://example.com/sql-like-{uuid4().hex}"
    item = NewsItem(
        source_id=source.id,
        original_url=url,
        canonical_url=url,
        url_hash=url_hash(url),
        title=title,
        normalized_title=normalized,
        raw_summary=raw_summary,
        sanitized_summary=sanitized,
        published_at=COLLECTED_AT,
        collected_at=COLLECTED_AT,
        content_hash=content_hash(normalized, sanitized),
    )

    async with transaction_scope(session_factory) as session:
        await SourceRepository(session).add(source)
        result = await NewsItemRepository(session).add_if_new(item)
        assert result.inserted is True

    async with transaction_scope(session_factory) as session:
        loaded = await NewsItemRepository(session).get(item.id)
        assert loaded is not None
        assert loaded.title == title
        assert "DROP TABLE" in loaded.sanitized_summary
        still_there = await SourceRepository(session).get(source.id)
        assert still_there is not None
