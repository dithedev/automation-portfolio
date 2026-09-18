"""Persistence models for generated digests and their articles."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.enums import DigestStatus, ErrorCode
from app.infrastructure.db.models.base import Base


class DigestModel(Base):
    """Persist rendered digest content and its delivery lifecycle."""

    __tablename__ = "digests"
    __table_args__ = (
        UniqueConstraint("run_id"),
        CheckConstraint(
            "model = 'gpt-4o-mini'",
            name="model_valid",
        ),
        CheckConstraint(
            "input_tokens IS NULL OR input_tokens >= 0",
            name="input_tokens_non_negative",
        ),
        CheckConstraint(
            "output_tokens IS NULL OR output_tokens >= 0",
            name="output_tokens_non_negative",
        ),
        CheckConstraint(
            "(status = 'sent' AND sent_at IS NOT NULL) OR (status <> 'sent' AND sent_at IS NULL)",
            name="sent_time_matches_status",
        ),
        CheckConstraint(
            "sent_at IS NULL OR sent_at >= created_at",
            name="sent_time_valid",
        ),
        CheckConstraint(
            "(status = 'failed' AND error_code IS NOT NULL) "
            "OR (status <> 'failed' AND error_code IS NULL "
            "AND error_summary IS NULL)",
            name="error_matches_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    run_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("pipeline_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    digest_date: Mapped[date] = mapped_column(Date, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[DigestStatus] = mapped_column(
        Enum(
            DigestStatus,
            values_callable=lambda members: [member.value for member in members],
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            name="digest_status",
            length=32,
        ),
        nullable=False,
        server_default=text("'generated'"),
    )
    rendered_text: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        server_default=text("'gpt-4o-mini'"),
    )
    prompt_version: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_response_id: Mapped[str | None] = mapped_column(
        String(160),
        nullable=True,
    )
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    error_code: Mapped[ErrorCode | None] = mapped_column(
        Enum(
            ErrorCode,
            values_callable=lambda members: [member.value for member in members],
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            name="digest_error_code",
            length=64,
        ),
        nullable=True,
    )
    error_summary: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )


class DigestItemModel(Base):
    """Persist an article's position and generated content within a digest."""

    __tablename__ = "digest_items"
    __table_args__ = (
        UniqueConstraint("digest_id", "position"),
        CheckConstraint(
            "position BETWEEN 1 AND 7",
            name="position_valid",
        ),
        CheckConstraint(
            "relevance_score >= 0 AND relevance_score <= 1",
            name="relevance_score_valid",
        ),
    )

    digest_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("digests.id", ondelete="CASCADE"),
        primary_key=True,
    )
    news_item_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("news_items.id", ondelete="RESTRICT"),
        primary_key=True,
        index=True,
    )
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    summary: Mapped[str] = mapped_column(String(400), nullable=False)
    tag: Mapped[str] = mapped_column(String(32), nullable=False)
    relevance_score: Mapped[Decimal] = mapped_column(
        Numeric(4, 3),
        nullable=False,
    )
    selection_reason: Mapped[str] = mapped_column(String(300), nullable=False)
