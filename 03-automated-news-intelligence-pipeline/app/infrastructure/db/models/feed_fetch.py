"""Persistence model for completed feed fetches."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.enums import ErrorCode, FeedFetchStatus
from app.infrastructure.db.models.base import Base


class FeedFetchModel(Base):
    """Persist one completed fetch result per source and pipeline run."""

    __tablename__ = "feed_fetches"
    __table_args__ = (
        UniqueConstraint("run_id", "source_id"),
        CheckConstraint(
            "entries_count >= 0",
            name="entries_non_negative",
        ),
        CheckConstraint(
            "duration_ms >= 0",
            name="duration_non_negative",
        ),
        CheckConstraint(
            "finished_at >= started_at",
            name="completion_time_valid",
        ),
        CheckConstraint(
            "http_status IS NULL OR http_status BETWEEN 100 AND 599",
            name="http_status_valid",
        ),
        CheckConstraint(
            "(status = 'failed' AND error_code IS NOT NULL) "
            "OR (status <> 'failed' AND error_code IS NULL "
            "AND error_summary IS NULL)",
            name="error_matches_status",
        ),
        CheckConstraint(
            "status <> 'success' OR (http_status IS NOT NULL AND http_status BETWEEN 200 AND 299)",
            name="success_http_valid",
        ),
        CheckConstraint(
            "status <> 'not_modified' OR "
            "(http_status IS NOT NULL AND http_status = 304 "
            "AND entries_count = 0)",
            name="not_modified_result_valid",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    run_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("pipeline_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("feed_sources.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status: Mapped[FeedFetchStatus] = mapped_column(
        Enum(
            FeedFetchStatus,
            values_callable=lambda members: [member.value for member in members],
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            name="feed_fetch_status",
            length=32,
        ),
        nullable=False,
    )
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    entries_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    duration_ms: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    error_code: Mapped[ErrorCode | None] = mapped_column(
        Enum(
            ErrorCode,
            values_callable=lambda members: [member.value for member in members],
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            name="feed_fetch_error_code",
            length=64,
        ),
        nullable=True,
    )
    error_summary: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    finished_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
