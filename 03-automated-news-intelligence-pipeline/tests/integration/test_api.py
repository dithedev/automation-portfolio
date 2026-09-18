"""Integration tests for FastAPI operational endpoints."""

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.api.main import create_app
from app.application.digest_render import RenderedDigestLine, render_digest_text
from app.config import Settings
from app.domain import (
    Digest,
    DigestItem,
    DigestStatus,
    NewsItem,
    NewsItemStatus,
    PipelineRun,
    PipelineRunStatus,
    Source,
    TriggerType,
)
from app.domain.hashing import content_hash, url_hash
from app.domain.text_sanitize import normalize_title
from app.infrastructure.db.repositories import (
    DigestRepository,
    NewsItemRepository,
    PipelineRunRepository,
    SourceRepository,
)
from app.infrastructure.db.session import transaction_scope
from app.prompts import PROMPT_VERSION

NOW = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)
SUMMARY = (
    "Teams shipping AI features get a concrete product update that clarifies "
    "automation defaults and reduces operational surprise during rollout."
)
ADMIN_KEY = "test-admin-api-key-32-characters!!"


def _settings(**overrides: object) -> Settings:
    data: dict[str, object] = {
        "APP_MODE": "demo",
        "APP_ENV": "development",
        "DATABASE_URL": "postgresql+asyncpg://news:news@localhost:5432/news",
        "TELEGRAM_ENABLED": False,
        "EXPOSE_DEMO_ENDPOINTS": False,
        "SCHEDULER_ENABLED": False,
        "ADMIN_API_KEY": SecretStr(ADMIN_KEY),
    }
    data.update(overrides)
    return Settings(_env_file=None, **data)


def _admin_headers() -> dict[str, str]:
    return {"X-Admin-Api-Key": ADMIN_KEY}


@pytest.mark.asyncio
async def test_health_live_and_ready(
    db_engine: AsyncEngine,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    app = create_app(
        settings=_settings(),
        engine=db_engine,
        session_factory=session_factory,
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        live = await client.get("/health/live")
        ready = await client.get("/health/ready")
    assert live.status_code == 200
    assert live.json() == {"status": "ok"}
    assert ready.status_code == 200
    assert ready.json() == {"status": "ok"}
    assert live.headers["x-content-type-options"] == "nosniff"


@pytest.mark.asyncio
async def test_digests_latest_disabled_by_default(
    db_engine: AsyncEngine,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    app = create_app(
        settings=_settings(EXPOSE_DEMO_ENDPOINTS=False),
        engine=db_engine,
        session_factory=session_factory,
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/digests/latest")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_status_requires_admin_api_key(
    db_engine: AsyncEngine,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    app = create_app(
        settings=_settings(),
        engine=db_engine,
        session_factory=session_factory,
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        missing = await client.get("/status")
        wrong = await client.get("/status", headers={"X-Admin-Api-Key": "wrong-key"})
        live = await client.get("/health/live")

    assert missing.status_code == 401
    assert wrong.status_code == 401
    assert live.status_code == 200


@pytest.mark.asyncio
async def test_status_and_latest_digest_when_enabled(
    db_engine: AsyncEngine,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    run = PipelineRun(trigger_type=TriggerType.MANUAL, app_version="0.1.0")
    run.complete(PipelineRunStatus.SUCCESS)
    source = Source(
        key=f"api-{uuid4().hex[:8]}",
        name="API Source",
        feed_url="https://example.com/api.xml",
        allowed_host="example.com",
        category="artificial_intelligence",
    )
    async with transaction_scope(session_factory) as session:
        await PipelineRunRepository(session).add(run)
        await SourceRepository(session).add(source)
        news_repo = NewsItemRepository(session)
        items: list[DigestItem] = []
        lines: list[RenderedDigestLine] = []
        for index in range(1, 4):
            title = f"AI automation product update number {index} for teams"
            summary = (
                "A long enough summary about AI automation and product delivery "
                f"practices for item {index}."
            )
            url = f"https://example.com/api-{uuid4().hex}"
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
            loaded = await news_repo.get(news.id)
            assert loaded is not None
            if loaded.status is NewsItemStatus.COLLECTED:
                loaded = await news_repo.transition_to(loaded.id, NewsItemStatus.CANDIDATE)
            item = DigestItem(
                news_item_id=loaded.id,
                position=index,
                summary=SUMMARY,
                tag="PRODUCT",
                relevance_score=Decimal("0.9"),
                selection_reason="Useful for product teams.",
            )
            items.append(item)
            lines.append(RenderedDigestLine(item=item, news_item=loaded, source=source))
        title = "AI & Automation Daily Digest — 2026-09-15"
        digest = Digest(
            run_id=run.id,
            digest_date=date(2026, 9, 15),
            title=title,
            rendered_text=render_digest_text(title=title, lines=tuple(lines)),
            prompt_version=PROMPT_VERSION,
            items=tuple(items),
            model="gpt-4o-mini",
            provider_response_id="api-mock",
            input_tokens=1,
            output_tokens=1,
        )
        digest = await DigestRepository(session).create_generated(digest)
        await DigestRepository(session).transition_to(digest.id, DigestStatus.SENDING)
        await DigestRepository(session).transition_to(digest.id, DigestStatus.SENT)

    app = create_app(
        settings=_settings(EXPOSE_DEMO_ENDPOINTS=True),
        engine=db_engine,
        session_factory=session_factory,
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        status = await client.get("/status", headers=_admin_headers())
        latest = await client.get("/digests/latest")

    assert status.status_code == 200
    body = status.json()
    assert body["last_run_status"] == "success"
    assert body["last_sent_digest_at"] is not None
    assert "provider_response_id" not in body

    assert latest.status_code == 200
    latest_body = latest.json()
    assert latest_body["title"] == title
    assert "rendered_text" in latest_body
    assert "provider_response_id" not in latest_body
