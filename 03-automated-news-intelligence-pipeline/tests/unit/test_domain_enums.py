import inspect

from app.domain import (
    DeliveryStatus,
    DigestStatus,
    ErrorCode,
    FeedFetchStatus,
    IgnoreReason,
    NewsItemStatus,
    PipelineRunStatus,
    TriggerType,
)

ENUM_CLASSES = (
    TriggerType,
    PipelineRunStatus,
    FeedFetchStatus,
    NewsItemStatus,
    DigestStatus,
    DeliveryStatus,
    IgnoreReason,
    ErrorCode,
)


def test_enum_members_serialize_as_strings() -> None:
    assert TriggerType.SCHEDULED == "scheduled"
    assert PipelineRunStatus.PARTIAL_SUCCESS == "partial_success"
    assert FeedFetchStatus.NOT_MODIFIED == "not_modified"
    assert NewsItemStatus.CANDIDATE == "candidate"
    assert DigestStatus.GENERATED == "generated"
    assert DeliveryStatus.PENDING == "pending"
    assert IgnoreReason.DUPLICATE_CONTENT == "duplicate_content"
    assert ErrorCode.FEED_TIMEOUT == "FEED_TIMEOUT"


def test_enum_members_have_expected_string_values() -> None:
    assert str(TriggerType.DRY_RUN) == "dry_run"
    assert str(PipelineRunStatus.SKIPPED_LOCKED) == "skipped_locked"
    assert str(NewsItemStatus.USED) == "used"
    assert str(DigestStatus.SENT) == "sent"
    assert str(ErrorCode.TELEGRAM_RATE_LIMITED) == ("TELEGRAM_RATE_LIMITED")


def test_error_codes_are_uppercase_snake_case() -> None:
    for error_code in ErrorCode:
        assert error_code.value == error_code.value.upper()
        assert error_code.value.replace("_", "").isalnum()


def test_public_enum_classes_have_docstrings() -> None:
    for enum_class in ENUM_CLASSES:
        assert inspect.getdoc(enum_class)
