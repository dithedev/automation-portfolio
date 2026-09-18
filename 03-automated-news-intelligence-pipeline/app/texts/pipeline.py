"""Pipeline run validation messages."""

RUN_NOT_RUNNING = "Only running pipeline runs may be modified"
RUN_RUNNING_COMPLETION_FORBIDDEN = "Running pipeline run must not have completion data"
RUN_COMPLETION_REQUIRED = "Completed pipeline run must have completion data"
RUN_COMPLETION_BEFORE_START = "finished_at must not be before started_at"
RUN_FAILED_ERROR_REQUIRED = "Failed pipeline run requires error_code"
RUN_ERROR_FORBIDDEN = "Only failed pipeline run may contain error information"

FEED_COUNTERS_INCONSISTENT = "feeds_succeeded must not exceed feeds_total"
ITEM_COUNTERS_INCONSISTENT = "Inserted and duplicate items must not exceed fetched items"
SELECTION_COUNTERS_INCONSISTENT = "selected_count must not exceed candidates_count"

FEED_FAILURE_WARNING = "One or more feeds exceeded the consecutive failure threshold: {keys}"
PIPELINE_UNEXPECTED_FAILURE = "Pipeline stopped because of an unexpected internal error."
