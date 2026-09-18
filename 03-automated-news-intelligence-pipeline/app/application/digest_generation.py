"""Generate and persist a digest from selected candidates."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from app.application.digest_render import RenderedDigestLine, render_digest_text
from app.application.digest_validation import (
    CandidateContext,
    DigestPostValidationError,
    build_digest,
    ensure_telegram_splittable,
    format_validation_errors,
    validate_model_output,
)
from app.application.llm_types import LlmError
from app.application.ports import LlmClient
from app.config import Settings
from app.domain import Digest, NewsItem, Source
from app.domain.enums import ErrorCode
from app.observability import log_event
from app.prompts import SYSTEM_PROMPT, render_articles
from app.texts.llm import LLM_POST_VALIDATION_FAILED

EXCERPT_MAX_CHARS = 1500


def build_candidate_contexts(
    *,
    news_items: tuple[NewsItem, ...],
    sources_by_id: dict[UUID, Source],
    scores_by_id: dict[UUID, float],
) -> dict[str, CandidateContext]:
    """Assign opaque candidate ids in stable input order."""
    contexts: dict[str, CandidateContext] = {}
    for index, item in enumerate(news_items, start=1):
        source = sources_by_id[item.source_id]
        candidate_id = f"c_{index:02d}"
        contexts[candidate_id] = CandidateContext(
            candidate_id=candidate_id,
            news_item=item,
            source=source,
            pre_score=scores_by_id.get(item.id, 0.0),
        )
    return contexts


def articles_payload(contexts: dict[str, CandidateContext]) -> list[dict[str, str]]:
    """Build the JSON-serializable article list for the model."""
    articles: list[dict[str, str]] = []
    for candidate_id, context in contexts.items():
        excerpt = context.news_item.sanitized_summary[:EXCERPT_MAX_CHARS]
        published = ""
        if context.news_item.published_at is not None:
            published = context.news_item.published_at.isoformat()
        articles.append(
            {
                "candidate_id": candidate_id,
                "source_name": context.source.name,
                "title": context.news_item.title,
                "summary": excerpt,
                "published_at": published,
                "relevance_score": f"{context.pre_score:.3f}",
            }
        )
    return articles


def _context_by_news_id(
    contexts: dict[str, CandidateContext],
) -> dict[UUID, CandidateContext]:
    return {context.news_item.id: context for context in contexts.values()}


async def generate_validated_digest(
    *,
    llm_client: LlmClient,
    settings: Settings,
    run_id: UUID,
    digest_date: date,
    contexts: dict[str, CandidateContext],
) -> Digest:
    """Call the LLM once, repair once on post-validation failure, then build Digest."""
    desired = min(
        settings.digest_top_articles,
        settings.max_digest_items,
        len(contexts),
    )
    min_items = min(settings.min_digest_items, desired)
    articles_json = render_articles(articles_payload(contexts))

    log_event("llm.request_started", candidate_count=len(contexts), desired=desired)
    result = await llm_client.generate_digest(
        system=SYSTEM_PROMPT,
        articles_json=articles_json,
        model=settings.openai_model,
        max_output_tokens=settings.openai_max_output_tokens,
    )

    try:
        digest_items = validate_model_output(
            result.output,
            contexts=contexts,
            min_items=min_items,
            max_items=desired,
        )
    except DigestPostValidationError as first_error:
        log_event(
            "llm.output_rejected",
            stage="primary",
            error_count=len(first_error.errors),
        )
        repair = await llm_client.generate_digest(
            system=SYSTEM_PROMPT,
            articles_json=articles_json,
            model=settings.openai_model,
            max_output_tokens=settings.openai_max_output_tokens,
            repair_errors=format_validation_errors(first_error.errors),
        )
        try:
            digest_items = validate_model_output(
                repair.output,
                contexts=contexts,
                min_items=min_items,
                max_items=desired,
            )
            result = repair
        except DigestPostValidationError as second_error:
            log_event(
                "llm.output_rejected",
                stage="repair",
                error_count=len(second_error.errors),
            )
            summary = format_validation_errors(second_error.errors)[:500]
            raise LlmError(
                ErrorCode.OUTPUT_POST_VALIDATION_FAILED,
                summary or LLM_POST_VALIDATION_FAILED,
            ) from second_error

    by_news_id = _context_by_news_id(contexts)
    lines = tuple(
        RenderedDigestLine(
            item=item,
            news_item=by_news_id[item.news_item_id].news_item,
            source=by_news_id[item.news_item_id].source,
        )
        for item in digest_items
    )
    ensure_telegram_splittable(title=result.output.digest_title, lines=lines)
    rendered = render_digest_text(title=result.output.digest_title, lines=lines)

    log_event(
        "llm.request_succeeded",
        selected_count=len(digest_items),
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
    )
    return build_digest(
        run_id=run_id,
        digest_date=digest_date,
        model_output=result.output,
        digest_items=digest_items,
        rendered_text=rendered,
        model=settings.openai_model,
        provider_response_id=result.response_id,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
    )
