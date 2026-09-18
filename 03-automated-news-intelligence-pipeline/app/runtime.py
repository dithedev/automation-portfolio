"""Shared runtime wiring for CLI, scheduler, and API entrypoints."""

from __future__ import annotations

from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.application.pipeline import DigestPipelineService
from app.application.ports import FeedHttpClient, LlmClient, TelegramClient
from app.config import Settings, get_settings
from app.infrastructure.db.engine import build_engine
from app.infrastructure.db.session import build_session_factory
from app.infrastructure.feeds.factory import build_feed_http_client
from app.infrastructure.llm import build_llm_client
from app.infrastructure.telegram import build_telegram_client


def app_version() -> str:
    """Return the installed package version, falling back for editable installs."""
    try:
        return version("news-intelligence-pipeline")
    except PackageNotFoundError:
        return "0.1.0"


@dataclass(slots=True, kw_only=True)
class PipelineRuntime:
    """Owned resources for one process that runs the digest pipeline."""

    settings: Settings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    http_client: FeedHttpClient
    llm_client: LlmClient
    telegram_client: TelegramClient
    pipeline: DigestPipelineService
    version: str

    async def aclose(self) -> None:
        close_http = getattr(self.http_client, "aclose", None)
        if close_http is not None:
            await close_http()
        close = getattr(self.telegram_client, "aclose", None)
        if close is not None:
            await close()
        await self.engine.dispose()


def build_pipeline_runtime(settings: Settings | None = None) -> PipelineRuntime:
    """Construct engine, clients, and DigestPipelineService for entrypoints."""
    resolved = settings if settings is not None else get_settings()
    engine = build_engine(resolved)
    session_factory = build_session_factory(engine)
    http_client = build_feed_http_client(resolved)
    llm_client = build_llm_client(resolved)
    telegram_client = build_telegram_client(resolved)
    pipeline = DigestPipelineService(
        engine=engine,
        session_factory=session_factory,
        http_client=http_client,
        llm_client=llm_client,
        telegram_client=telegram_client,
        settings=resolved,
    )
    return PipelineRuntime(
        settings=resolved,
        engine=engine,
        session_factory=session_factory,
        http_client=http_client,
        llm_client=llm_client,
        telegram_client=telegram_client,
        pipeline=pipeline,
        version=app_version(),
    )


# Re-export for type checkers / callers that only need the protocol name.
__all__ = [
    "FeedHttpClient",
    "PipelineRuntime",
    "app_version",
    "build_pipeline_runtime",
]
