from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType
from typing import Any

import pytest

from app.domain import (
    DigestStatus,
    DomainError,
    InvalidStateTransitionError,
    NewsItemStatus,
    PipelineRunStatus,
    ensure_digest_transition,
    ensure_news_item_transition,
    ensure_pipeline_run_transition,
)
from app.domain.state_machine import (
    DIGEST_TRANSITIONS,
    NEWS_ITEM_TRANSITIONS,
    PIPELINE_RUN_TRANSITIONS,
    ensure_transition_allowed,
)

PIPELINE_ALLOWED_PAIRS = {
    (PipelineRunStatus.RUNNING, PipelineRunStatus.SUCCESS),
    (PipelineRunStatus.RUNNING, PipelineRunStatus.PARTIAL_SUCCESS),
    (PipelineRunStatus.RUNNING, PipelineRunStatus.NO_CONTENT),
    (PipelineRunStatus.RUNNING, PipelineRunStatus.FAILED),
}

NEWS_ALLOWED_PAIRS = {
    (NewsItemStatus.COLLECTED, NewsItemStatus.CANDIDATE),
    (NewsItemStatus.COLLECTED, NewsItemStatus.IGNORED),
    (NewsItemStatus.CANDIDATE, NewsItemStatus.USED),
    (NewsItemStatus.CANDIDATE, NewsItemStatus.COLLECTED),
}

DIGEST_ALLOWED_PAIRS = {
    (DigestStatus.GENERATED, DigestStatus.SENDING),
    (DigestStatus.SENDING, DigestStatus.SENT),
    (DigestStatus.SENDING, DigestStatus.FAILED),
    (DigestStatus.FAILED, DigestStatus.SENDING),
}


@pytest.mark.parametrize("current_status", list(PipelineRunStatus))
@pytest.mark.parametrize("target_status", list(PipelineRunStatus))
def test_pipeline_run_transition_matrix(
    current_status: PipelineRunStatus,
    target_status: PipelineRunStatus,
) -> None:
    if (current_status, target_status) in PIPELINE_ALLOWED_PAIRS:
        ensure_pipeline_run_transition(current_status, target_status)
    else:
        with pytest.raises(InvalidStateTransitionError):
            ensure_pipeline_run_transition(current_status, target_status)


@pytest.mark.parametrize("current_status", list(NewsItemStatus))
@pytest.mark.parametrize("target_status", list(NewsItemStatus))
def test_news_item_transition_matrix(
    current_status: NewsItemStatus,
    target_status: NewsItemStatus,
) -> None:
    if (current_status, target_status) in NEWS_ALLOWED_PAIRS:
        ensure_news_item_transition(current_status, target_status)
    else:
        with pytest.raises(InvalidStateTransitionError):
            ensure_news_item_transition(current_status, target_status)


@pytest.mark.parametrize("current_status", list(DigestStatus))
@pytest.mark.parametrize("target_status", list(DigestStatus))
def test_digest_transition_matrix(
    current_status: DigestStatus,
    target_status: DigestStatus,
) -> None:
    if (current_status, target_status) in DIGEST_ALLOWED_PAIRS:
        ensure_digest_transition(current_status, target_status)
    else:
        with pytest.raises(InvalidStateTransitionError):
            ensure_digest_transition(current_status, target_status)


def test_transition_error_preserves_transition_details() -> None:
    with pytest.raises(InvalidStateTransitionError) as error:
        ensure_digest_transition(
            DigestStatus.SENT,
            DigestStatus.SENDING,
        )

    assert isinstance(error.value, DomainError)
    assert error.value.entity == "digest"
    assert error.value.current_status == "sent"
    assert error.value.target_status == "sending"
    assert str(error.value) == ("Invalid digest state transition: 'sent' -> 'sending'")


def test_generic_transition_validator_accepts_custom_table() -> None:
    transitions = {
        DigestStatus.GENERATED: frozenset({DigestStatus.SENDING}),
    }

    ensure_transition_allowed(
        entity="digest",
        current_status=DigestStatus.GENERATED,
        target_status=DigestStatus.SENDING,
        allowed_transitions=transitions,
    )


def test_missing_status_has_no_outgoing_transitions() -> None:
    transitions: Mapping[DigestStatus, frozenset[DigestStatus]] = {}

    with pytest.raises(InvalidStateTransitionError):
        ensure_transition_allowed(
            entity="digest",
            current_status=DigestStatus.GENERATED,
            target_status=DigestStatus.SENDING,
            allowed_transitions=transitions,
        )


@pytest.mark.parametrize(
    "transitions",
    [
        PIPELINE_RUN_TRANSITIONS,
        NEWS_ITEM_TRANSITIONS,
        DIGEST_TRANSITIONS,
    ],
)
def test_transition_tables_are_read_only(
    transitions: Any,
) -> None:
    assert isinstance(transitions, MappingProxyType)

    current_status = next(iter(transitions))

    with pytest.raises(TypeError):
        transitions[current_status] = frozenset()


@pytest.mark.parametrize(
    "transitions",
    [
        PIPELINE_RUN_TRANSITIONS,
        NEWS_ITEM_TRANSITIONS,
        DIGEST_TRANSITIONS,
    ],
)
def test_transition_targets_are_immutable(
    transitions: Mapping[StrEnum, frozenset[StrEnum]],
) -> None:
    for targets in transitions.values():
        assert isinstance(targets, frozenset)


def test_state_machine_public_functions_have_docstrings() -> None:
    for function in (
        ensure_transition_allowed,
        ensure_pipeline_run_transition,
        ensure_news_item_transition,
        ensure_digest_transition,
    ):
        assert function.__doc__


def test_domain_exceptions_have_docstrings() -> None:
    assert DomainError.__doc__
    assert InvalidStateTransitionError.__doc__
    assert InvalidStateTransitionError.__init__.__doc__
