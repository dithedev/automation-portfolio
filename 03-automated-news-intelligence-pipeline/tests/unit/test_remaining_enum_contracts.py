from copy import deepcopy
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest

from app.domain import (
    DeliveryStatus,
    Digest,
    DigestItem,
    DigestStatus,
    IgnoreReason,
    NewsItem,
    NewsItemStatus,
    PipelineRun,
    PipelineRunStatus,
    TriggerType,
    ensure_digest_transition,
    ensure_news_item_transition,
    ensure_pipeline_run_transition,
)
from app.domain.state_machine import ensure_transition_allowed

TIMESTAMP = datetime(2026, 9, 10, 8, 0, tzinfo=UTC)

VALID_SUMMARY = (
    "The selected article reports a concrete product or tooling update "
    "with clear implications for automation-focused teams."
)


def make_digest() -> Digest:
    item = DigestItem(
        news_item_id=uuid4(),
        position=1,
        summary=VALID_SUMMARY,
        tag="PRODUCT",
        relevance_score=Decimal("0.9"),
        selection_reason="Relevant product update.",
    )
    return Digest(
        run_id=uuid4(),
        digest_date=date(2026, 9, 10),
        title="Daily digest",
        rendered_text="1. A grounded summary.",
        prompt_version="v1",
        items=(item,),
        created_at=TIMESTAMP,
    )


def make_news_item() -> NewsItem:
    return NewsItem(
        source_id=uuid4(),
        original_url="https://example.com/article",
        canonical_url="https://example.com/article",
        url_hash="a" * 64,
        title="Article",
        normalized_title="article",
        sanitized_summary="Article summary.",
        content_hash="b" * 64,
        collected_at=TIMESTAMP,
    )


def make_run() -> PipelineRun:
    return PipelineRun(
        trigger_type=TriggerType.MANUAL,
        app_version="0.1.0",
        started_at=TIMESTAMP,
    )


@pytest.mark.parametrize("status", [member.value for member in DigestStatus])
def test_digest_rejects_string_status(status: Any) -> None:
    with pytest.raises(TypeError, match="DigestStatus"):
        replace(make_digest(), status=status)


@pytest.mark.parametrize("status", [member.value for member in NewsItemStatus])
def test_news_item_rejects_string_status(status: Any) -> None:
    with pytest.raises(TypeError, match="NewsItemStatus"):
        replace(make_news_item(), status=status)


@pytest.mark.parametrize(
    "status",
    [member.value for member in PipelineRunStatus],
)
def test_pipeline_run_rejects_string_status(status: Any) -> None:
    with pytest.raises(TypeError, match="PipelineRunStatus"):
        replace(make_run(), status=status)


@pytest.mark.parametrize(
    "trigger_type",
    [member.value for member in TriggerType],
)
def test_pipeline_run_rejects_string_trigger(trigger_type: Any) -> None:
    with pytest.raises(TypeError, match="TriggerType"):
        replace(make_run(), trigger_type=trigger_type)


def test_skipped_run_rejects_string_trigger() -> None:
    trigger_type: Any = "manual"

    with pytest.raises(TypeError, match="TriggerType"):
        PipelineRun.create_skipped_locked(
            trigger_type=trigger_type,
            app_version="0.1.0",
            occurred_at=TIMESTAMP,
        )


@pytest.mark.parametrize(
    "target_status",
    ["sending", DeliveryStatus.SENT, None],
)
def test_invalid_digest_target_preserves_state(target_status: Any) -> None:
    digest = make_digest()
    before = deepcopy(digest)

    with pytest.raises(TypeError, match="DigestStatus"):
        digest.transition_to(target_status, occurred_at=TIMESTAMP)

    assert digest == before


@pytest.mark.parametrize("target_status", ["candidate", "ignored", None])
def test_invalid_news_target_preserves_state(target_status: Any) -> None:
    item = make_news_item()
    before = deepcopy(item)

    with pytest.raises(TypeError, match="NewsItemStatus"):
        item.transition_to(target_status)

    assert item == before


@pytest.mark.parametrize(
    "target_status",
    ["success", "failed", DigestStatus.FAILED, None],
)
def test_invalid_run_target_preserves_state(target_status: Any) -> None:
    run = make_run()
    before = deepcopy(run)

    with pytest.raises(TypeError, match="PipelineRunStatus"):
        run.complete(target_status, finished_at=TIMESTAMP)

    assert run == before


def test_news_item_rejects_string_ignore_reason_on_creation() -> None:
    ignore_reason: Any = "too_old"

    with pytest.raises(TypeError, match="IgnoreReason"):
        replace(
            make_news_item(),
            status=NewsItemStatus.IGNORED,
            ignore_reason=ignore_reason,
        )


def test_string_ignore_reason_preserves_news_item() -> None:
    item = make_news_item()
    before = deepcopy(item)
    ignore_reason: Any = "too_old"

    with pytest.raises(TypeError, match="IgnoreReason"):
        item.transition_to(
            NewsItemStatus.IGNORED,
            ignore_reason=ignore_reason,
        )

    assert item == before


def test_typed_ignore_reason_still_works() -> None:
    item = make_news_item()

    item.transition_to(
        NewsItemStatus.IGNORED,
        ignore_reason=IgnoreReason.TOO_OLD,
    )

    assert item.ignore_reason is IgnoreReason.TOO_OLD


@pytest.mark.parametrize(
    ("validator", "current_status", "target_status"),
    [
        (ensure_digest_transition, "generated", DigestStatus.SENDING),
        (ensure_digest_transition, DigestStatus.GENERATED, "sending"),
        (
            ensure_digest_transition,
            DigestStatus.SENDING,
            DeliveryStatus.SENT,
        ),
        (
            ensure_news_item_transition,
            "collected",
            NewsItemStatus.CANDIDATE,
        ),
        (
            ensure_news_item_transition,
            NewsItemStatus.COLLECTED,
            "candidate",
        ),
        (
            ensure_pipeline_run_transition,
            "running",
            PipelineRunStatus.SUCCESS,
        ),
        (
            ensure_pipeline_run_transition,
            PipelineRunStatus.RUNNING,
            "success",
        ),
    ],
)
def test_state_machine_rejects_incorrect_enum_types(
    validator: Any,
    current_status: Any,
    target_status: Any,
) -> None:
    with pytest.raises(TypeError, match="must be a member"):
        validator(current_status, target_status)


def test_generic_state_machine_rejects_string_current_status() -> None:
    current_status: Any = "generated"

    with pytest.raises(TypeError, match="current_status"):
        ensure_transition_allowed(
            entity="digest",
            current_status=current_status,
            target_status=DigestStatus.SENDING,
            allowed_transitions={},
        )


def test_generic_state_machine_rejects_different_target_enum() -> None:
    target_status: Any = DeliveryStatus.SENT

    with pytest.raises(TypeError, match="target_status"):
        ensure_transition_allowed(
            entity="digest",
            current_status=DigestStatus.SENDING,
            target_status=target_status,
            allowed_transitions={
                DigestStatus.SENDING: frozenset({DigestStatus.SENT}),
            },
        )
