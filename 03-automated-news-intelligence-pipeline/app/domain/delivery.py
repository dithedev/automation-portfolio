from dataclasses import dataclass, field, replace
from datetime import datetime
from uuid import UUID, uuid4

from app.domain.enum_validation import ensure_enum_member
from app.domain.enums import DeliveryStatus, ErrorCode
from app.domain.validators import (
    ensure_http_status,
    ensure_non_negative_int,
    ensure_utc_datetime,
    normalize_error_code,
    normalize_error_summary,
    utc_now,
)
from app.texts.delivery import (
    DELIVERY_COMPLETION_BEFORE_START,
    DELIVERY_COMPLETION_REQUIRED,
    DELIVERY_FAILED_ERROR_REQUIRED,
    DELIVERY_FAILED_MESSAGE_ID_FORBIDDEN,
    DELIVERY_MESSAGE_ID_REQUIRED,
    DELIVERY_PENDING_REQUIRED,
    DELIVERY_PENDING_RESULT_FORBIDDEN,
    DELIVERY_POSITIVE_INTEGER_REQUIRED,
    DELIVERY_SENT_ERROR_FORBIDDEN,
    DELIVERY_SUCCESS_HTTP_REQUIRED,
)


@dataclass(slots=True, kw_only=True)
class DeliveryAttempt:
    """Track one attempt to send one digest part to Telegram.

    Only pending attempts can be completed. Retrying delivery requires
    a new attempt rather than rewriting an existing result.
    """

    digest_id: UUID
    part_number: int
    attempt_number: int
    id: UUID = field(default_factory=uuid4)
    status: DeliveryStatus = DeliveryStatus.PENDING
    telegram_message_id: int | None = None
    http_status: int | None = None
    retry_after_seconds: int | None = None
    error_code: ErrorCode | None = None
    error_summary: str | None = field(default=None, repr=False)
    started_at: datetime = field(default_factory=utc_now)
    finished_at: datetime | None = None

    def __post_init__(self) -> None:
        """Validate attempt numbering, timestamps, and status-specific data."""
        ensure_enum_member(self.status, DeliveryStatus, "status")
        self._ensure_positive_int(self.part_number, "part_number")
        self._ensure_positive_int(self.attempt_number, "attempt_number")
        ensure_utc_datetime(self.started_at, "started_at")

        if self.finished_at is not None:
            ensure_utc_datetime(self.finished_at, "finished_at")

            if self.finished_at < self.started_at:
                raise ValueError(DELIVERY_COMPLETION_BEFORE_START)

        if self.http_status is not None:
            ensure_http_status(self.http_status)

        if self.retry_after_seconds is not None:
            ensure_non_negative_int(
                self.retry_after_seconds,
                "retry_after_seconds",
            )

        if self.telegram_message_id is not None:
            self._ensure_positive_int(
                self.telegram_message_id,
                "telegram_message_id",
            )

        self._validate_status_fields()

        if self.status is DeliveryStatus.FAILED:
            if self.error_code is None:
                raise ValueError(DELIVERY_FAILED_ERROR_REQUIRED)

            error_code = normalize_error_code(self.error_code)
            error_summary = normalize_error_summary(self.error_summary)

            self.error_code = error_code
            self.error_summary = error_summary

    def mark_sent(
        self,
        *,
        telegram_message_id: int,
        finished_at: datetime | None = None,
        http_status: int = 200,
    ) -> None:
        """Complete a pending attempt with a successful Telegram response.

        Raises:
            ValueError: If the attempt is already completed or response data
                is invalid. Rejected completion leaves the attempt unchanged.
            TypeError: If numeric response fields are not integers.
        """
        self._ensure_pending()
        completion_time = finished_at if finished_at is not None else utc_now()

        # Validate a separate instance before committing the delivery result.
        result = replace(
            self,
            status=DeliveryStatus.SENT,
            telegram_message_id=telegram_message_id,
            http_status=http_status,
            retry_after_seconds=None,
            error_code=None,
            error_summary=None,
            finished_at=completion_time,
        )
        self._apply_result(result)

    def mark_failed(
        self,
        *,
        error_code: ErrorCode,
        error_summary: str | None = None,
        http_status: int | None = None,
        retry_after_seconds: int | None = None,
        finished_at: datetime | None = None,
    ) -> None:
        """Complete a pending attempt with a controlled failure code.

        Error summaries must already be sanitized by the caller.

        Raises:
            ValueError: If the attempt is already completed or failure data
                is invalid. Rejected completion leaves the attempt unchanged.
            TypeError: If numeric response fields are not integers.
        """
        self._ensure_pending()
        completion_time = finished_at if finished_at is not None else utc_now()
        result = replace(
            self,
            status=DeliveryStatus.FAILED,
            telegram_message_id=None,
            http_status=http_status,
            retry_after_seconds=retry_after_seconds,
            error_code=error_code,
            error_summary=error_summary,
            finished_at=completion_time,
        )
        self._apply_result(result)

    def _ensure_pending(self) -> None:
        """Reject attempts to overwrite an existing delivery result."""
        ensure_enum_member(self.status, DeliveryStatus, "status")

        if self.status is not DeliveryStatus.PENDING:
            raise ValueError(DELIVERY_PENDING_REQUIRED)

    def _apply_result(self, result: "DeliveryAttempt") -> None:
        """Commit result fields from a fully validated attempt."""
        self.status = result.status
        self.telegram_message_id = result.telegram_message_id
        self.http_status = result.http_status
        self.retry_after_seconds = result.retry_after_seconds
        self.error_code = result.error_code
        self.error_summary = result.error_summary
        self.finished_at = result.finished_at

    def _validate_status_fields(self) -> None:
        """Require result fields consistent with the delivery status."""
        if self.status is DeliveryStatus.PENDING:
            if any(
                value is not None
                for value in (
                    self.finished_at,
                    self.telegram_message_id,
                    self.http_status,
                    self.retry_after_seconds,
                    self.error_code,
                    self.error_summary,
                )
            ):
                raise ValueError(DELIVERY_PENDING_RESULT_FORBIDDEN)

            return

        if self.finished_at is None:
            raise ValueError(DELIVERY_COMPLETION_REQUIRED)

        if self.status is DeliveryStatus.SENT:
            if self.telegram_message_id is None:
                raise ValueError(DELIVERY_MESSAGE_ID_REQUIRED)

            if self.http_status is None or not 200 <= self.http_status <= 299:
                raise ValueError(DELIVERY_SUCCESS_HTTP_REQUIRED)

            if any(
                value is not None
                for value in (
                    self.retry_after_seconds,
                    self.error_code,
                    self.error_summary,
                )
            ):
                raise ValueError(DELIVERY_SENT_ERROR_FORBIDDEN)

        elif self.status is DeliveryStatus.FAILED:
            if self.error_code is None:
                raise ValueError(DELIVERY_FAILED_ERROR_REQUIRED)

            if self.telegram_message_id is not None:
                raise ValueError(DELIVERY_FAILED_MESSAGE_ID_FORBIDDEN)

    @staticmethod
    def _ensure_positive_int(value: int, field_name: str) -> None:
        """Require a positive integer while rejecting boolean values."""
        ensure_non_negative_int(value, field_name)

        if value == 0:
            raise ValueError(
                DELIVERY_POSITIVE_INTEGER_REQUIRED.format(
                    field_name=field_name,
                )
            )
