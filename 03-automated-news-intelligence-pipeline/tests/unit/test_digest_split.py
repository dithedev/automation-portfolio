"""Unit tests for digest Telegram HTML rendering and message splitting."""

from __future__ import annotations

import html
import re
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from app.application.digest_render import (
    DigestSplitError,
    RenderedDigestLine,
    render_digest_text,
    split_digest_messages,
)
from app.domain import DigestItem, NewsItem, NewsItemStatus, Source
from app.domain.hashing import content_hash, url_hash
from app.domain.text_sanitize import normalize_title
from app.texts.digest_format import (
    DIGEST_FOOTER_STORIES,
    DIGEST_FOOTER_VERIFY,
    DIGEST_ITEM_SEPARATOR,
    DIGEST_READ_ON_PREFIX,
)

NOW = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)
SUMMARY = (
    "Teams shipping AI features get a concrete product update that clarifies "
    "automation defaults and reduces operational surprise during rollout."
)
_HREF_RE = re.compile(r'href="([^"]*)"')


def _visible_text(message: str) -> str:
    without_tags = re.sub(r"<[^>]+>", "", message)
    return html.unescape(without_tags)


def _line(
    *,
    position: int,
    title: str | None = None,
    tag: str = "PRODUCT",
    summary: str | None = None,
    source_name: str | None = None,
    url: str | None = None,
) -> RenderedDigestLine:
    article_title = title or f"AI automation product update number {position}"
    item_summary = summary or SUMMARY
    article_url = url or f"https://example.com/item-{position}-{uuid4().hex}"
    normalized = normalize_title(article_title)
    source_id = uuid4()
    news = NewsItem(
        source_id=source_id,
        original_url=article_url,
        canonical_url=article_url,
        url_hash=url_hash(article_url),
        title=article_title,
        normalized_title=normalized,
        sanitized_summary=item_summary,
        content_hash=content_hash(normalized, item_summary),
        published_at=NOW,
        collected_at=NOW,
        status=NewsItemStatus.CANDIDATE,
    )
    source = Source(
        id=source_id,
        key=f"src-{position}",
        name=source_name or f"Source {position}",
        feed_url=f"https://example.com/{position}.xml",
        allowed_host="example.com",
        category="artificial_intelligence",
    )
    item = DigestItem(
        news_item_id=news.id,
        position=position,
        summary=item_summary,
        tag=tag,
        relevance_score=Decimal("0.9"),
        selection_reason="Useful for product teams.",
    )
    return RenderedDigestLine(item=item, news_item=news, source=source)


def test_render_single_item_exact_format() -> None:
    line = _line(
        position=1,
        title="Launch notes",
        source_name="Publisher",
        url="https://example.com/launch",
    )
    text = render_digest_text(title="Daily Digest", lines=(line,))
    expected = (
        "🗞 <b>Daily Digest</b>\n"
        "\n"
        "<b>1. Launch notes</b>\n"
        "<blockquote>🏷 PRODUCT</blockquote>\n"
        f"{SUMMARY}\n"
        '↗ <a href="https://example.com/launch">Read on Publisher</a>\n'
        "\n"
        f"{DIGEST_FOOTER_STORIES.format(count=1)}\n"
        f"{DIGEST_FOOTER_VERIFY}\n"
    )
    assert text == expected


def test_render_multiple_items_uses_separator() -> None:
    lines = (
        _line(position=1, title="First", url="https://example.com/a", source_name="A"),
        _line(position=2, title="Second", url="https://example.com/b", source_name="B"),
    )
    text = render_digest_text(title="Daily Digest", lines=lines)
    assert DIGEST_ITEM_SEPARATOR in text
    assert text.count(DIGEST_ITEM_SEPARATOR) == 1
    assert "<b>1. First</b>" in text
    assert "<b>2. Second</b>" in text
    assert text.index("<b>1. First</b>") < text.index(DIGEST_ITEM_SEPARATOR)
    assert text.index(DIGEST_ITEM_SEPARATOR) < text.index("<b>2. Second</b>")
    assert DIGEST_FOOTER_STORIES.format(count=2) in text


def test_render_escapes_html_injection_characters() -> None:
    summary = (
        'Summary with <em>tags</em> & "quotes" that must stay escaped for Telegram '
        "HTML safety across RSS and model text."
    )
    line = _line(
        position=1,
        title='Break <b>me</b> & "quotes"',
        tag="PRODUCT",
        summary=summary,
        source_name='Acme <News> & "Co"',
        url='https://example.com/path?a=1&b="2"<3>',
    )
    text = render_digest_text(title='Digest <script> & "T"', lines=(line,))

    assert "<script>" not in text
    assert "&lt;script&gt;" in text
    assert "&lt;b&gt;me&lt;/b&gt;" in text
    assert html.escape(summary) in text
    assert "&amp;" in text
    assert "&quot;quotes&quot;" in text
    assert "&lt;em&gt;tags&lt;/em&gt;" in text
    href_values = _HREF_RE.findall(text)
    assert len(href_values) == 1
    assert href_values[0] == html.escape(
        'https://example.com/path?a=1&b="2"<3>',
        quote=True,
    )
    assert "&lt;News&gt;" in text
    assert "<blockquote>🏷 PRODUCT</blockquote>" in text
    assert 'href="' in text
    assert f"Read on {html.escape(line.source.name)}" in text


def test_render_hides_raw_url_from_visible_text() -> None:
    url = "https://example.com/no-raw-url-visible"
    line = _line(position=1, url=url, source_name="Wired")
    text = render_digest_text(title="Daily Digest", lines=(line,))
    visible = _visible_text(text)
    assert url not in visible
    assert f"{DIGEST_READ_ON_PREFIX}Wired" in visible
    assert f'href="{url}"' in text


def test_split_fits_in_single_part() -> None:
    lines = tuple(_line(position=index) for index in range(1, 4))
    parts = split_digest_messages(title="Daily Digest", lines=lines)
    assert len(parts) == 1
    assert parts[0] == render_digest_text(title="Daily Digest", lines=lines)
    assert all(len(part) <= 4096 for part in parts)


def test_split_creates_multiple_parts_under_small_limit() -> None:
    lines = tuple(_line(position=index) for index in range(1, 4))
    parts = split_digest_messages(title="Daily Digest", lines=lines, limit=650)
    assert len(parts) >= 2
    assert all(len(part) <= 650 for part in parts)
    assert "🗞 <b>Daily Digest</b>" in parts[0]
    assert "Daily Digest" not in parts[1]
    assert DIGEST_FOOTER_STORIES.format(count=3) in parts[-1]
    assert DIGEST_FOOTER_STORIES.format(count=3) not in parts[0]
    for part in parts:
        assert 'href="https://example.com/' in part
        assert "https://example.com/" not in _visible_text(part)


def test_split_rejects_oversized_single_item() -> None:
    with pytest.raises(DigestSplitError):
        split_digest_messages(
            title="Daily Digest",
            lines=(_line(position=1),),
            limit=50,
        )
