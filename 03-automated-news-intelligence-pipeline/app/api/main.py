"""FastAPI operational API (read-only)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.api.auth import admin_api_key_is_valid
from app.config import Settings, get_settings
from app.domain import DigestStatus
from app.infrastructure.db.engine import build_engine
from app.infrastructure.db.repositories import DigestRepository, PipelineRunRepository
from app.infrastructure.db.session import build_session_factory, transaction_scope
from app.observability import configure_logging
from app.runtime import app_version
from app.texts.api import (
    API_DEMO_DISABLED,
    API_DIGEST_NOT_FOUND,
    API_NOT_READY,
    API_UNAUTHORIZED,
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        return response


class LiveResponse(BaseModel):
    status: str


class ReadyResponse(BaseModel):
    status: str


class StatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    app_version: str
    timestamp: str
    last_run_status: str | None
    last_run_finished_at: str | None
    last_run_duration_ms: int | None
    last_sent_digest_at: str | None
    next_scheduled_run: str | None
    feeds_total_last_run: int | None
    items_inserted_last_run: int | None
    selected_count_last_run: int | None


class LatestDigestResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    rendered_text: str
    sent_at: str


def _next_scheduled_run(settings: Settings, *, now: datetime) -> str | None:
    if not settings.scheduler_enabled:
        return None
    trigger = CronTrigger(
        hour=settings.digest_schedule_hour,
        minute=settings.digest_schedule_minute,
        timezone=ZoneInfo(settings.app_timezone),
    )
    nxt = trigger.get_next_fire_time(None, now)
    if nxt is None:
        return None
    return str(nxt.astimezone(UTC).isoformat().replace("+00:00", "Z"))


def create_app(
    *,
    settings: Settings | None = None,
    engine: AsyncEngine | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> FastAPI:
    """Build the FastAPI application (injectable for tests)."""
    resolved = settings if settings is not None else get_settings()
    configure_logging(resolved)
    docs_url = None if resolved.app_env == "production" else "/docs"
    openapi_url = None if resolved.app_env == "production" else "/openapi.json"

    state: dict[str, Any] = {
        "settings": resolved,
        "engine": engine,
        "session_factory": session_factory,
        "owns_engine": engine is None and session_factory is None,
    }

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        if state["engine"] is None:
            built = build_engine(resolved)
            state["engine"] = built
            state["session_factory"] = build_session_factory(built)
            state["owns_engine"] = True
        yield
        if state["owns_engine"] and state["engine"] is not None:
            await state["engine"].dispose()

    application = FastAPI(
        title="News Intelligence Pipeline",
        version=app_version(),
        lifespan=lifespan,
        docs_url=docs_url,
        redoc_url=None,
        openapi_url=openapi_url,
    )
    application.add_middleware(SecurityHeadersMiddleware)
    application.state.settings = resolved

    @application.get("/health/live", response_model=LiveResponse)
    async def health_live() -> LiveResponse:
        return LiveResponse(status="ok")

    @application.get("/health/ready", response_model=ReadyResponse)
    async def health_ready() -> ReadyResponse | JSONResponse:
        factory: async_sessionmaker[AsyncSession] | None = state["session_factory"]
        if factory is None:
            return JSONResponse(
                status_code=503, content={"status": "unavailable", "detail": API_NOT_READY}
            )
        try:
            async with transaction_scope(factory) as session:
                value = await session.scalar(select(1))
                if value != 1:
                    raise RuntimeError(API_NOT_READY)
        except Exception:
            return JSONResponse(
                status_code=503,
                content={"status": "unavailable", "detail": API_NOT_READY},
            )
        return ReadyResponse(status="ok")

    @application.get("/status", response_model=StatusResponse)
    async def status(
        x_admin_api_key: str | None = Header(default=None, alias="X-Admin-Api-Key"),
    ) -> StatusResponse | JSONResponse:
        if not admin_api_key_is_valid(resolved, x_admin_api_key):
            return JSONResponse(status_code=401, content={"detail": API_UNAUTHORIZED})

        factory: async_sessionmaker[AsyncSession] = state["session_factory"]
        now = datetime.now(UTC)
        async with transaction_scope(factory) as session:
            last_run = await PipelineRunRepository(session).get_latest()
            last_sent = await DigestRepository(session).get_latest_sent()

        return StatusResponse(
            app_version=app_version(),
            timestamp=now.isoformat().replace("+00:00", "Z"),
            last_run_status=last_run.status.value if last_run else None,
            last_run_finished_at=(
                last_run.finished_at.isoformat().replace("+00:00", "Z")
                if last_run and last_run.finished_at
                else None
            ),
            last_run_duration_ms=last_run.duration_ms if last_run else None,
            last_sent_digest_at=(
                last_sent.sent_at.isoformat().replace("+00:00", "Z")
                if last_sent and last_sent.sent_at
                else None
            ),
            next_scheduled_run=_next_scheduled_run(resolved, now=now),
            feeds_total_last_run=last_run.feeds_total if last_run else None,
            items_inserted_last_run=last_run.items_inserted if last_run else None,
            selected_count_last_run=last_run.selected_count if last_run else None,
        )

    @application.get("/digests/latest", response_model=LatestDigestResponse)
    async def digests_latest() -> LatestDigestResponse | JSONResponse:
        if not resolved.expose_demo_endpoints:
            return JSONResponse(status_code=404, content={"detail": API_DEMO_DISABLED})
        factory: async_sessionmaker[AsyncSession] = state["session_factory"]
        async with transaction_scope(factory) as session:
            digest = await DigestRepository(session).get_latest_sent()
        if digest is None or digest.status is not DigestStatus.SENT:
            return JSONResponse(status_code=404, content={"detail": API_DIGEST_NOT_FOUND})
        assert digest.sent_at is not None
        return LatestDigestResponse(
            title=digest.title,
            rendered_text=digest.rendered_text,
            sent_at=digest.sent_at.isoformat().replace("+00:00", "Z"),
        )

    return application


# ASGI entry for `uvicorn app.api.main:create_app --factory`
