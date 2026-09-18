"""Persistence model for configured feed sources."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.models.base import Base


class SourceModel(Base):
    """Persist feed configuration and conditional-request metadata.

    Domain entities validate feed URLs and source identity. Database
    constraints protect numeric bounds and source-key uniqueness.
    """

    __tablename__ = "feed_sources"
    __table_args__ = (
        UniqueConstraint("key"),
        CheckConstraint(
            "priority >= 0 AND priority <= 10",
            name="priority_range",
        ),
        CheckConstraint(
            "consecutive_failures >= 0",
            name="consecutive_failures_non_negative",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    feed_url: Mapped[str] = mapped_column(Text, nullable=False)
    allowed_host: Mapped[str] = mapped_column(String(253), nullable=False)

    category: Mapped[str] = mapped_column(String(64), nullable=False)
    language: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=text("'en'"),
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
    )
    priority: Mapped[Decimal] = mapped_column(
        Numeric(4, 2),
        nullable=False,
        server_default=text("5.00"),
    )

    etag: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_modified: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_success_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    consecutive_failures: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
