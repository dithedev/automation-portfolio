"""Deterministic pre-filter, scoring, and candidate caps."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from app.domain.entities import NewsItem, Source
from app.domain.enums import IgnoreReason, NewsItemStatus

MAX_ITEMS_PER_SOURCE = 3


class SelectionProfile(Protocol):
    """Minimal profile contract used by deterministic selection."""

    include_keywords: tuple[str, ...]
    exclude_keywords: tuple[str, ...]
    min_title_length: int
    min_summary_length: int


@dataclass(frozen=True, slots=True, kw_only=True)
class ScoredCandidate:
    """One eligible item with its deterministic relevance score."""

    item: NewsItem
    score: float


@dataclass(frozen=True, slots=True, kw_only=True)
class IgnoredItem:
    """One item rejected by the pre-filter."""

    news_item_id: UUID
    reason: IgnoreReason


@dataclass(frozen=True, slots=True, kw_only=True)
class SelectionResult:
    """Ranked candidates and ignored items after diversity caps."""

    candidates: tuple[ScoredCandidate, ...]
    ignored: tuple[IgnoredItem, ...]


def _item_age_anchor(item: NewsItem) -> datetime:
    return item.published_at if item.published_at is not None else item.collected_at


def _keyword_score(text: str, include_keywords: tuple[str, ...]) -> float:
    if not include_keywords:
        return 0.0

    hits = sum(1 for keyword in include_keywords if keyword in text)
    return min(1.0, hits / max(1, len(include_keywords)))


def _freshness_score(anchor: datetime, *, now: datetime, max_age_hours: int) -> float:
    age = now - anchor
    if age.total_seconds() < 0:
        return 1.0

    max_age = timedelta(hours=max_age_hours)
    if age >= max_age:
        return 0.0

    return 1.0 - (age / max_age)


def _source_weight(priority: Decimal) -> float:
    return float(priority) / 10.0


def score_item(
    item: NewsItem,
    *,
    source: Source,
    profile: SelectionProfile,
    now: datetime,
    max_age_hours: int,
) -> tuple[float | None, IgnoreReason | None]:
    """Return a score or an ignore reason for one news item."""
    if item.status in {NewsItemStatus.USED, NewsItemStatus.IGNORED}:
        return None, IgnoreReason.IRRELEVANT

    anchor = _item_age_anchor(item)
    if now - anchor > timedelta(hours=max_age_hours):
        return None, IgnoreReason.TOO_OLD

    title = item.title.strip()
    summary = item.sanitized_summary.strip()

    if len(title) < profile.min_title_length:
        return None, IgnoreReason.MISSING_TITLE

    if len(summary) < profile.min_summary_length:
        return None, IgnoreReason.MISSING_CONTENT

    haystack = f"{title.lower()} {summary.lower()}"
    if any(keyword in haystack for keyword in profile.exclude_keywords):
        return None, IgnoreReason.IRRELEVANT

    keyword = _keyword_score(haystack, profile.include_keywords)
    freshness = _freshness_score(anchor, now=now, max_age_hours=max_age_hours)
    weight = _source_weight(source.priority)
    score = (0.45 * keyword) + (0.30 * freshness) + (0.25 * weight)
    return score, None


def select_candidates(
    items: tuple[NewsItem, ...],
    *,
    sources_by_id: dict[UUID, Source],
    profile: SelectionProfile,
    now: datetime,
    max_age_hours: int,
    max_candidates: int,
    max_per_source: int = MAX_ITEMS_PER_SOURCE,
) -> SelectionResult:
    """Filter, score, rank, and apply source diversity caps."""
    ignored: list[IgnoredItem] = []
    scored: list[ScoredCandidate] = []

    for item in items:
        source = sources_by_id.get(item.source_id)
        if source is None:
            ignored.append(IgnoredItem(news_item_id=item.id, reason=IgnoreReason.IRRELEVANT))
            continue

        score, reason = score_item(
            item,
            source=source,
            profile=profile,
            now=now,
            max_age_hours=max_age_hours,
        )
        if reason is not None or score is None:
            ignored.append(
                IgnoredItem(
                    news_item_id=item.id,
                    reason=reason or IgnoreReason.IRRELEVANT,
                )
            )
            continue

        scored.append(ScoredCandidate(item=item, score=score))

    scored.sort(key=lambda row: (-row.score, row.item.id.hex))

    selected: list[ScoredCandidate] = []
    per_source: dict[UUID, int] = {}

    for candidate in scored:
        source_id = candidate.item.source_id
        taken = per_source.get(source_id, 0)
        if taken >= max_per_source:
            continue

        selected.append(candidate)
        per_source[source_id] = taken + 1

        if len(selected) >= max_candidates:
            break

    return SelectionResult(candidates=tuple(selected), ignored=tuple(ignored))
