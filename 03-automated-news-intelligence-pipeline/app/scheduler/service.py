"""Standalone APScheduler bootstrap (no FastAPI imports)."""

from __future__ import annotations

import asyncio
import logging
import signal
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import get_settings
from app.domain import TriggerType
from app.observability import configure_logging
from app.runtime import PipelineRuntime, build_pipeline_runtime

logger = logging.getLogger(__name__)

JOB_ID = "daily-news-digest"


async def _run_scheduled(runtime: PipelineRuntime) -> None:
    try:
        outcome = await runtime.pipeline.run(
            trigger_type=TriggerType.SCHEDULED,
            app_version=runtime.version,
        )
        logger.info(
            "scheduled_run_finished status=%s run_id=%s digest_id=%s",
            outcome.run.status.value,
            outcome.run.id,
            outcome.digest_id,
        )
    except Exception:
        logger.exception("scheduled_run_failed")


def build_scheduler(runtime: PipelineRuntime) -> AsyncIOScheduler:
    """Create a scheduler and optionally register the daily digest job."""
    scheduler = AsyncIOScheduler(timezone=ZoneInfo("UTC"))
    if not runtime.settings.scheduler_enabled:
        return scheduler

    trigger = CronTrigger(
        hour=runtime.settings.digest_schedule_hour,
        minute=runtime.settings.digest_schedule_minute,
        timezone=ZoneInfo(runtime.settings.app_timezone),
    )
    scheduler.add_job(
        _run_scheduled,
        trigger=trigger,
        id=JOB_ID,
        kwargs={"runtime": runtime},
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=runtime.settings.scheduler_misfire_grace_seconds,
    )
    return scheduler


async def run_scheduler() -> None:
    """Start AsyncIOScheduler and block until SIGINT/SIGTERM."""
    logging.basicConfig(level=logging.INFO)
    runtime = build_pipeline_runtime()
    scheduler = build_scheduler(runtime)
    stop_event = asyncio.Event()

    def _request_stop(*_args: object) -> None:
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _request_stop)
        except NotImplementedError:
            signal.signal(sig, lambda *_: _request_stop())

    if runtime.settings.scheduler_enabled:
        logger.info(
            "scheduler_job_registered job_id=%s hour=%s minute=%s timezone=%s",
            JOB_ID,
            runtime.settings.digest_schedule_hour,
            runtime.settings.digest_schedule_minute,
            runtime.settings.app_timezone,
        )
    else:
        logger.info("scheduler_disabled_waiting")

    scheduler.start()
    try:
        await stop_event.wait()
    finally:
        scheduler.shutdown(wait=False)
        await runtime.aclose()


def main() -> None:
    configure_logging(get_settings())
    asyncio.run(run_scheduler())
