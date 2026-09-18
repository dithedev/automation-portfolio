"""Persistence model for pipeline runs."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    Integer,
    String,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.enums import ErrorCode, PipelineRunStatus, TriggerType
from app.infrastructure.db.models.base import Base


class PipelineRunModel(Base):
    """Persist run outcomes, processing counters, and completion metadata."""

    __tablename__ = "pipeline_runs"
    __table_args__ = (
        CheckConstraint(
            "feeds_total >= 0 AND feeds_succeeded >= 0 "
            "AND items_fetched >= 0 AND items_inserted >= 0 "
            "AND items_duplicate >= 0 AND candidates_count >= 0 "
            "AND selected_count >= 0",
            name="counters_non_negative",
        ),
        CheckConstraint(
            "feeds_succeeded <= feeds_total",
            name="feed_counters_consistent",
        ),
        CheckConstraint(
            "items_inserted + items_duplicate <= items_fetched",
            name="item_counters_consistent",
        ),
        CheckConstraint(
            "selected_count <= candidates_count",
            name="selection_counters_consistent",
        ),
        CheckConstraint(
            "(status = 'running' AND finished_at IS NULL "
            "AND duration_ms IS NULL) "
            "OR (status <> 'running' AND finished_at IS NOT NULL "
            "AND duration_ms IS NOT NULL)",
            name="completion_matches_status",
        ),
        CheckConstraint(
            "finished_at IS NULL OR finished_at >= started_at",
            name="completion_time_valid",
        ),
        CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0",
            name="duration_non_negative",
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
    trigger_type: Mapped[TriggerType] = mapped_column(
        Enum(
            TriggerType,
            values_callable=lambda members: [member.value for member in members],
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            name="pipeline_trigger_type",
            length=32,
        ),
        nullable=False,
    )
    status: Mapped[PipelineRunStatus] = mapped_column(
        Enum(
            PipelineRunStatus,
            values_callable=lambda members: [member.value for member in members],
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            name="pipeline_run_status",
            length=32,
        ),
        nullable=False,
        server_default=text("'running'"),
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    feeds_total: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    feeds_succeeded: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    items_fetched: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    items_inserted: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    items_duplicate: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    candidates_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    selected_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    error_code: Mapped[ErrorCode | None] = mapped_column(
        Enum(
            ErrorCode,
            values_callable=lambda members: [member.value for member in members],
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            name="pipeline_error_code",
            length=64,
        ),
        nullable=True,
    )
    error_summary: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    app_version: Mapped[str] = mapped_column(String(64), nullable=False)
