from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from app.domain.enum_validation import ensure_enum_member
from app.domain.enums import DigestStatus, DigestTag, ErrorCode
from app.domain.state_machine import ensure_digest_transition
from app.domain.validators import (
    ensure_non_negative_int,
    ensure_utc_datetime,
    normalize_bounded_string,
    normalize_error_code,
    normalize_error_summary,
    utc_now,
)
from app.texts.digest import (
    DIGEST_ERROR_FORBIDDEN,
    DIGEST_ERROR_REQUIRED,
    DIGEST_ITEMS_INVALID,
    DIGEST_MODEL_INVALID,
    DIGEST_NEWS_DUPLICATE,
    DIGEST_POSITIONS_DUPLICATE,
    DIGEST_POSITIONS_INVALID,
    DIGEST_SENT_TIME_FORBIDDEN,
    DIGEST_SENT_TIME_REQUIRED,
    DIGEST_TAG_INVALID,
    DIGEST_TEXT_REQUIRED,
    DIGEST_TIME_BEFORE_CREATION,
    ITEM_POSITION_INVALID,
    ITEM_RELEVANCE_INVALID,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class DigestItem:
    """Store the validated summary and selection metadata for one article."""

    news_item_id: UUID
    position: int
    summary: str
    tag: str
    relevance_score: Decimal
    selection_reason: str

    def __post_init__(self) -> None:
        """Normalize text and validate position, lengths, and relevance."""
        ensure_non_negative_int(self.position, "position")

        if not 1 <= self.position <= 7:
            raise ValueError(ITEM_POSITION_INVALID)

        summary = normalize_bounded_string(
            self.summary,
            "Digest item summary",
            minimum=80,
            maximum=280,
        )
        try:
            tag = DigestTag(self.tag.strip().upper())
        except ValueError as error:
            raise ValueError(DIGEST_TAG_INVALID) from error

        selection_reason = normalize_bounded_string(
            self.selection_reason,
            "selection_reason",
            maximum=300,
        )

        if not self.relevance_score.is_finite() or not Decimal(
            "0"
        ) <= self.relevance_score <= Decimal("1"):
            raise ValueError(ITEM_RELEVANCE_INVALID)

        object.__setattr__(self, "summary", summary)
        object.__setattr__(self, "tag", tag.value)
        object.__setattr__(self, "selection_reason", selection_reason)


@dataclass(slots=True, kw_only=True)
class Digest:
    """Store generated digest content and track its delivery lifecycle.

    Failed delivery may be retried by transitioning back to sending.
    Sent digests are terminal according to the domain state machine.
    """

    run_id: UUID
    digest_date: date
    title: str
    rendered_text: str
    prompt_version: str
    items: tuple[DigestItem, ...]
    model: str = "gpt-4o-mini"
    id: UUID = field(default_factory=uuid4)
    status: DigestStatus = DigestStatus.GENERATED
    provider_response_id: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    created_at: datetime = field(default_factory=utc_now)
    sent_at: datetime | None = None
    error_code: ErrorCode | None = None
    error_summary: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        """Validate generated content, provider metadata, and initial state."""
        ensure_enum_member(self.status, DigestStatus, "status")
        title = normalize_bounded_string(
            self.title,
            "Digest title",
            maximum=200,
        )
        prompt_version = normalize_bounded_string(
            self.prompt_version,
            "prompt_version",
            maximum=32,
        )
        rendered_text = self.rendered_text.strip()
        model = self.model.strip()

        if not rendered_text:
            raise ValueError(DIGEST_TEXT_REQUIRED)

        if model != "gpt-4o-mini":
            raise ValueError(DIGEST_MODEL_INVALID)

        ensure_utc_datetime(self.created_at, "created_at")
        self._validate_items()

        provider_response_id = self.provider_response_id

        if provider_response_id is not None:
            provider_response_id = normalize_bounded_string(
                provider_response_id,
                "provider_response_id",
                maximum=160,
            )

        for field_name, value in (
            ("input_tokens", self.input_tokens),
            ("output_tokens", self.output_tokens),
        ):
            if value is not None:
                ensure_non_negative_int(value, field_name)

        if self.status is DigestStatus.SENT:
            if self.sent_at is None:
                raise ValueError(DIGEST_SENT_TIME_REQUIRED)

            self._validate_timestamp(self.sent_at, "sent_at")
        elif self.sent_at is not None:
            raise ValueError(DIGEST_SENT_TIME_FORBIDDEN)

        error_code, error_summary = self._normalize_error_fields(
            self.status,
            self.error_code,
            self.error_summary,
        )

        self.title = title
        self.rendered_text = rendered_text
        self.prompt_version = prompt_version
        self.model = model
        self.provider_response_id = provider_response_id
        self.error_code = error_code
        self.error_summary = error_summary

    def transition_to(
        self,
        target_status: DigestStatus,
        *,
        occurred_at: datetime | None = None,
        error_code: ErrorCode | None = None,
        error_summary: str | None = None,
    ) -> None:
        """Apply a delivery transition after validating supplied metadata.

        Error summaries must already be sanitized by the caller.

        Raises:
            TypeError: If either status has the wrong enum type.
            ValueError: If timestamps or error fields are invalid.
            InvalidStateTransitionError: If the transition is forbidden.
                Rejected transitions leave the digest unchanged.
        """
        ensure_enum_member(self.status, DigestStatus, "status")
        ensure_enum_member(target_status, DigestStatus, "target_status")
        timestamp = occurred_at if occurred_at is not None else utc_now()
        self._validate_timestamp(timestamp, "occurred_at")
        normalized_code, normalized_summary = self._normalize_error_fields(
            target_status,
            error_code,
            error_summary,
        )
        ensure_digest_transition(self.status, target_status)

        sent_at = timestamp if target_status is DigestStatus.SENT else None

        self.status = target_status
        self.sent_at = sent_at
        self.error_code = normalized_code
        self.error_summary = normalized_summary

    def _validate_items(self) -> None:
        """Require unique articles with consecutive digest positions."""
        if not 1 <= len(self.items) <= 7:
            raise ValueError(DIGEST_ITEMS_INVALID)

        positions = [item.position for item in self.items]
        news_item_ids = [item.news_item_id for item in self.items]

        if len(positions) != len(set(positions)):
            raise ValueError(DIGEST_POSITIONS_DUPLICATE)

        if len(news_item_ids) != len(set(news_item_ids)):
            raise ValueError(DIGEST_NEWS_DUPLICATE)

        if sorted(positions) != list(range(1, len(self.items) + 1)):
            raise ValueError(DIGEST_POSITIONS_INVALID)

    def _validate_timestamp(self, value: datetime, field_name: str) -> None:
        """Reject naive timestamps and events preceding digest creation."""
        ensure_utc_datetime(value, field_name)

        if value < self.created_at:
            raise ValueError(DIGEST_TIME_BEFORE_CREATION.format(field_name=field_name))

    @staticmethod
    def _normalize_error_fields(
        status: DigestStatus,
        error_code: ErrorCode | None,
        error_summary: str | None,
    ) -> tuple[ErrorCode | None, str | None]:
        """Require a controlled error code only for failed digests."""
        ensure_enum_member(status, DigestStatus, "status")

        if status is not DigestStatus.FAILED:
            if error_code is not None or error_summary is not None:
                raise ValueError(DIGEST_ERROR_FORBIDDEN)

            return None, None

        if error_code is None:
            raise ValueError(DIGEST_ERROR_REQUIRED)

        return (
            normalize_error_code(error_code),
            normalize_error_summary(error_summary),
        )
