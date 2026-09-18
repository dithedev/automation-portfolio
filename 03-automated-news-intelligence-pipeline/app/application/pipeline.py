"""Orchestrate lock, ingest, selection, digest generation, and delivery."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.application.digest_delivery import DeliveryOutcome, DigestDeliveryService
from app.application.digest_generation import (
    build_candidate_contexts,
    generate_validated_digest,
)
from app.application.feed_ingestion import FeedIngestionService, IngestRunResult
from app.application.llm_types import LlmError
from app.application.ports import FeedHttpClient, LlmClient, TelegramClient
from app.application.source_limits import resolve_source_limits
from app.config import Settings
from app.domain import (
    ErrorCode,
    FeedFetchStatus,
    NewsItem,
    NewsItemStatus,
    PipelineRun,
    PipelineRunStatus,
    Source,
    TriggerType,
)
from app.domain.selection import select_candidates
from app.domain.validators import utc_now
from app.infrastructure.db.advisory_lock import PipelineAdvisoryLock
from app.infrastructure.db.repositories import (
    DigestRepository,
    NewsItemRepository,
    PipelineRunRepository,
    SourceRepository,
)
from app.infrastructure.db.session import transaction_scope
from app.infrastructure.feeds.config import load_feed_configuration
from app.infrastructure.topic_profile import load_topic_profile
from app.observability import bind_run, clear_run_context, log_event
from app.texts.pipeline import FEED_FAILURE_WARNING, PIPELINE_UNEXPECTED_FAILURE


@dataclass(frozen=True, slots=True, kw_only=True)
class PipelineRunOutcome:
    """Terminal result of one orchestrated pipeline attempt."""

    run: PipelineRun
    candidate_ids: tuple[UUID, ...]
    ingest: IngestRunResult | None
    lock_acquired: bool
    digest_id: UUID | None = None
    delivery: DeliveryOutcome | None = None


class DigestPipelineService:
    """Run collection, selection, AI generation, and Telegram delivery under a lock."""

    def __init__(
        self,
        *,
        engine: AsyncEngine,
        session_factory: async_sessionmaker[AsyncSession],
        http_client: FeedHttpClient,
        llm_client: LlmClient,
        telegram_client: TelegramClient,
        settings: Settings,
    ) -> None:
        self._engine = engine
        self._session_factory = session_factory
        self._http_client = http_client
        self._llm_client = llm_client
        self._telegram_client = telegram_client
        self._settings = settings
        self._ingestion = FeedIngestionService(
            session_factory=session_factory,
            http_client=http_client,
            settings=settings,
        )
        self._delivery = DigestDeliveryService(
            session_factory=session_factory,
            telegram_client=telegram_client,
            settings=settings,
        )

    async def run(
        self,
        *,
        trigger_type: TriggerType,
        app_version: str,
    ) -> PipelineRunOutcome:
        lock = PipelineAdvisoryLock(self._engine)
        acquired = await lock.acquire()

        try:
            if not acquired:
                skipped = PipelineRun.create_skipped_locked(
                    trigger_type=trigger_type,
                    app_version=app_version,
                )
                async with transaction_scope(self._session_factory) as session:
                    await PipelineRunRepository(session).add(skipped)
                bind_run(run_id=skipped.id)
                log_event("pipeline.lock_not_acquired", trigger_type=trigger_type.value)
                clear_run_context()
                return PipelineRunOutcome(
                    run=skipped,
                    candidate_ids=(),
                    ingest=None,
                    lock_acquired=False,
                )

            return await self._run_locked(
                trigger_type=trigger_type,
                app_version=app_version,
            )
        finally:
            await lock.release()

    async def _run_locked(
        self,
        *,
        trigger_type: TriggerType,
        app_version: str,
    ) -> PipelineRunOutcome:
        run = PipelineRun(
            trigger_type=trigger_type,
            app_version=app_version,
        )
        bind_run(run_id=run.id)
        log_event("pipeline.started", trigger_type=trigger_type.value)

        async with transaction_scope(self._session_factory) as session:
            await PipelineRunRepository(session).add(run)

        try:
            feed_configuration = load_feed_configuration(self._settings.feeds_config_path)
            profile = load_topic_profile(self._settings.topic_profile_path)

            async with transaction_scope(self._session_factory) as session:
                sources = await SourceRepository(session).list_enabled()

            if not sources:
                run.complete(PipelineRunStatus.NO_CONTENT)
                async with transaction_scope(self._session_factory) as session:
                    await PipelineRunRepository(session).save(run)
                log_event("pipeline.completed", status=run.status.value)
                clear_run_context()
                return PipelineRunOutcome(
                    run=run,
                    candidate_ids=(),
                    ingest=None,
                    lock_acquired=True,
                )

            limits = resolve_source_limits(
                settings=self._settings,
                feed_configuration=feed_configuration,
                sources=sources,
            )
            ingest = await self._ingestion.ingest_sources(
                run_id=run.id,
                sources=sources,
                limits_by_source_id=limits,
            )
            self._apply_ingest_counters(run, ingest)

            async with transaction_scope(self._session_factory) as session:
                sources_fresh = await SourceRepository(session).list_enabled()
                sources_by_id = {source.id: source for source in sources_fresh}
                eligible = await NewsItemRepository(session).list_eligible_for_selection(
                    now=utc_now(),
                    max_age_hours=self._settings.max_item_age_hours,
                    limit=max(self._settings.max_new_items_per_run * 2, 200),
                )

            selection = select_candidates(
                eligible,
                sources_by_id=sources_by_id,
                profile=profile,
                now=utc_now(),
                max_age_hours=self._settings.max_item_age_hours,
                max_candidates=self._settings.max_llm_candidates,
            )

            candidate_ids: list[UUID] = []
            scores_by_id: dict[UUID, float] = {}
            async with transaction_scope(self._session_factory) as session:
                news_repo = NewsItemRepository(session)
                for ignored in selection.ignored:
                    current = await news_repo.get(ignored.news_item_id)
                    if current is None:
                        continue
                    if current.status is NewsItemStatus.COLLECTED:
                        await news_repo.transition_to(
                            ignored.news_item_id,
                            NewsItemStatus.IGNORED,
                            ignore_reason=ignored.reason,
                        )

                for scored in selection.candidates:
                    item = scored.item
                    if item.status is NewsItemStatus.COLLECTED:
                        item = await news_repo.transition_to(
                            item.id,
                            NewsItemStatus.CANDIDATE,
                        )
                    candidate_ids.append(item.id)
                    scores_by_id[item.id] = scored.score

            if candidate_ids:
                run.record_candidates(len(candidate_ids))

            _ = self._feed_failure_warning(sources_fresh)

            if len(candidate_ids) < self._settings.min_digest_items:
                run.complete(PipelineRunStatus.NO_CONTENT)
                async with transaction_scope(self._session_factory) as session:
                    await PipelineRunRepository(session).save(run)
                log_event(
                    "pipeline.completed",
                    status=run.status.value,
                    candidates=len(candidate_ids),
                )
                clear_run_context()
                return PipelineRunOutcome(
                    run=run,
                    candidate_ids=tuple(candidate_ids),
                    ingest=ingest,
                    lock_acquired=True,
                )

            async with transaction_scope(self._session_factory) as session:
                news_repo = NewsItemRepository(session)
                news_items: list[NewsItem] = []
                for news_item_id in candidate_ids:
                    loaded = await news_repo.get(news_item_id)
                    if loaded is not None:
                        news_items.append(loaded)

            contexts = build_candidate_contexts(
                news_items=tuple(news_items),
                sources_by_id=sources_by_id,
                scores_by_id=scores_by_id,
            )

            try:
                digest = await generate_validated_digest(
                    llm_client=self._llm_client,
                    settings=self._settings,
                    run_id=run.id,
                    digest_date=utc_now().date(),
                    contexts=contexts,
                )
            except LlmError as error:
                run.complete(
                    PipelineRunStatus.FAILED,
                    error_code=error.error_code,
                    error_summary=error.summary[:500],
                )
                async with transaction_scope(self._session_factory) as session:
                    await PipelineRunRepository(session).save(run)
                log_event(
                    "pipeline.failed",
                    status=run.status.value,
                    error_code=error.error_code.value,
                )
                clear_run_context()
                return PipelineRunOutcome(
                    run=run,
                    candidate_ids=tuple(candidate_ids),
                    ingest=ingest,
                    lock_acquired=True,
                )

            async with transaction_scope(self._session_factory) as session:
                await DigestRepository(session).create_generated(digest)
                run.record_selected(len(digest.items))
                if ingest.feeds_failed > 0:
                    run.complete(PipelineRunStatus.PARTIAL_SUCCESS)
                else:
                    run.complete(PipelineRunStatus.SUCCESS)
                await PipelineRunRepository(session).save(run)

            log_event(
                "digest.created",
                digest_id=digest.id,
                selected_count=len(digest.items),
            )

            delivery: DeliveryOutcome | None = None
            should_deliver = (
                self._settings.telegram_enabled and trigger_type is not TriggerType.DRY_RUN
            )
            if should_deliver:
                delivery = await self._delivery.deliver(digest.id)

            log_event(
                "pipeline.completed",
                status=run.status.value,
                digest_id=digest.id,
            )
            clear_run_context()
            return PipelineRunOutcome(
                run=run,
                candidate_ids=tuple(candidate_ids),
                ingest=ingest,
                lock_acquired=True,
                digest_id=digest.id,
                delivery=delivery,
            )
        except Exception:
            if run.status is PipelineRunStatus.RUNNING:
                run.complete(
                    PipelineRunStatus.FAILED,
                    error_code=ErrorCode.UNEXPECTED_PIPELINE_FAILURE,
                    error_summary=PIPELINE_UNEXPECTED_FAILURE,
                )
                async with transaction_scope(self._session_factory) as session:
                    await PipelineRunRepository(session).save(run)
            log_event(
                "pipeline.failed",
                status=run.status.value,
                error_code=(
                    run.error_code.value
                    if run.error_code is not None
                    else ErrorCode.UNEXPECTED_PIPELINE_FAILURE.value
                ),
            )
            clear_run_context()
            return PipelineRunOutcome(
                run=run,
                candidate_ids=(),
                ingest=None,
                lock_acquired=True,
            )

    @staticmethod
    def _apply_ingest_counters(run: PipelineRun, ingest: IngestRunResult) -> None:
        for source_result in ingest.sources:
            run.record_feed_attempt()
            if source_result.status is not FeedFetchStatus.FAILED:
                run.record_feed_success()

            if source_result.items_inserted or source_result.items_duplicate:
                run.record_items_fetched(
                    source_result.items_inserted + source_result.items_duplicate,
                )

            for _ in range(source_result.items_inserted):
                run.record_item_inserted()

            for _ in range(source_result.items_duplicate):
                run.record_item_duplicate()

    def _feed_failure_warning(self, sources: tuple[Source, ...]) -> str | None:
        threshold = self._settings.feed_failure_warning_threshold
        noisy = [source.key for source in sources if source.consecutive_failures >= threshold]
        if not noisy:
            return None

        return FEED_FAILURE_WARNING.format(keys=", ".join(sorted(noisy)))
