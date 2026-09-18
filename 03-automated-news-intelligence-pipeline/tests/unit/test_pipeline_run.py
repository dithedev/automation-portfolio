from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.domain import (
    ErrorCode,
    InvalidStateTransitionError,
    PipelineRun,
    PipelineRunStatus,
    TriggerType,
)

STARTED_AT = datetime(2026, 9, 10, 8, 0, tzinfo=UTC)
FINISHED_AT = STARTED_AT + timedelta(seconds=2, milliseconds=500)


def make_pipeline_run() -> PipelineRun:
    return PipelineRun(
        trigger_type=TriggerType.MANUAL,
        app_version="0.1.0",
        started_at=STARTED_AT,
    )


def test_pipeline_run_starts_running() -> None:
    run = make_pipeline_run()

    assert run.status is PipelineRunStatus.RUNNING
    assert run.finished_at is None
    assert run.duration_ms is None
    assert run.error_code is None
    assert run.error_summary is None


def test_pipeline_run_normalizes_app_version() -> None:
    run = PipelineRun(
        trigger_type=TriggerType.MANUAL,
        app_version="  0.1.0  ",
    )

    assert run.app_version == "0.1.0"


@pytest.mark.parametrize("app_version", ["", "   ", "a" * 65])
def test_pipeline_run_rejects_invalid_app_version(app_version: str) -> None:
    with pytest.raises(ValueError, match="app_version"):
        PipelineRun(
            trigger_type=TriggerType.MANUAL,
            app_version=app_version,
        )


def test_pipeline_run_records_all_processing_counters() -> None:
    run = make_pipeline_run()

    run.record_feed_attempt()
    run.record_feed_success()
    run.record_items_fetched(3)
    run.record_item_inserted()
    run.record_item_duplicate()
    run.record_candidates(2)
    run.record_selected(1)

    assert run.feeds_total == 1
    assert run.feeds_succeeded == 1
    assert run.items_fetched == 3
    assert run.items_inserted == 1
    assert run.items_duplicate == 1
    assert run.candidates_count == 2
    assert run.selected_count == 1


def test_pipeline_run_accepts_zero_count_updates() -> None:
    run = make_pipeline_run()
    before = deepcopy(run)

    run.record_items_fetched(0)
    run.record_candidates(0)
    run.record_selected(0)

    assert run == before


@pytest.mark.parametrize(
    "method_name",
    [
        "record_items_fetched",
        "record_candidates",
        "record_selected",
    ],
)
def test_negative_counter_update_preserves_state(method_name: str) -> None:
    run = make_pipeline_run()
    before = deepcopy(run)

    with pytest.raises(ValueError, match="must not be negative"):
        getattr(run, method_name)(-1)

    assert run == before


@pytest.mark.parametrize("count", [True, 1.5, "1"])
def test_non_integer_counter_update_preserves_state(count: Any) -> None:
    run = make_pipeline_run()
    before = deepcopy(run)

    with pytest.raises(TypeError, match="must be an integer"):
        run.record_items_fetched(count)

    assert run == before


def test_feed_success_without_attempt_preserves_state() -> None:
    run = make_pipeline_run()
    before = deepcopy(run)

    with pytest.raises(ValueError, match="feeds_succeeded"):
        run.record_feed_success()

    assert run == before


@pytest.mark.parametrize(
    "method_name",
    ["record_item_inserted", "record_item_duplicate"],
)
def test_processed_item_without_fetch_preserves_state(
    method_name: str,
) -> None:
    run = make_pipeline_run()
    before = deepcopy(run)

    with pytest.raises(ValueError, match="must not exceed fetched items"):
        getattr(run, method_name)()

    assert run == before


def test_inserted_and_duplicate_counts_share_fetched_limit() -> None:
    run = make_pipeline_run()
    run.record_items_fetched(1)
    run.record_item_inserted()
    before = deepcopy(run)

    with pytest.raises(ValueError, match="must not exceed fetched items"):
        run.record_item_duplicate()

    assert run == before


def test_selection_without_candidates_preserves_state() -> None:
    run = make_pipeline_run()
    before = deepcopy(run)

    with pytest.raises(ValueError, match="selected_count"):
        run.record_selected(1)

    assert run == before


@pytest.mark.parametrize(
    "target_status",
    [
        PipelineRunStatus.SUCCESS,
        PipelineRunStatus.PARTIAL_SUCCESS,
        PipelineRunStatus.NO_CONTENT,
    ],
)
def test_pipeline_run_completes_without_error(
    target_status: PipelineRunStatus,
) -> None:
    run = make_pipeline_run()

    run.complete(target_status, finished_at=FINISHED_AT)

    assert run.status is target_status
    assert run.finished_at == FINISHED_AT
    assert run.duration_ms == 2500
    assert run.error_code is None
    assert run.error_summary is None


def test_pipeline_run_truncates_submillisecond_duration() -> None:
    run = make_pipeline_run()

    run.complete(
        PipelineRunStatus.SUCCESS,
        finished_at=STARTED_AT + timedelta(microseconds=1999),
    )

    assert run.duration_ms == 1


def test_failed_pipeline_run_requires_error_code() -> None:
    run = make_pipeline_run()
    before = deepcopy(run)

    with pytest.raises(ValueError, match="requires error_code"):
        run.complete(
            PipelineRunStatus.FAILED,
            finished_at=FINISHED_AT,
        )

    assert run == before


def test_pipeline_run_stores_normalized_failure() -> None:
    run = make_pipeline_run()

    run.complete(
        PipelineRunStatus.FAILED,
        finished_at=FINISHED_AT,
        error_code=ErrorCode.OPENAI_TIMEOUT,
        error_summary="  OpenAI request timed out  ",
    )

    assert run.status is PipelineRunStatus.FAILED
    assert run.error_code is ErrorCode.OPENAI_TIMEOUT
    assert run.error_summary == "OpenAI request timed out"


def test_pipeline_run_normalizes_blank_error_summary() -> None:
    run = make_pipeline_run()

    run.complete(
        PipelineRunStatus.FAILED,
        finished_at=FINISHED_AT,
        error_code=ErrorCode.OPENAI_TIMEOUT,
        error_summary="   ",
    )

    assert run.error_summary is None


@pytest.mark.parametrize("error_code", ["   ", "UNKNOWN_ERROR"])
def test_invalid_error_code_preserves_state(error_code: Any) -> None:
    run = make_pipeline_run()
    before = deepcopy(run)

    with pytest.raises(ValueError):
        run.complete(
            PipelineRunStatus.FAILED,
            finished_at=FINISHED_AT,
            error_code=error_code,
        )

    assert run == before


def test_long_error_summary_preserves_state() -> None:
    run = make_pipeline_run()
    before = deepcopy(run)

    with pytest.raises(ValueError, match="must not exceed 500"):
        run.complete(
            PipelineRunStatus.FAILED,
            finished_at=FINISHED_AT,
            error_code=ErrorCode.OPENAI_TIMEOUT,
            error_summary="a" * 501,
        )

    assert run == before


@pytest.mark.parametrize(
    ("error_code", "error_summary"),
    [
        (ErrorCode.OPENAI_TIMEOUT, None),
        (None, "Unexpected failure"),
        (None, "   "),
    ],
)
def test_success_rejects_error_information(
    error_code: ErrorCode | None,
    error_summary: str | None,
) -> None:
    run = make_pipeline_run()
    before = deepcopy(run)

    with pytest.raises(ValueError, match="Only failed pipeline run"):
        run.complete(
            PipelineRunStatus.SUCCESS,
            finished_at=FINISHED_AT,
            error_code=error_code,
            error_summary=error_summary,
        )

    assert run == before


@pytest.mark.parametrize(
    "finished_at",
    [
        datetime(2026, 9, 10, 8, 0),
        STARTED_AT - timedelta(seconds=1),
    ],
)
def test_invalid_completion_time_preserves_state(
    finished_at: datetime,
) -> None:
    run = make_pipeline_run()
    before = deepcopy(run)

    with pytest.raises(ValueError):
        run.complete(
            PipelineRunStatus.SUCCESS,
            finished_at=finished_at,
        )

    assert run == before


def test_completed_run_cannot_be_completed_again() -> None:
    run = make_pipeline_run()
    run.complete(PipelineRunStatus.SUCCESS, finished_at=FINISHED_AT)
    before = deepcopy(run)

    with pytest.raises(InvalidStateTransitionError):
        run.complete(
            PipelineRunStatus.SUCCESS,
            finished_at=FINISHED_AT,
        )

    assert run == before


@pytest.mark.parametrize(
    "status",
    [
        PipelineRunStatus.SUCCESS,
        PipelineRunStatus.PARTIAL_SUCCESS,
        PipelineRunStatus.NO_CONTENT,
        PipelineRunStatus.FAILED,
        PipelineRunStatus.SKIPPED_LOCKED,
    ],
)
@pytest.mark.parametrize(
    ("method_name", "arguments"),
    [
        ("record_feed_attempt", ()),
        ("record_feed_success", ()),
        ("record_items_fetched", (1,)),
        ("record_item_inserted", ()),
        ("record_item_duplicate", ()),
        ("record_candidates", (1,)),
        ("record_selected", (1,)),
    ],
)
def test_terminal_run_rejects_counter_updates(
    status: PipelineRunStatus,
    method_name: str,
    arguments: tuple[int, ...],
) -> None:
    if status is PipelineRunStatus.SKIPPED_LOCKED:
        run = PipelineRun.create_skipped_locked(
            trigger_type=TriggerType.MANUAL,
            app_version="0.1.0",
            occurred_at=STARTED_AT,
        )
    else:
        run = make_pipeline_run()
        run.complete(
            status,
            finished_at=FINISHED_AT,
            error_code=(
                ErrorCode.UNEXPECTED_PIPELINE_FAILURE
                if status is PipelineRunStatus.FAILED
                else None
            ),
        )

    before = deepcopy(run)

    with pytest.raises(ValueError, match="Only running pipeline runs"):
        getattr(run, method_name)(*arguments)

    assert run == before


@pytest.mark.parametrize(
    "counters",
    [
        {"feeds_total": -1},
        {"feeds_total": 1, "feeds_succeeded": 2},
        {"items_fetched": 1, "items_inserted": 1, "items_duplicate": 1},
        {"candidates_count": 1, "selected_count": 2},
    ],
)
def test_pipeline_run_rejects_invalid_initial_counters(
    counters: dict[str, int],
) -> None:
    with pytest.raises(ValueError):
        PipelineRun(
            trigger_type=TriggerType.MANUAL,
            app_version="0.1.0",
            **counters,
        )


def test_running_run_rejects_completion_data() -> None:
    with pytest.raises(ValueError, match="must not have completion data"):
        PipelineRun(
            trigger_type=TriggerType.MANUAL,
            app_version="0.1.0",
            started_at=STARTED_AT,
            finished_at=FINISHED_AT,
            duration_ms=2500,
        )


def test_completed_run_requires_completion_data() -> None:
    with pytest.raises(ValueError, match="must have completion data"):
        PipelineRun(
            trigger_type=TriggerType.MANUAL,
            app_version="0.1.0",
            status=PipelineRunStatus.SUCCESS,
        )


def test_initial_failed_run_requires_error_code() -> None:
    with pytest.raises(ValueError, match="requires error_code"):
        PipelineRun(
            trigger_type=TriggerType.MANUAL,
            app_version="0.1.0",
            status=PipelineRunStatus.FAILED,
            started_at=STARTED_AT,
            finished_at=FINISHED_AT,
            duration_ms=2500,
        )


def test_initial_completed_run_rejects_negative_duration() -> None:
    with pytest.raises(ValueError, match="duration_ms must not be negative"):
        PipelineRun(
            trigger_type=TriggerType.MANUAL,
            app_version="0.1.0",
            status=PipelineRunStatus.SUCCESS,
            started_at=STARTED_AT,
            finished_at=FINISHED_AT,
            duration_ms=-1,
        )


def test_skipped_locked_run_is_completed_immediately() -> None:
    run = PipelineRun.create_skipped_locked(
        trigger_type=TriggerType.SCHEDULED,
        app_version="0.1.0",
        occurred_at=STARTED_AT,
    )

    assert run.status is PipelineRunStatus.SKIPPED_LOCKED
    assert run.started_at == STARTED_AT
    assert run.finished_at == STARTED_AT
    assert run.duration_ms == 0


def test_pipeline_run_has_no_unrestricted_increment_method() -> None:
    assert not hasattr(PipelineRun, "increment")


def test_pipeline_run_public_api_has_docstrings() -> None:
    assert PipelineRun.__doc__

    for name in (
        "create_skipped_locked",
        "record_feed_attempt",
        "record_feed_success",
        "record_items_fetched",
        "record_item_inserted",
        "record_item_duplicate",
        "record_candidates",
        "record_selected",
        "complete",
    ):
        assert getattr(PipelineRun, name).__doc__, name
