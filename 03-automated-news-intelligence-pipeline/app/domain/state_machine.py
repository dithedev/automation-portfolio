"""Allowed lifecycle transitions for pipeline runs, news items, and digests."""

from collections.abc import Mapping, Set
from enum import StrEnum
from types import MappingProxyType

from app.domain.enum_validation import ensure_enum_member
from app.domain.enums import DigestStatus, NewsItemStatus, PipelineRunStatus
from app.domain.exceptions import InvalidStateTransitionError

PIPELINE_RUN_TRANSITIONS: Mapping[
    PipelineRunStatus,
    frozenset[PipelineRunStatus],
] = MappingProxyType(
    {
        PipelineRunStatus.RUNNING: frozenset(
            {
                PipelineRunStatus.SUCCESS,
                PipelineRunStatus.PARTIAL_SUCCESS,
                PipelineRunStatus.NO_CONTENT,
                PipelineRunStatus.FAILED,
            }
        ),
    }
)

NEWS_ITEM_TRANSITIONS: Mapping[
    NewsItemStatus,
    frozenset[NewsItemStatus],
] = MappingProxyType(
    {
        NewsItemStatus.COLLECTED: frozenset(
            {
                NewsItemStatus.CANDIDATE,
                NewsItemStatus.IGNORED,
            }
        ),
        NewsItemStatus.CANDIDATE: frozenset(
            {
                NewsItemStatus.USED,
                NewsItemStatus.COLLECTED,
            }
        ),
    }
)

DIGEST_TRANSITIONS: Mapping[
    DigestStatus,
    frozenset[DigestStatus],
] = MappingProxyType(
    {
        DigestStatus.GENERATED: frozenset({DigestStatus.SENDING}),
        DigestStatus.SENDING: frozenset(
            {
                DigestStatus.SENT,
                DigestStatus.FAILED,
            }
        ),
        DigestStatus.FAILED: frozenset({DigestStatus.SENDING}),
    }
)


def ensure_transition_allowed[StatusT: StrEnum](
    *,
    entity: str,
    current_status: StatusT,
    target_status: StatusT,
    allowed_transitions: Mapping[StatusT, Set[StatusT]],
) -> None:
    """Validate a transition without changing entity state.

    Both statuses must belong to the same enum. A status absent from the
    transition table has no outgoing transitions.

    Raises:
        TypeError: If statuses are not members of the same enum.
        InvalidStateTransitionError: If the target status is not allowed.
    """
    ensure_enum_member(current_status, StrEnum, "current_status")
    ensure_enum_member(target_status, type(current_status), "target_status")
    allowed_targets = allowed_transitions.get(current_status, frozenset())

    if target_status not in allowed_targets:
        raise InvalidStateTransitionError(
            entity=entity,
            current_status=current_status.value,
            target_status=target_status.value,
        )


def ensure_pipeline_run_transition(
    current_status: PipelineRunStatus,
    target_status: PipelineRunStatus,
) -> None:
    """Require an allowed transition between PipelineRunStatus members.

    Raises:
        TypeError: If either status belongs to a different type.
        InvalidStateTransitionError: If the transition is forbidden.
    """
    ensure_enum_member(current_status, PipelineRunStatus, "current_status")
    ensure_enum_member(target_status, PipelineRunStatus, "target_status")
    ensure_transition_allowed(
        entity="pipeline run",
        current_status=current_status,
        target_status=target_status,
        allowed_transitions=PIPELINE_RUN_TRANSITIONS,
    )


def ensure_news_item_transition(
    current_status: NewsItemStatus,
    target_status: NewsItemStatus,
) -> None:
    """Require an allowed transition between NewsItemStatus members.

    Candidates may return to collected when selection is not committed.
    Used and ignored items have no outgoing transitions.

    Raises:
        TypeError: If either status belongs to a different type.
        InvalidStateTransitionError: If the transition is forbidden.
    """
    ensure_enum_member(current_status, NewsItemStatus, "current_status")
    ensure_enum_member(target_status, NewsItemStatus, "target_status")
    ensure_transition_allowed(
        entity="news item",
        current_status=current_status,
        target_status=target_status,
        allowed_transitions=NEWS_ITEM_TRANSITIONS,
    )


def ensure_digest_transition(
    current_status: DigestStatus,
    target_status: DigestStatus,
) -> None:
    """Require an allowed transition between DigestStatus members.

    Failed digests may be retried; sent digests are terminal.

    Raises:
        TypeError: If either status belongs to a different type.
        InvalidStateTransitionError: If the transition is forbidden.
    """
    ensure_enum_member(current_status, DigestStatus, "current_status")
    ensure_enum_member(target_status, DigestStatus, "target_status")
    ensure_transition_allowed(
        entity="digest",
        current_status=current_status,
        target_status=target_status,
        allowed_transitions=DIGEST_TRANSITIONS,
    )
