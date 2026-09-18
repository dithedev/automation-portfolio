"""Unit tests for deterministic candidate selection."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.domain import NewsItem, NewsItemStatus, Source
from app.domain.enums import IgnoreReason
from app.domain.hashing import content_hash, url_hash
from app.domain.selection import select_candidates
from app.domain.text_sanitize import normalize_title
from app.infrastructure.topic_profile import TopicProfile

NOW = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)


def _profile(**overrides: object) -> TopicProfile:
    data: dict[str, object] = {
        "version": 1,
        "name": "Test",
        "include_keywords": ("ai", "automation", "product"),
        "exclude_keywords": ("casino",),
        "min_title_length": 12,
        "min_summary_length": 40,
    }
    data.update(overrides)
    return TopicProfile.model_validate(data)


def _source(*, key: str = "src", priority: str = "5.00") -> Source:
    return Source(
        key=key,
        name=key,
        feed_url=f"https://example.com/{key}.xml",
        allowed_host="example.com",
        category="artificial_intelligence",
        priority=Decimal(priority),
    )


def _item(
    *,
    source_id,
    title: str,
    summary: str,
    published_at: datetime | None = None,
    collected_at: datetime | None = None,
    path: str = "a",
) -> NewsItem:
    url = f"https://example.com/{path}"
    normalized = normalize_title(title)
    return NewsItem(
        source_id=source_id,
        original_url=url,
        canonical_url=url,
        url_hash=url_hash(url),
        title=title,
        normalized_title=normalized,
        sanitized_summary=summary,
        content_hash=content_hash(normalized, summary),
        published_at=published_at,
        collected_at=collected_at or NOW,
        status=NewsItemStatus.COLLECTED,
    )


def test_exclude_keyword_marks_irrelevant() -> None:
    source = _source()
    item = _item(
        source_id=source.id,
        title="Weekly AI product notes for teams",
        summary="A long enough summary about casino promotions and AI tools.",
        path="exclude",
    )

    result = select_candidates(
        (item,),
        sources_by_id={source.id: source},
        profile=_profile(),
        now=NOW,
        max_age_hours=72,
        max_candidates=25,
    )

    assert result.candidates == ()
    assert result.ignored[0].reason is IgnoreReason.IRRELEVANT


def test_too_old_items_are_ignored() -> None:
    source = _source()
    item = _item(
        source_id=source.id,
        title="Weekly AI product notes for teams",
        summary="A long enough summary about automation for product teams today.",
        published_at=NOW - timedelta(hours=100),
        path="old",
    )

    result = select_candidates(
        (item,),
        sources_by_id={source.id: source},
        profile=_profile(),
        now=NOW,
        max_age_hours=72,
        max_candidates=25,
    )

    assert result.ignored[0].reason is IgnoreReason.TOO_OLD


def test_diversity_caps_per_source() -> None:
    source = _source(key="one", priority="9.00")
    other = _source(key="two", priority="1.00")
    items = [
        _item(
            source_id=source.id,
            title=f"AI automation update number {index} for product teams",
            summary=(
                f"A long enough summary about AI automation and product delivery for item {index}."
            ),
            published_at=NOW - timedelta(hours=index),
            path=f"one-{index}",
        )
        for index in range(4)
    ]
    items.append(
        _item(
            source_id=other.id,
            title="Secondary AI tooling note for product teams",
            summary="A long enough summary about automation for another source item.",
            published_at=NOW,
            path="two-1",
        )
    )

    result = select_candidates(
        tuple(items),
        sources_by_id={source.id: source, other.id: other},
        profile=_profile(),
        now=NOW,
        max_age_hours=72,
        max_candidates=25,
    )

    from_source = [row for row in result.candidates if row.item.source_id == source.id]
    assert len(from_source) == 3
    assert any(row.item.source_id == other.id for row in result.candidates)


def test_max_candidates_cap() -> None:
    source = _source()
    items = tuple(
        _item(
            source_id=source.id,
            title=f"AI automation update number {index} for product teams",
            summary=(
                f"A long enough summary about AI automation and product delivery for item {index}."
            ),
            published_at=NOW - timedelta(minutes=index),
            path=f"cap-{index}",
        )
        for index in range(5)
    )

    result = select_candidates(
        items,
        sources_by_id={source.id: source},
        profile=_profile(),
        now=NOW,
        max_age_hours=72,
        max_candidates=2,
        max_per_source=3,
    )

    assert len(result.candidates) == 2


def test_ranking_prefers_fresher_higher_priority_items() -> None:
    high = _source(key="high", priority="9.00")
    low = _source(key="low", priority="1.00")
    fresh = _item(
        source_id=high.id,
        title="Fresh AI automation product update for teams",
        summary="A long enough summary about AI automation and product delivery practices today.",
        published_at=NOW - timedelta(hours=1),
        path="fresh",
    )
    stale = _item(
        source_id=low.id,
        title="Older AI automation product update for teams",
        summary="A long enough summary about AI automation and product delivery practices earlier.",
        published_at=NOW - timedelta(hours=48),
        path="stale",
    )

    result = select_candidates(
        (stale, fresh),
        sources_by_id={high.id: high, low.id: low},
        profile=_profile(),
        now=NOW,
        max_age_hours=72,
        max_candidates=25,
    )

    assert len(result.candidates) == 2
    assert result.candidates[0].item.id == fresh.id
    assert result.candidates[0].score > result.candidates[1].score


def test_missing_title_and_content_are_ignored() -> None:
    source = _source()
    short_title = _item(
        source_id=source.id,
        title="Short",
        summary="A long enough summary about AI automation and product delivery practices today.",
        path="short-title",
    )
    short_summary = _item(
        source_id=source.id,
        title="Weekly AI product notes for teams",
        summary="Too short.",
        path="short-summary",
    )

    result = select_candidates(
        (short_title, short_summary),
        sources_by_id={source.id: source},
        profile=_profile(),
        now=NOW,
        max_age_hours=72,
        max_candidates=25,
    )

    reasons = {row.reason for row in result.ignored}
    assert result.candidates == ()
    assert IgnoreReason.MISSING_TITLE in reasons
    assert IgnoreReason.MISSING_CONTENT in reasons
