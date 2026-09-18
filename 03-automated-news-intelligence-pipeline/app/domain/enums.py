from enum import StrEnum


class TriggerType(StrEnum):
    """Identify how a pipeline run was started."""

    SCHEDULED = "scheduled"
    MANUAL = "manual"
    DRY_RUN = "dry_run"


class PipelineRunStatus(StrEnum):
    """Represent the lifecycle state of a pipeline run."""

    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    NO_CONTENT = "no_content"
    FAILED = "failed"
    SKIPPED_LOCKED = "skipped_locked"


class FeedFetchStatus(StrEnum):
    """Represent the outcome of fetching one configured feed."""

    NOT_MODIFIED = "not_modified"
    SUCCESS = "success"
    FAILED = "failed"


class NewsItemStatus(StrEnum):
    """Represent the processing state of a collected news item."""

    COLLECTED = "collected"
    CANDIDATE = "candidate"
    USED = "used"
    IGNORED = "ignored"


class DigestStatus(StrEnum):
    """Represent the generation and delivery state of a digest."""

    GENERATED = "generated"
    SENDING = "sending"
    SENT = "sent"
    FAILED = "failed"


class DigestTag(StrEnum):
    """Allowed thematic tags for digest items."""

    AI_MODELS = "AI_MODELS"
    AUTOMATION = "AUTOMATION"
    DEVELOPER_TOOLS = "DEVELOPER_TOOLS"
    PRODUCT = "PRODUCT"
    SECURITY = "SECURITY"
    RESEARCH = "RESEARCH"
    BUSINESS = "BUSINESS"
    OTHER = "OTHER"


class DeliveryStatus(StrEnum):
    """Represent the result of one Telegram delivery attempt."""

    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


class IgnoreReason(StrEnum):
    """Explain why a news item was excluded from further processing."""

    TOO_OLD = "too_old"
    MISSING_TITLE = "missing_title"
    MISSING_CONTENT = "missing_content"
    INVALID_URL = "invalid_url"
    IRRELEVANT = "irrelevant"
    DUPLICATE_CONTENT = "duplicate_content"


class ErrorCode(StrEnum):
    """Provide stable machine-readable codes for operational failures."""

    FEED_TIMEOUT = "FEED_TIMEOUT"
    FEED_CONNECTION_FAILED = "FEED_CONNECTION_FAILED"
    UNSAFE_FEED_URL = "UNSAFE_FEED_URL"
    FEED_RESPONSE_TOO_LARGE = "FEED_RESPONSE_TOO_LARGE"
    FEED_PARSE_FAILED = "FEED_PARSE_FAILED"
    OPENAI_TIMEOUT = "OPENAI_TIMEOUT"
    OPENAI_RATE_LIMITED = "OPENAI_RATE_LIMITED"
    INVALID_STRUCTURED_OUTPUT = "INVALID_STRUCTURED_OUTPUT"
    OUTPUT_POST_VALIDATION_FAILED = "OUTPUT_POST_VALIDATION_FAILED"
    TELEGRAM_TIMEOUT = "TELEGRAM_TIMEOUT"
    TELEGRAM_RATE_LIMITED = "TELEGRAM_RATE_LIMITED"
    TELEGRAM_PERMANENT_FAILURE = "TELEGRAM_PERMANENT_FAILURE"
    UNEXPECTED_PIPELINE_FAILURE = "UNEXPECTED_PIPELINE_FAILURE"
