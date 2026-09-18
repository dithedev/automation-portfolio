"""Typer CLI entrypoints for pipeline operations."""

from __future__ import annotations

import asyncio
from uuid import UUID

import typer

from app.application.cleanup import cleanup_operational_records
from app.application.digest_delivery import DigestDeliveryService
from app.config import Settings, get_settings
from app.domain import DigestStatus, PipelineRunStatus, TriggerType
from app.infrastructure.db.repositories import SourceRepository
from app.infrastructure.db.session import transaction_scope
from app.infrastructure.feeds.seed import run_seed
from app.observability import configure_logging
from app.runtime import build_pipeline_runtime
from app.texts.cli import (
    CLI_CLEANUP_CONFIRM_REQUIRED,
    CLI_CLEANUP_SUMMARY,
    CLI_COMMAND_FAILED,
    CLI_CONFIG_OK,
    CLI_DRY_RUN_PREFIX,
    CLI_MANUAL_RUN_DISABLED,
    CLI_NO_CONTENT,
    CLI_RUN_SUMMARY,
    CLI_SKIPPED_LOCKED,
)

cli = typer.Typer(add_completion=False, no_args_is_help=True)

_SUCCESS_STATUSES = {
    PipelineRunStatus.SUCCESS,
    PipelineRunStatus.PARTIAL_SUCCESS,
    PipelineRunStatus.NO_CONTENT,
    PipelineRunStatus.SKIPPED_LOCKED,
}


@cli.callback()
def root() -> None:
    """Automated News Intelligence Pipeline CLI."""


@cli.command("run-digest")
def run_digest(
    dry_run: bool = typer.Option(False, "--dry-run", help="Skip Telegram delivery."),
) -> None:
    """Run the full digest pipeline once."""
    raise SystemExit(asyncio.run(_run_digest(dry_run=dry_run)))


@cli.command("retry-delivery")
def retry_delivery(
    digest_id: UUID = typer.Option(..., "--digest-id", help="Digest UUID to redeliver."),
) -> None:
    """Retry Telegram delivery for a generated or failed digest without LLM calls."""
    raise SystemExit(asyncio.run(_retry_delivery(digest_id)))


@cli.command("seed-sources")
def seed_sources() -> None:
    """Synchronize config/feeds.yaml into the database."""
    raise SystemExit(asyncio.run(run_seed()))


@cli.command("list-sources")
def list_sources() -> None:
    """List feed sources stored in PostgreSQL."""
    raise SystemExit(asyncio.run(_list_sources()))


@cli.command("cleanup")
def cleanup(
    older_than_days: int = typer.Option(
        ...,
        "--older-than-days",
        min=1,
        help="Delete operational rows finished before this many days ago.",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Report counts without deleting."),
    confirm: bool = typer.Option(
        False,
        "--confirm",
        help="Required for destructive cleanup.",
    ),
) -> None:
    """Delete aged feed_fetches and delivery_attempts (not news items or digests)."""
    raise SystemExit(
        asyncio.run(
            _cleanup(
                older_than_days=older_than_days,
                dry_run=dry_run,
                confirm=confirm,
            )
        )
    )


@cli.command("check-config")
def check_config() -> None:
    """Validate settings and print a redacted configuration summary."""
    raise SystemExit(_check_config())


def exit_code_for_run_status(status: PipelineRunStatus) -> int:
    """Map pipeline terminal status to a process exit code."""
    return 0 if status in _SUCCESS_STATUSES else 1


async def _run_digest(*, dry_run: bool) -> int:
    try:
        runtime = build_pipeline_runtime()
    except Exception:
        typer.echo(CLI_COMMAND_FAILED, err=True)
        return 1

    if not runtime.settings.manual_run_enabled:
        typer.echo(CLI_MANUAL_RUN_DISABLED, err=True)
        await runtime.aclose()
        return 1

    trigger = TriggerType.DRY_RUN if dry_run else TriggerType.MANUAL
    try:
        outcome = await runtime.pipeline.run(
            trigger_type=trigger,
            app_version=runtime.version,
        )
    except Exception:
        typer.echo(CLI_COMMAND_FAILED, err=True)
        await runtime.aclose()
        return 1

    prefix = f"{CLI_DRY_RUN_PREFIX} " if dry_run else ""
    if outcome.run.status is PipelineRunStatus.SKIPPED_LOCKED:
        typer.echo(f"{prefix}{CLI_SKIPPED_LOCKED}")
    elif outcome.run.status is PipelineRunStatus.NO_CONTENT:
        typer.echo(f"{prefix}{CLI_NO_CONTENT}")
    else:
        summary = CLI_RUN_SUMMARY.format(
            status=outcome.run.status.value,
            run_id=outcome.run.id,
            digest_id=outcome.digest_id or "-",
        )
        typer.echo(f"{prefix}{summary}")

    await runtime.aclose()
    return exit_code_for_run_status(outcome.run.status)


async def _retry_delivery(digest_id: UUID) -> int:
    try:
        runtime = build_pipeline_runtime()
    except Exception:
        typer.echo(CLI_COMMAND_FAILED, err=True)
        return 1

    service = DigestDeliveryService(
        session_factory=runtime.session_factory,
        telegram_client=runtime.telegram_client,
        settings=runtime.settings,
    )
    try:
        outcome = await service.deliver(digest_id)
    except Exception as error:
        typer.echo(f"Delivery failed: {error}", err=True)
        await runtime.aclose()
        return 1

    typer.echo(
        f"digest_id={outcome.digest_id} status={outcome.status.value} "
        f"parts_sent={outcome.parts_sent}/{outcome.parts_total}"
    )
    await runtime.aclose()
    return 0 if outcome.status is DigestStatus.SENT else 1


async def _list_sources() -> int:
    try:
        runtime = build_pipeline_runtime()
    except Exception:
        typer.echo(CLI_COMMAND_FAILED, err=True)
        return 1

    try:
        async with transaction_scope(runtime.session_factory) as session:
            sources = await SourceRepository(session).list_all()
    except Exception:
        typer.echo(CLI_COMMAND_FAILED, err=True)
        await runtime.aclose()
        return 1

    if not sources:
        typer.echo("No sources found.")
    else:
        for source in sources:
            typer.echo(
                f"{source.key}\tenabled={source.enabled}\thost={source.allowed_host}\t{source.name}"
            )

    await runtime.aclose()
    return 0


async def _cleanup(*, older_than_days: int, dry_run: bool, confirm: bool) -> int:
    if not dry_run and not confirm:
        typer.echo(CLI_CLEANUP_CONFIRM_REQUIRED, err=True)
        return 1

    try:
        runtime = build_pipeline_runtime()
    except Exception:
        typer.echo(CLI_COMMAND_FAILED, err=True)
        return 1

    try:
        result = await cleanup_operational_records(
            runtime.session_factory,
            older_than_days=older_than_days,
            dry_run=dry_run,
        )
    except Exception:
        typer.echo(CLI_COMMAND_FAILED, err=True)
        await runtime.aclose()
        return 1

    typer.echo(
        CLI_CLEANUP_SUMMARY.format(
            feed_fetches=result.feed_fetches,
            delivery_attempts=result.delivery_attempts,
            dry_run=result.dry_run,
        )
    )
    await runtime.aclose()
    return 0


def _check_config() -> int:
    try:
        settings = get_settings()
    except Exception:
        typer.echo(CLI_COMMAND_FAILED, err=True)
        return 1

    typer.echo(CLI_CONFIG_OK)
    for line in _redacted_settings_lines(settings):
        typer.echo(line)
    return 0


def _redacted_settings_lines(settings: Settings) -> list[str]:
    """Emit non-secret settings for operator verification."""
    return [
        f"app_env={settings.app_env}",
        f"app_mode={settings.app_mode}",
        f"log_level={settings.app_log_level}",
        f"scheduler_timezone={settings.app_timezone}",
        f"scheduler_enabled={settings.scheduler_enabled}",
        f"digest_schedule={settings.digest_schedule_hour:02d}:{settings.digest_schedule_minute:02d}",
        f"telegram_enabled={settings.telegram_enabled}",
        f"manual_run_enabled={settings.manual_run_enabled}",
        f"expose_demo_endpoints={settings.expose_demo_endpoints}",
        f"openai_model={settings.openai_model}",
        f"min_digest_items={settings.min_digest_items}",
        f"max_digest_items={settings.max_digest_items}",
        "database_url=***",
        "openai_api_key=***" if settings.openai_api_key is not None else "openai_api_key=",
        "telegram_bot_token=***"
        if settings.telegram_bot_token is not None
        else "telegram_bot_token=",
        "telegram_chat_id=***" if settings.telegram_chat_id else "telegram_chat_id=",
        "admin_api_key=***" if settings.admin_api_key is not None else "admin_api_key=",
    ]


def main() -> None:
    configure_logging(get_settings())
    cli()
