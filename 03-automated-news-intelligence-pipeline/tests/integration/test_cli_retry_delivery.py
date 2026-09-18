"""CLI smoke tests for retry-delivery."""

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from typer.testing import CliRunner

from app.application.digest_render import RenderedDigestLine, render_digest_text
from app.cli.app import _retry_delivery, cli
from app.config import Settings
from app.domain import (
    Digest,
    DigestItem,
    DigestStatus,
    ErrorCode,
    NewsItem,
    NewsItemStatus,
    PipelineRun,
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
from app.infrastructure.telegram.mock_client import MockTelegramClient
from app.prompts import PROMPT_VERSION
from app.runtime import PipelineRuntime

NOW = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)
SUMMARY = (
    "Teams shipping AI features get a concrete product update that clarifies "
    "automation defaults and reduces operational surprise during rollout."
)


@pytest.mark.asyncio
async def test_retry_delivery_cli_sends_failed_digest(
    db_engine: AsyncEngine,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = PipelineRun(trigger_type=TriggerType.MANUAL, app_version="0.1.0")
    source = Source(
        key=f"cli-{uuid4().hex[:8]}",
        name="CLI Source",
        feed_url="https://example.com/cli.xml",
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
            url = f"https://example.com/cli-{uuid4().hex}"
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
                loaded = await news_repo.transition_to(
                    loaded.id,
                    NewsItemStatus.CANDIDATE,
                )
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
            provider_response_id="cli-mock",
            input_tokens=1,
            output_tokens=1,
        )
        digest = await DigestRepository(session).create_generated(digest)
        digest = await DigestRepository(session).transition_to(
            digest.id,
            DigestStatus.SENDING,
        )
        digest = await DigestRepository(session).transition_to(
            digest.id,
            DigestStatus.FAILED,
            error_code=ErrorCode.TELEGRAM_PERMANENT_FAILURE,
            error_summary="forced",
        )
        digest_id = digest.id

    telegram = MockTelegramClient()
    settings = Settings(
        _env_file=None,
        APP_MODE="demo",
        DATABASE_URL="postgresql+asyncpg://news:news@localhost:5432/news",
        TELEGRAM_ENABLED=True,
        TELEGRAM_CHAT_ID="123456789",
    )

    class _EngineProxy:
        def __init__(self, engine: AsyncEngine) -> None:
            self._engine = engine

        def __getattr__(self, name: str) -> object:
            return getattr(self._engine, name)

        async def dispose(self) -> None:
            return None

    def fake_runtime(_settings: Settings | None = None) -> PipelineRuntime:
        return PipelineRuntime(
            settings=settings,
            engine=_EngineProxy(db_engine),  # type: ignore[arg-type]
            session_factory=session_factory,
            http_client=None,  # type: ignore[arg-type]
            llm_client=None,  # type: ignore[arg-type]
            telegram_client=telegram,
            pipeline=None,  # type: ignore[arg-type]
            version="0.1.0",
        )

    async def fake_aclose(self: PipelineRuntime) -> None:
        return None

    monkeypatch.setattr("app.cli.app.build_pipeline_runtime", fake_runtime)
    monkeypatch.setattr(PipelineRuntime, "aclose", fake_aclose)

    help_result = CliRunner().invoke(cli, ["retry-delivery", "--help"])
    assert help_result.exit_code == 0
    assert "--digest-id" in help_result.stdout

    exit_code = await _retry_delivery(digest_id)
    assert exit_code == 0
    assert len(telegram.calls) >= 1
    retry_text = telegram.calls[0][1]
    assert retry_text.startswith("🗞 <b>AI &amp; Automation Daily Digest — 2026-09-15</b>")
    assert "<blockquote>🏷 PRODUCT</blockquote>" in retry_text
    assert "Read on CLI Source" in retry_text
    assert "3 stories · AI-generated digest" in retry_text
    assert 'href="https://example.com/' in retry_text
    assert "\nhttps://example.com/" not in retry_text
