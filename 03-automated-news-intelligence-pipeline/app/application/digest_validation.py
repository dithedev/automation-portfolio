"""Post-validate model digest output against local candidate data."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from app.application.digest_render import (
    TELEGRAM_MESSAGE_LIMIT,
    DigestSplitError,
    RenderedDigestLine,
    split_digest_messages,
)
from app.application.digest_schema import DigestModelOutput
from app.domain import Digest, DigestItem, NewsItem, NewsItemStatus, Source
from app.domain.enums import DigestTag
from app.prompts import PROMPT_VERSION
from app.texts.llm import LLM_POST_VALIDATION_FAILED

_URL_OR_MARKUP = re.compile(
    r"(https?://|www\.|<|>|\[/?(b|i|u|code|pre|a)\]|telegram\.me)",
    re.IGNORECASE,
)

__all__ = [
    "TELEGRAM_MESSAGE_LIMIT",
    "CandidateContext",
    "DigestPostValidationError",
    "build_digest",
    "ensure_telegram_splittable",
    "format_validation_errors",
    "validate_model_output",
]


@dataclass(frozen=True, slots=True, kw_only=True)
class CandidateContext:
    """Local data for one opaque candidate id."""

    candidate_id: str
    news_item: NewsItem
    source: Source
    pre_score: float


class DigestPostValidationError(ValueError):
    """Collect human-readable post-validation failures for repair."""

    def __init__(self, errors: tuple[str, ...]) -> None:
        self.errors = errors
        super().__init__(LLM_POST_VALIDATION_FAILED)


def _summary_clean(summary: str) -> list[str]:
    issues: list[str] = []
    if not 80 <= len(summary) <= 280:
        issues.append("summary length must be between 80 and 280 characters")
    if _URL_OR_MARKUP.search(summary):
        issues.append("summary must not contain URLs, HTML, or Telegram markup")
    return issues


def validate_model_output(
    output: DigestModelOutput,
    *,
    contexts: dict[str, CandidateContext],
    min_items: int,
    max_items: int,
) -> tuple[DigestItem, ...]:
    """Validate model output and map opaque ids onto domain digest items."""
    errors: list[str] = []
    items = output.items

    if not min_items <= len(items) <= max_items:
        errors.append(f"item count must be between {min_items} and {max_items}, got {len(items)}")

    seen: set[str] = set()
    digest_items: list[DigestItem] = []

    for position, item in enumerate(items, start=1):
        if item.candidate_id in seen:
            errors.append(f"duplicate candidate_id {item.candidate_id}")
        seen.add(item.candidate_id)

        context = contexts.get(item.candidate_id)
        if context is None:
            errors.append(f"unknown candidate_id {item.candidate_id}")
            continue

        news = context.news_item
        if news.status is NewsItemStatus.USED:
            errors.append(f"candidate {item.candidate_id} was already used")
        elif news.status is not NewsItemStatus.CANDIDATE:
            errors.append(f"candidate {item.candidate_id} is not in candidate status")

        errors.extend(_summary_clean(item.summary))

        try:
            DigestTag(item.tag)
        except ValueError:
            errors.append(f"invalid tag for {item.candidate_id}")

        if errors:
            continue

        digest_items.append(
            DigestItem(
                news_item_id=news.id,
                position=position,
                summary=item.summary,
                tag=item.tag.value if isinstance(item.tag, DigestTag) else str(item.tag),
                relevance_score=Decimal(str(item.relevance_score)),
                selection_reason=item.selection_reason,
            )
        )

    if errors:
        raise DigestPostValidationError(tuple(errors))

    return tuple(digest_items)


def ensure_telegram_splittable(
    *,
    title: str,
    lines: tuple[RenderedDigestLine, ...],
) -> tuple[str, ...]:
    """Require that the digest can be split into Telegram-safe parts."""
    try:
        return split_digest_messages(title=title, lines=lines)
    except DigestSplitError as error:
        raise DigestPostValidationError((str(error),)) from error


def build_digest(
    *,
    run_id: UUID,
    digest_date: date,
    model_output: DigestModelOutput,
    digest_items: tuple[DigestItem, ...],
    rendered_text: str,
    model: str,
    provider_response_id: str | None,
    input_tokens: int | None,
    output_tokens: int | None,
) -> Digest:
    """Assemble a generated digest entity ready for persistence."""
    return Digest(
        run_id=run_id,
        digest_date=digest_date,
        title=model_output.digest_title.strip(),
        rendered_text=rendered_text,
        prompt_version=PROMPT_VERSION,
        items=digest_items,
        model=model,
        provider_response_id=provider_response_id,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


def format_validation_errors(errors: tuple[str, ...]) -> str:
    """Serialize validation errors for a repair prompt turn."""
    return "\n".join(f"- {error}" for error in errors)
