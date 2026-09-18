"""Unit tests for digest structured-output schema and post-validation."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.application.digest_render import RenderedDigestLine, render_digest_text
from app.application.digest_schema import DigestModelOutput
from app.application.digest_validation import (
    CandidateContext,
    DigestPostValidationError,
    validate_model_output,
)
from app.domain import NewsItem, NewsItemStatus, Source
from app.domain.enums import DigestTag
from app.domain.hashing import content_hash, url_hash
from app.domain.text_sanitize import normalize_title

NOW = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)
VALID_SUMMARY = (
    "Teams shipping AI features get a concrete product update that clarifies "
    "automation defaults and reduces operational surprise during rollout."
)


def _item(*, status: NewsItemStatus = NewsItemStatus.CANDIDATE) -> NewsItem:
    title = "AI automation product update for teams"
    summary = "A long enough summary about AI automation and product delivery practices."
    url = f"https://example.com/{uuid4().hex}"
    normalized = normalize_title(title)
    return NewsItem(
        source_id=uuid4(),
        original_url=url,
        canonical_url=url,
        url_hash=url_hash(url),
        title=title,
        normalized_title=normalized,
        sanitized_summary=summary,
        content_hash=content_hash(normalized, summary),
        published_at=NOW,
        collected_at=NOW,
        status=status,
    )


def test_schema_accepts_valid_output() -> None:
    output = DigestModelOutput.model_validate(
        {
            "digest_title": "AI & Automation Daily Digest — 2026-09-15",
            "items": [
                {
                    "candidate_id": "c_01",
                    "summary": VALID_SUMMARY,
                    "tag": "PRODUCT",
                    "relevance_score": "0.9",
                    "selection_reason": "Useful for product teams.",
                }
            ],
        }
    )
    assert output.items[0].tag is DigestTag.PRODUCT


def test_structured_output_schema_has_no_anyof() -> None:
    """OpenAI strict structured outputs reject anyOf (e.g. from Decimal)."""
    import json

    schema = json.dumps(DigestModelOutput.model_json_schema())
    assert "anyOf" not in schema
    assert '"type": "number"' in schema or '"type":"number"' in schema


def test_schema_rejects_duplicate_candidate_ids() -> None:
    with pytest.raises(ValidationError):
        DigestModelOutput.model_validate(
            {
                "digest_title": "Title",
                "items": [
                    {
                        "candidate_id": "c_01",
                        "summary": VALID_SUMMARY,
                        "tag": "PRODUCT",
                        "relevance_score": "0.9",
                        "selection_reason": "One",
                    },
                    {
                        "candidate_id": "c_01",
                        "summary": VALID_SUMMARY,
                        "tag": "OTHER",
                        "relevance_score": "0.8",
                        "selection_reason": "Two",
                    },
                ],
            }
        )


def test_post_validation_rejects_unknown_candidate() -> None:
    news = _item()
    source = Source(
        id=news.source_id,
        key="src",
        name="Source",
        feed_url="https://example.com/feed.xml",
        allowed_host="example.com",
        category="artificial_intelligence",
    )
    contexts = {
        "c_01": CandidateContext(
            candidate_id="c_01",
            news_item=news,
            source=source,
            pre_score=0.5,
        )
    }
    output = DigestModelOutput.model_validate(
        {
            "digest_title": "Title",
            "items": [
                {
                    "candidate_id": "c_99",
                    "summary": VALID_SUMMARY,
                    "tag": "PRODUCT",
                    "relevance_score": "0.9",
                    "selection_reason": "Bad id",
                }
            ],
        }
    )

    with pytest.raises(DigestPostValidationError) as raised:
        validate_model_output(output, contexts=contexts, min_items=1, max_items=1)

    assert any("unknown candidate_id" in error for error in raised.value.errors)


def test_post_validation_rejects_url_in_summary() -> None:
    news = _item()
    source = Source(
        id=news.source_id,
        key="src",
        name="Source",
        feed_url="https://example.com/feed.xml",
        allowed_host="example.com",
        category="artificial_intelligence",
    )
    contexts = {
        "c_01": CandidateContext(
            candidate_id="c_01",
            news_item=news,
            source=source,
            pre_score=0.5,
        )
    }
    summary = (
        "Visit https://evil.example for details about this AI automation product "
        "update that should never include a raw URL in the summary text."
    )
    output = DigestModelOutput.model_validate(
        {
            "digest_title": "Title",
            "items": [
                {
                    "candidate_id": "c_01",
                    "summary": summary,
                    "tag": "PRODUCT",
                    "relevance_score": "0.9",
                    "selection_reason": "Contains URL",
                }
            ],
        }
    )

    with pytest.raises(DigestPostValidationError):
        validate_model_output(output, contexts=contexts, min_items=1, max_items=1)


def _context(news: NewsItem) -> tuple[Source, dict[str, CandidateContext]]:
    source = Source(
        id=news.source_id,
        key="src",
        name="Source",
        feed_url="https://example.com/feed.xml",
        allowed_host="example.com",
        category="artificial_intelligence",
    )
    contexts = {
        "c_01": CandidateContext(
            candidate_id="c_01",
            news_item=news,
            source=source,
            pre_score=0.5,
        )
    }
    return source, contexts


def _valid_item_payload(candidate_id: str = "c_01", *, summary: str = VALID_SUMMARY) -> dict:
    return {
        "candidate_id": candidate_id,
        "summary": summary,
        "tag": "PRODUCT",
        "relevance_score": "0.9",
        "selection_reason": "Useful for product teams.",
    }


def test_post_validation_rejects_used_candidate() -> None:
    news = _item(status=NewsItemStatus.USED)
    _, contexts = _context(news)
    output = DigestModelOutput.model_validate(
        {
            "digest_title": "Title",
            "items": [_valid_item_payload()],
        }
    )
    with pytest.raises(DigestPostValidationError) as raised:
        validate_model_output(output, contexts=contexts, min_items=1, max_items=1)
    assert any("already used" in error for error in raised.value.errors)


def test_post_validation_rejects_non_candidate_status() -> None:
    news = _item(status=NewsItemStatus.COLLECTED)
    _, contexts = _context(news)
    output = DigestModelOutput.model_validate(
        {
            "digest_title": "Title",
            "items": [_valid_item_payload()],
        }
    )
    with pytest.raises(DigestPostValidationError) as raised:
        validate_model_output(output, contexts=contexts, min_items=1, max_items=1)
    assert any("not in candidate status" in error for error in raised.value.errors)


def test_post_validation_rejects_short_summary() -> None:
    news = _item()
    _, contexts = _context(news)
    from app.application.digest_schema import DigestModelItem

    short_item = DigestModelItem.model_construct(
        candidate_id="c_01",
        summary="too short for digest summary rules",
        tag=DigestTag.PRODUCT,
        relevance_score=0.9,
        selection_reason="Useful for product teams.",
    )
    output = DigestModelOutput.model_construct(
        digest_title="Title",
        items=[short_item],
    )
    with pytest.raises(DigestPostValidationError) as raised:
        validate_model_output(output, contexts=contexts, min_items=1, max_items=1)
    assert any("summary length" in error for error in raised.value.errors)


def test_post_validation_rejects_telegram_markup_in_summary() -> None:
    news = _item()
    _, contexts = _context(news)
    summary = (
        "Teams shipping AI features get a concrete <b>product</b> update that clarifies "
        "automation defaults and reduces operational surprise during rollout."
    )
    output = DigestModelOutput.model_validate(
        {
            "digest_title": "Title",
            "items": [_valid_item_payload(summary=summary)],
        }
    )
    with pytest.raises(DigestPostValidationError) as raised:
        validate_model_output(output, contexts=contexts, min_items=1, max_items=1)
    assert any("markup" in error for error in raised.value.errors)


def test_post_validation_rejects_item_count_below_minimum() -> None:
    news = _item()
    _, contexts = _context(news)
    output = DigestModelOutput.model_validate(
        {
            "digest_title": "Title",
            "items": [_valid_item_payload()],
        }
    )
    with pytest.raises(DigestPostValidationError) as raised:
        validate_model_output(output, contexts=contexts, min_items=2, max_items=5)
    assert any("item count must be between" in error for error in raised.value.errors)


def test_renderer_includes_source_and_url() -> None:
    news = _item()
    source = Source(
        id=news.source_id,
        key="src",
        name="Publisher",
        feed_url="https://example.com/feed.xml",
        allowed_host="example.com",
        category="artificial_intelligence",
    )
    from app.domain import DigestItem

    item = DigestItem(
        news_item_id=news.id,
        position=1,
        summary=VALID_SUMMARY,
        tag="PRODUCT",
        relevance_score=Decimal("0.9"),
        selection_reason="Useful",
    )
    text = render_digest_text(
        title="AI & Automation Daily Digest — 2026-09-15",
        lines=(RenderedDigestLine(item=item, news_item=news, source=source),),
    )

    assert "<b>1. " in text
    assert "Read on Publisher" in text
    assert f'href="{news.canonical_url}"' in text
    assert "<blockquote>🏷 PRODUCT</blockquote>" in text
    assert news.canonical_url not in text.replace(f'href="{news.canonical_url}"', "")
    assert len(text) < 4096
