from dataclasses import dataclass, field
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from app.domain.enum_validation import ensure_enum_member
from app.domain.enums import ErrorCode, PipelineRunStatus, TriggerType
from app.domain.state_machine import ensure_pipeline_run_transition
from app.domain.validators import (
    ensure_non_negative_int,
    ensure_utc_datetime,
    normalize_bounded_string,
    normalize_error_code,
    normalize_error_summary,
    utc_now,
)
from app.texts.pipeline import (
    FEED_COUNTERS_INCONSISTENT,
    ITEM_COUNTERS_INCONSISTENT,
    RUN_COMPLETION_BEFORE_START,
    RUN_COMPLETION_REQUIRED,
    RUN_ERROR_FORBIDDEN,
    RUN_FAILED_ERROR_REQUIRED,
    RUN_NOT_RUNNING,
    RUN_RUNNING_COMPLETION_FORBIDDEN,
    SELECTION_COUNTERS_INCONSISTENT,
)


@dataclass(slots=True, kw_only=True)
class PipelineRun:
    """Track pipeline execution, processing counters, and its final outcome.

    Counter methods are available only while the run is running.
    Failed operations leave the object unchanged.
    """

    trigger_type: TriggerType
    app_version: str
    id: UUID = field(default_factory=uuid4)
    status: PipelineRunStatus = PipelineRunStatus.RUNNING
    started_at: datetime = field(default_factory=utc_now)
    finished_at: datetime | None = None
    feeds_total: int = 0
    feeds_succeeded: int = 0
    items_fetched: int = 0
    items_inserted: int = 0
    items_duplicate: int = 0
    candidates_count: int = 0
    selected_count: int = 0
    error_code: ErrorCode | None = None
    error_summary: str | None = field(default=None, repr=False)
    duration_ms: int | None = None

    def __post_init__(self) -> None:
        """Validate initial counters, completion data, and enum fields."""
        ensure_enum_member(self.status, PipelineRunStatus, "status")
        ensure_enum_member(self.trigger_type, TriggerType, "trigger_type")
        app_version = normalize_bounded_string(
            self.app_version,
            "app_version",
            maximum=64,
        )
        ensure_utc_datetime(self.started_at, "started_at")
        self._validate_counters(self._counter_values())

        if self.status is PipelineRunStatus.RUNNING:
            if self.finished_at is not None or self.duration_ms is not None:
                raise ValueError(RUN_RUNNING_COMPLETION_FORBIDDEN)
        else:
            if self.finished_at is None or self.duration_ms is None:
                raise ValueError(RUN_COMPLETION_REQUIRED)

            ensure_utc_datetime(self.finished_at, "finished_at")

            if self.finished_at < self.started_at:
                raise ValueError(RUN_COMPLETION_BEFORE_START)

            ensure_non_negative_int(self.duration_ms, "duration_ms")

        error_code, error_summary = self._normalize_error_fields(
            self.status,
            self.error_code,
            self.error_summary,
        )

        self.app_version = app_version
        self.error_code = error_code
        self.error_summary = error_summary

    @classmethod
    def create_skipped_locked(
        cls,
        *,
        trigger_type: TriggerType,
        app_version: str,
        occurred_at: datetime | None = None,
    ) -> "PipelineRun":
        """Create a completed record for a run skipped due to an active lock."""
        ensure_enum_member(trigger_type, TriggerType, "trigger_type")
        timestamp = occurred_at if occurred_at is not None else utc_now()
        ensure_utc_datetime(timestamp, "occurred_at")

        return cls(
            trigger_type=trigger_type,
            app_version=app_version,
            status=PipelineRunStatus.SKIPPED_LOCKED,
            started_at=timestamp,
            finished_at=timestamp,
            duration_ms=0,
        )

    def record_feed_attempt(self) -> None:
        """Count one attempted feed fetch while the run is running."""
        self._record_counter("feeds_total", 1)

    def record_feed_success(self) -> None:
        """Count one successful fetch without exceeding attempted fetches."""
        self._record_counter("feeds_succeeded", 1)

    def record_items_fetched(self, count: int) -> None:
        """Add fetched entries before recording insertion or deduplication."""
        self._record_counter("items_fetched", count)

    def record_item_inserted(self) -> None:
        """Count one inserted entry without exceeding fetched entries."""
        self._record_counter("items_inserted", 1)

    def record_item_duplicate(self) -> None:
        """Count one duplicate entry without exceeding fetched entries."""
        self._record_counter("items_duplicate", 1)

    def record_candidates(self, count: int) -> None:
        """Add candidate entries before recording selected entries."""
        self._record_counter("candidates_count", count)

    def record_selected(self, count: int) -> None:
        """Add selected entries without exceeding candidate entries."""
        self._record_counter("selected_count", count)

    def complete(
        self,
        target_status: PipelineRunStatus,
        *,
        finished_at: datetime | None = None,
        error_code: ErrorCode | None = None,
        error_summary: str | None = None,
    ) -> None:
        """Complete a running pipeline run with a terminal outcome.

        Error summaries must already be sanitized by the caller.

        Raises:
            TypeError: If either status has the wrong enum type.
            ValueError: If completion data, counters, or error fields are invalid.
            InvalidStateTransitionError: If the transition is forbidden.
                Rejected completion leaves the run unchanged.
        """
        ensure_enum_member(self.status, PipelineRunStatus, "status")
        ensure_enum_member(target_status, PipelineRunStatus, "target_status")
        completion_time = finished_at if finished_at is not None else utc_now()
        ensure_utc_datetime(completion_time, "finished_at")

        if completion_time < self.started_at:
            raise ValueError(RUN_COMPLETION_BEFORE_START)

        self._validate_counters(self._counter_values())
        normalized_code, normalized_summary = self._normalize_error_fields(
            target_status,
            error_code,
            error_summary,
        )
        ensure_pipeline_run_transition(self.status, target_status)

        # Integer timedelta division avoids floating-point duration rounding.
        duration_ms = (completion_time - self.started_at) // timedelta(milliseconds=1)

        self.status = target_status
        self.finished_at = completion_time
        self.duration_ms = duration_ms
        self.error_code = normalized_code
        self.error_summary = normalized_summary

    def _record_counter(self, counter_name: str, count: int) -> None:
        """Validate a proposed counter snapshot before committing one update."""
        ensure_enum_member(self.status, PipelineRunStatus, "status")

        if self.status is not PipelineRunStatus.RUNNING:
            raise ValueError(RUN_NOT_RUNNING)

        validated_count = ensure_non_negative_int(count, "count")
        counters = self._counter_values()
        counters[counter_name] += validated_count
        self._validate_counters(counters)

        setattr(self, counter_name, counters[counter_name])

    def _counter_values(self) -> dict[str, int]:
        """Return an independent snapshot of the processing counters."""
        return {
            "feeds_total": self.feeds_total,
            "feeds_succeeded": self.feeds_succeeded,
            "items_fetched": self.items_fetched,
            "items_inserted": self.items_inserted,
            "items_duplicate": self.items_duplicate,
            "candidates_count": self.candidates_count,
            "selected_count": self.selected_count,
        }

    @staticmethod
    def _validate_counters(counters: dict[str, int]) -> None:
        """Reject negative counters and inconsistent processing totals."""
        for field_name, value in counters.items():
            ensure_non_negative_int(value, field_name)

        if counters["feeds_succeeded"] > counters["feeds_total"]:
            raise ValueError(FEED_COUNTERS_INCONSISTENT)

        if counters["items_inserted"] + counters["items_duplicate"] > counters["items_fetched"]:
            raise ValueError(ITEM_COUNTERS_INCONSISTENT)

        if counters["selected_count"] > counters["candidates_count"]:
            raise ValueError(SELECTION_COUNTERS_INCONSISTENT)

    @staticmethod
    def _normalize_error_fields(
        status: PipelineRunStatus,
        error_code: ErrorCode | None,
        error_summary: str | None,
    ) -> tuple[ErrorCode | None, str | None]:
        """Require a controlled error code only for failed runs."""
        ensure_enum_member(status, PipelineRunStatus, "status")

        if status is not PipelineRunStatus.FAILED:
            if error_code is not None or error_summary is not None:
                raise ValueError(RUN_ERROR_FORBIDDEN)

            return None, None

        if error_code is None:
            raise ValueError(RUN_FAILED_ERROR_REQUIRED)

        return (
            normalize_error_code(error_code),
            normalize_error_summary(error_summary),
        )
