"""Persistence model for Telegram delivery attempts."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.enums import DeliveryStatus, ErrorCode
from app.infrastructure.db.models.base import Base


class DeliveryAttemptModel(Base):
    """Persist the outcome of one attempt to send one digest part."""

    __tablename__ = "delivery_attempts"
    __table_args__ = (
        UniqueConstraint("digest_id", "part_number", "attempt_number"),
        CheckConstraint(
            "part_number >= 1 AND attempt_number >= 1",
            name="numbering_positive",
        ),
        CheckConstraint(
            "telegram_message_id IS NULL OR telegram_message_id > 0",
            name="message_id_positive",
        ),
        CheckConstraint(
            "http_status IS NULL OR http_status BETWEEN 100 AND 599",
            name="http_status_valid",
        ),
        CheckConstraint(
            "retry_after_seconds IS NULL OR retry_after_seconds >= 0",
            name="retry_after_non_negative",
        ),
        CheckConstraint(
            "finished_at IS NULL OR finished_at >= started_at",
            name="completion_time_valid",
        ),
        CheckConstraint(
            "(status = 'pending' AND finished_at IS NULL "
            "AND telegram_message_id IS NULL AND http_status IS NULL "
            "AND retry_after_seconds IS NULL AND error_code IS NULL "
            "AND error_summary IS NULL) "
            "OR (status = 'sent' AND finished_at IS NOT NULL "
            "AND telegram_message_id IS NOT NULL AND http_status IS NOT NULL "
            "AND http_status BETWEEN 200 AND 299 "
            "AND retry_after_seconds IS NULL AND error_code IS NULL "
            "AND error_summary IS NULL) "
            "OR (status = 'failed' AND finished_at IS NOT NULL "
            "AND telegram_message_id IS NULL AND error_code IS NOT NULL)",
            name="result_matches_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    digest_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("digests.id", ondelete="CASCADE"),
        nullable=False,
    )
    part_number: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    attempt_number: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    status: Mapped[DeliveryStatus] = mapped_column(
        Enum(
            DeliveryStatus,
            values_callable=lambda members: [member.value for member in members],
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            name="delivery_status",
            length=32,
        ),
        nullable=False,
        server_default=text("'pending'"),
    )
    telegram_message_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retry_after_seconds: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    error_code: Mapped[ErrorCode | None] = mapped_column(
        Enum(
            ErrorCode,
            values_callable=lambda members: [member.value for member in members],
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            name="delivery_error_code",
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
        server_default=func.now(),
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
