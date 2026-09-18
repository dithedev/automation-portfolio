"""Unit tests for Telegram mock client and delivery retries."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.application.digest_delivery import DigestDeliveryService
from app.config import Settings
from app.domain import (
    Digest,
    DigestItem,
    DigestStatus,
    NewsItem,
    NewsItemStatus,
    PipelineRun,
    Source,
    TriggerType,
)
from app.domain.hashing import content_hash, url_hash
from app.domain.text_sanitize import normalize_title
from app.infrastructure.db.repositories import (
    DeliveryAttemptRepository,
    DigestRepository,
    NewsItemRepository,
    PipelineRunRepository,
    SourceRepository,
)
from app.infrastructure.db.session import transaction_scope
from app.infrastructure.telegram.mock_client import MockTelegramClient
from app.prompts import PROMPT_VERSION

NOW = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)
SUMMARY = (
    "Teams shipping AI features get a concrete product update that clarifies "
    "automation defaults and reduces operational surprise during rollout."
)


def _settings(**overrides: object) -> Settings:
    data: dict[str, object] = {
        "APP_MODE": "demo",
        "DATABASE_URL": "postgresql+asyncpg://news:news@localhost:5432/news",
        "TELEGRAM_ENABLED": True,
        "TELEGRAM_CHAT_ID": "123456789",
        "TELEGRAM_MAX_RETRIES": 3,
    }
    data.update(overrides)
    return Settings(_env_file=None, **data)


async def _seed_digest(
    session_factory: async_sessionmaker[AsyncSession],
) -> Digest:
    run = PipelineRun(trigger_type=TriggerType.MANUAL, app_version="0.1.0")
    source = Source(
        key=f"delivery-{uuid4().hex[:8]}",
        name="Delivery Source",
        feed_url="https://example.com/delivery.xml",
        allowed_host="example.com",
        category="artificial_intelligence",
    )
    items: list[DigestItem] = []
    async with transaction_scope(session_factory) as session:
        await PipelineRunRepository(session).add(run)
        await SourceRepository(session).add(source)
        news_repo = NewsItemRepository(session)
        for index in range(1, 4):
            title = f"AI automation product update number {index} for teams"
            summary = (
                "A long enough summary about AI automation and product delivery "
                f"practices for item {index}."
            )
            url = f"https://example.com/delivery-{uuid4().hex}"
            normalized = normalize_title(title)
            news = NewsItem(
                source_id=source.id,
                original_url=url,
                canonical_url=url,
                url_hash=url_hash(url),
                title=title,
                normalized_title=normalized,
                sanitized_summary=summary,
                content_hash=content_hash(normalized, summary),
                published_at=NOW,
                collected_at=NOW,
                status=NewsItemStatus.CANDIDATE,
            )
            await news_repo.add_if_new(news)
            # mark candidate explicitly if collected
            loaded = await news_repo.get(news.id)
            assert loaded is not None
            if loaded.status is NewsItemStatus.COLLECTED:
                loaded = await news_repo.transition_to(
                    loaded.id,
                    NewsItemStatus.CANDIDATE,
                )
            items.append(
                DigestItem(
                    news_item_id=loaded.id,
                    position=index,
                    summary=SUMMARY,
                    tag="PRODUCT",
                    relevance_score=Decimal("0.9"),
                    selection_reason="Useful for product teams.",
                )
            )
        digest = Digest(
            run_id=run.id,
            digest_date=date(2026, 9, 15),
            title="AI & Automation Daily Digest — 2026-09-15",
            rendered_text="placeholder\n",
            prompt_version=PROMPT_VERSION,
            items=tuple(items),
            model="gpt-4o-mini",
            provider_response_id="mock-delivery",
            input_tokens=10,
            output_tokens=10,
        )
        # rebuild rendered via service path using create_generated requirements
        from app.application.digest_render import RenderedDigestLine, render_digest_text

        lines = []
        for item in digest.items:
            news = await news_repo.get(item.news_item_id)
            assert news is not None
            lines.append(
                RenderedDigestLine(item=item, news_item=news, source=source),
            )
        digest = Digest(
            run_id=run.id,
            digest_date=date(2026, 9, 15),
            title=digest.title,
            rendered_text=render_digest_text(title=digest.title, lines=tuple(lines)),
            prompt_version=PROMPT_VERSION,
            items=tuple(items),
            model="gpt-4o-mini",
            provider_response_id="mock-delivery",
            input_tokens=10,
            output_tokens=10,
        )
        return await DigestRepository(session).create_generated(digest)


@pytest.mark.asyncio
async def test_mock_telegram_happy_path() -> None:
    client = MockTelegramClient()
    result = await client.send_message(chat_id="1", text="hello")
    assert result.message_id == 1001
    assert client.calls == [("1", "hello")]


@pytest.mark.asyncio
async def test_delivery_marks_digest_sent(
    db_engine: AsyncEngine,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    digest = await _seed_digest(session_factory)
    telegram = MockTelegramClient()
    service = DigestDeliveryService(
        session_factory=session_factory,
        telegram_client=telegram,
        settings=_settings(),
    )
    outcome = await service.deliver(digest.id)
    assert outcome.status is DigestStatus.SENT
    assert outcome.parts_sent >= 1
    assert len(telegram.calls) == outcome.parts_sent
    sent_text = telegram.calls[0][1]
    assert sent_text.startswith("🗞 <b>")
    assert "<blockquote>🏷 PRODUCT</blockquote>" in sent_text
    assert "Read on Delivery Source" in sent_text
    assert "AI-generated digest" in sent_text
    assert "Always verify details at the original source." in sent_text
    assert 'href="https://example.com/' in sent_text
    assert "\nhttps://example.com/" not in sent_text

    async with transaction_scope(session_factory) as session:
        stored = await DigestRepository(session).get(digest.id)
        attempts = await DeliveryAttemptRepository(session).list_for_digest(digest.id)
    assert stored is not None
    assert stored.status is DigestStatus.SENT
    assert all(attempt.status.value == "sent" for attempt in attempts)


@pytest.mark.asyncio
async def test_delivery_retries_rate_limit_then_succeeds(
    db_engine: AsyncEngine,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    digest = await _seed_digest(session_factory)
    telegram = MockTelegramClient()
    telegram.force_rate_limited_once(retry_after_seconds=0)
    service = DigestDeliveryService(
        session_factory=session_factory,
        telegram_client=telegram,
        settings=_settings(),
    )
    outcome = await service.deliver(digest.id)
    assert outcome.status is DigestStatus.SENT
    async with transaction_scope(session_factory) as session:
        attempts = await DeliveryAttemptRepository(session).list_for_digest(digest.id)
    assert len(attempts) >= 2
    assert attempts[0].status.value == "failed"
    assert attempts[-1].status.value == "sent"


@pytest.mark.asyncio
async def test_delivery_permanent_failure_leaves_digest_failed(
    db_engine: AsyncEngine,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    digest = await _seed_digest(session_factory)
    telegram = MockTelegramClient()
    telegram.force_permanent_failure()
    service = DigestDeliveryService(
        session_factory=session_factory,
        telegram_client=telegram,
        settings=_settings(),
    )
    outcome = await service.deliver(digest.id)
    assert outcome.status is DigestStatus.FAILED

    async with transaction_scope(session_factory) as session:
        stored = await DigestRepository(session).get(digest.id)
        for item in digest.items:
            news = await NewsItemRepository(session).get(item.news_item_id)
            assert news is not None
            assert news.status is NewsItemStatus.USED
    assert stored is not None
    assert stored.status is DigestStatus.FAILED


@pytest.mark.asyncio
async def test_delivery_skips_already_sent_parts(
    db_engine: AsyncEngine,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    digest = await _seed_digest(session_factory)
    from app.domain import DeliveryAttempt

    async with transaction_scope(session_factory) as session:
        attempt = DeliveryAttempt(
            digest_id=digest.id,
            part_number=1,
            attempt_number=1,
        )
        attempt.mark_sent(telegram_message_id=42)
        await DeliveryAttemptRepository(session).add(attempt)

    telegram = MockTelegramClient()
    service = DigestDeliveryService(
        session_factory=session_factory,
        telegram_client=telegram,
        settings=_settings(),
    )
    outcome = await service.deliver(digest.id)
    assert outcome.status is DigestStatus.SENT
    assert telegram.calls == []

    digest = await _seed_digest(session_factory)
    telegram = MockTelegramClient()
    service = DigestDeliveryService(
        session_factory=session_factory,
        telegram_client=telegram,
        settings=_settings(),
    )
    first = await service.deliver(digest.id)
    second = await service.deliver(digest.id)
    assert first.status is DigestStatus.SENT
    assert second.skipped is True
    assert len(telegram.calls) == first.parts_sent
