"""Persistence model for collected news articles."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CHAR,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.enums import IgnoreReason, NewsItemStatus
from app.infrastructure.db.models.base import Base


class NewsItemModel(Base):
    """Persist article content, deduplication keys, and processing status.

    Domain entities validate and normalize article data before persistence.
    Database constraints enforce deduplication and status consistency.
    """

    __tablename__ = "news_items"
    __table_args__ = (
        UniqueConstraint("url_hash"),
        Index(
            "uq_news_items_source_external_id",
            "source_id",
            "external_id",
            unique=True,
            postgresql_where=text("external_id IS NOT NULL"),
        ),
        Index(
            "ix_news_items_status_published_at",
            "status",
            text("published_at DESC"),
        ),
        Index(
            "ix_news_items_source_collected_at",
            "source_id",
            text("collected_at DESC"),
        ),
        CheckConstraint(
            "(status = 'ignored' AND ignore_reason IS NOT NULL) "
            "OR (status <> 'ignored' AND ignore_reason IS NULL)",
            name="ignore_reason_matches_status",
        ),
        CheckConstraint(
            "url_hash ~ '^[0-9a-f]{64}$'",
            name="url_hash_valid",
        ),
        CheckConstraint(
            "content_hash ~ '^[0-9a-f]{64}$'",
            name="content_hash_valid",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    source_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("feed_sources.id", ondelete="RESTRICT"),
        nullable=False,
    )
    external_id: Mapped[str | None] = mapped_column(Text, nullable=True)

    original_url: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_url: Mapped[str] = mapped_column(Text, nullable=False)
    url_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    normalized_title: Mapped[str] = mapped_column(String(500), nullable=False)
    raw_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    sanitized_summary: Mapped[str] = mapped_column(Text, nullable=False)
    author: Mapped[str | None] = mapped_column(String(255), nullable=True)

    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    content_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)

    status: Mapped[NewsItemStatus] = mapped_column(
        Enum(
            NewsItemStatus,
            values_callable=lambda members: [member.value for member in members],
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            name="news_item_status",
            length=32,
        ),
        nullable=False,
        server_default=text("'collected'"),
    )
    ignore_reason: Mapped[IgnoreReason | None] = mapped_column(
        Enum(
            IgnoreReason,
            values_callable=lambda members: [member.value for member in members],
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            name="news_item_ignore_reason",
            length=64,
        ),
        nullable=True,
    )
