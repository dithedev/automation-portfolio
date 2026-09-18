from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from app.domain.enum_validation import ensure_enum_member
from app.domain.enums import ErrorCode, FeedFetchStatus
from app.domain.validators import (
    ensure_http_status,
    ensure_non_negative_int,
    ensure_utc_datetime,
    normalize_error_code,
    normalize_error_summary,
)
from app.texts.feeds import (
    FETCH_COMPLETION_BEFORE_START,
    FETCH_ERROR_FORBIDDEN,
    FETCH_ERROR_REQUIRED,
    FETCH_NOT_MODIFIED_ENTRIES_FORBIDDEN,
    FETCH_NOT_MODIFIED_HTTP_REQUIRED,
    FETCH_SUCCESS_HTTP_REQUIRED,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class FeedFetch:
    """Store the completed result of fetching one source during a run.

    Results are immutable. The database enforces uniqueness of the
    run_id and source_id pair.
    """

    run_id: UUID
    source_id: UUID
    status: FeedFetchStatus
    started_at: datetime
    finished_at: datetime
    id: UUID = field(default_factory=uuid4)
    http_status: int | None = None
    entries_count: int = 0
    duration_ms: int = 0
    error_code: ErrorCode | None = None
    error_summary: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        """Validate timing, counters, HTTP status, and outcome metadata."""
        ensure_enum_member(self.status, FeedFetchStatus, "status")
        ensure_utc_datetime(self.started_at, "started_at")
        ensure_utc_datetime(self.finished_at, "finished_at")

        if self.finished_at < self.started_at:
            raise ValueError(FETCH_COMPLETION_BEFORE_START)

        ensure_non_negative_int(self.entries_count, "entries_count")
        ensure_non_negative_int(self.duration_ms, "duration_ms")

        if self.http_status is not None:
            ensure_http_status(self.http_status)

        if self.status is FeedFetchStatus.FAILED:
            if self.error_code is None:
                raise ValueError(FETCH_ERROR_REQUIRED)

            error_code = normalize_error_code(self.error_code)
            error_summary = normalize_error_summary(self.error_summary)

            object.__setattr__(self, "error_code", error_code)
            object.__setattr__(self, "error_summary", error_summary)
            return

        if self.error_code is not None or self.error_summary is not None:
            raise ValueError(FETCH_ERROR_FORBIDDEN)

        if self.status is FeedFetchStatus.NOT_MODIFIED:
            if self.http_status != 304:
                raise ValueError(FETCH_NOT_MODIFIED_HTTP_REQUIRED)

            if self.entries_count != 0:
                raise ValueError(FETCH_NOT_MODIFIED_ENTRIES_FORBIDDEN)

        elif self.status is FeedFetchStatus.SUCCESS:
            if self.http_status is None or not 200 <= self.http_status <= 299:
                raise ValueError(FETCH_SUCCESS_HTTP_REQUIRED)
