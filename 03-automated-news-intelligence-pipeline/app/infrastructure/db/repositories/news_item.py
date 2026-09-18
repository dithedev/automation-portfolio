"""Persistence and deduplication operations for news items."""

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import IgnoreReason, NewsItem, NewsItemStatus
from app.infrastructure.db.models import NewsItemModel
from app.texts.db import (
    NEWS_DUPLICATE_CONFLICT,
    NEWS_ID_CONFLICT,
    NEWS_NOT_FOUND,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class NewsInsertResult:
    """Identify the stored article and whether this operation inserted it."""

    news_item_id: UUID
    inserted: bool


class NewsItemRepository:
    """Persist articles through a caller-owned session without committing."""

    def __init__(self, session: AsyncSession) -> None:
        """Bind repository operations to one session."""
        self._session = session

    async def add_if_new(self, item: NewsItem) -> NewsInsertResult:
        """Insert an article or identify its existing duplicate.

        Existing content and processing status are never overwritten.
        Conflicting keys that identify different rows are rejected.
        Database integrity errors unrelated to uniqueness propagate.
        """
        validated = replace(item)
        statement = (
            insert(NewsItemModel)
            .values(
                id=validated.id,
                source_id=validated.source_id,
                external_id=validated.external_id,
                original_url=validated.original_url,
                canonical_url=validated.canonical_url,
                url_hash=validated.url_hash,
                title=validated.title,
                normalized_title=validated.normalized_title,
                raw_summary=validated.raw_summary,
                sanitized_summary=validated.sanitized_summary,
                author=validated.author,
                published_at=validated.published_at,
                collected_at=validated.collected_at,
                content_hash=validated.content_hash,
                status=validated.status,
                ignore_reason=validated.ignore_reason,
            )
            .on_conflict_do_nothing()
            .returning(NewsItemModel.id)
        )
        inserted_id = await self._session.scalar(statement)

        if inserted_id is not None:
            return NewsInsertResult(news_item_id=inserted_id, inserted=True)

        return await self._resolve_duplicate(validated)

    async def get(self, news_item_id: UUID) -> NewsItem | None:
        """Return an article by ID, or None when it does not exist."""
        model = await self._session.get(NewsItemModel, news_item_id)
        return self._to_domain(model) if model is not None else None

    async def list_eligible_for_selection(
        self,
        *,
        now: datetime,
        max_age_hours: int,
        limit: int,
    ) -> tuple[NewsItem, ...]:
        """Return collected/candidate items still inside the age window."""
        age_anchor = func.coalesce(NewsItemModel.published_at, NewsItemModel.collected_at)
        oldest_allowed = now - timedelta(hours=max_age_hours)
        statement = (
            select(NewsItemModel)
            .where(
                NewsItemModel.status.in_(
                    (NewsItemStatus.COLLECTED, NewsItemStatus.CANDIDATE),
                ),
                age_anchor >= oldest_allowed,
            )
            .order_by(age_anchor.desc(), NewsItemModel.id.asc())
            .limit(limit)
        )
        models = await self._session.scalars(statement)
        return tuple(self._to_domain(model) for model in models)

    async def transition_to(
        self,
        news_item_id: UUID,
        target_status: NewsItemStatus,
        *,
        ignore_reason: IgnoreReason | None = None,
    ) -> NewsItem:
        """Apply a domain-approved transition while holding the article lock.

        Marking an article used must share the transaction that creates
        its digest. The caller owns transaction completion and rollback.
        """
        statement = (
            select(NewsItemModel)
            .where(NewsItemModel.id == news_item_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        model = await self._session.scalar(statement)

        if model is None:
            raise LookupError(NEWS_NOT_FOUND)

        item = self._to_domain(model)
        item.transition_to(target_status, ignore_reason=ignore_reason)

        model.status = item.status
        model.ignore_reason = item.ignore_reason

        await self._session.flush()
        return self._to_domain(model)

    async def _resolve_duplicate(self, item: NewsItem) -> NewsInsertResult:
        """Resolve uniqueness conflicts without accepting an unrelated ID."""
        predicates = [
            NewsItemModel.id == item.id,
            NewsItemModel.url_hash == item.url_hash,
        ]

        if item.external_id is not None:
            predicates.append(
                and_(
                    NewsItemModel.source_id == item.source_id,
                    NewsItemModel.external_id == item.external_id,
                )
            )

        statement = select(NewsItemModel).where(or_(*predicates))
        models = list(await self._session.scalars(statement))

        if len(models) != 1:
            raise ValueError(NEWS_DUPLICATE_CONFLICT)

        model = models[0]
        same_url = model.url_hash == item.url_hash
        same_external_id = (
            item.external_id is not None
            and model.source_id == item.source_id
            and model.external_id == item.external_id
        )

        if not same_url and not same_external_id:
            raise ValueError(NEWS_ID_CONFLICT)

        return NewsInsertResult(news_item_id=model.id, inserted=False)

    @staticmethod
    def _to_domain(model: NewsItemModel) -> NewsItem:
        """Restore and validate an article from persisted fields."""
        return NewsItem(
            id=model.id,
            source_id=model.source_id,
            external_id=model.external_id,
            original_url=model.original_url,
            canonical_url=model.canonical_url,
            url_hash=model.url_hash,
            title=model.title,
            normalized_title=model.normalized_title,
            raw_summary=model.raw_summary,
            sanitized_summary=model.sanitized_summary,
            author=model.author,
            published_at=model.published_at,
            collected_at=model.collected_at,
            content_hash=model.content_hash,
            status=model.status,
            ignore_reason=model.ignore_reason,
        )
