"""Deliver a generated digest to Telegram with per-part attempts."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.digest_render import (
    DigestSplitError,
    RenderedDigestLine,
    split_digest_messages,
)
from app.application.ports import TelegramClient
from app.application.telegram_types import TelegramError
from app.config import Settings
from app.domain import (
    DeliveryAttempt,
    DeliveryStatus,
    Digest,
    DigestStatus,
    ErrorCode,
)
from app.infrastructure.db.repositories import (
    DeliveryAttemptRepository,
    DigestRepository,
    NewsItemRepository,
    SourceRepository,
)
from app.infrastructure.db.session import transaction_scope
from app.observability import log_event
from app.texts.telegram import (
    TELEGRAM_CHAT_ID_REQUIRED,
    TELEGRAM_DELIVERY_EXHAUSTED,
    TELEGRAM_DIGEST_NOT_DELIVERABLE,
    TELEGRAM_DIGEST_NOT_FOUND,
    TELEGRAM_SPLIT_FAILED,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class DeliveryOutcome:
    """Result of one delivery or retry-delivery attempt."""

    digest_id: UUID
    status: DigestStatus
    parts_total: int
    parts_sent: int
    skipped: bool = False


class DigestDeliveryService:
    """Send digest parts after the generated digest has been committed."""

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        telegram_client: TelegramClient,
        settings: Settings,
    ) -> None:
        self._session_factory = session_factory
        self._telegram_client = telegram_client
        self._settings = settings

    async def deliver(self, digest_id: UUID) -> DeliveryOutcome:
        """Deliver unsent parts for a GENERATED or FAILED digest."""
        async with transaction_scope(self._session_factory) as session:
            digest = await DigestRepository(session).get(digest_id)
            if digest is None:
                raise LookupError(TELEGRAM_DIGEST_NOT_FOUND)
            if digest.status is DigestStatus.SENT:
                return DeliveryOutcome(
                    digest_id=digest_id,
                    status=DigestStatus.SENT,
                    parts_total=0,
                    parts_sent=0,
                    skipped=True,
                )
            if digest.status not in {DigestStatus.GENERATED, DigestStatus.FAILED}:
                raise ValueError(TELEGRAM_DIGEST_NOT_DELIVERABLE)

            lines = await self._load_lines(session, digest)
            attempts = await DeliveryAttemptRepository(session).list_for_digest(digest_id)

        try:
            parts = split_digest_messages(title=digest.title, lines=lines)
        except DigestSplitError as error:
            await self._fail_digest(
                digest_id,
                error_code=ErrorCode.TELEGRAM_PERMANENT_FAILURE,
                error_summary=TELEGRAM_SPLIT_FAILED,
            )
            raise TelegramError(
                ErrorCode.TELEGRAM_PERMANENT_FAILURE,
                TELEGRAM_SPLIT_FAILED,
            ) from error

        chat_id = self._settings.telegram_chat_id or "demo-chat"
        if (
            self._settings.app_mode == "live"
            and not (self._settings.telegram_chat_id or "").strip()
        ):
            await self._fail_digest(
                digest_id,
                error_code=ErrorCode.TELEGRAM_PERMANENT_FAILURE,
                error_summary=TELEGRAM_CHAT_ID_REQUIRED,
            )
            raise TelegramError(
                ErrorCode.TELEGRAM_PERMANENT_FAILURE,
                TELEGRAM_CHAT_ID_REQUIRED,
            )

        async with transaction_scope(self._session_factory) as session:
            await DigestRepository(session).transition_to(digest_id, DigestStatus.SENDING)

        sent_parts = {
            attempt.part_number for attempt in attempts if attempt.status is DeliveryStatus.SENT
        }
        max_attempts_by_part: dict[int, int] = {}
        for attempt in attempts:
            current = max_attempts_by_part.get(attempt.part_number, 0)
            if attempt.attempt_number > current:
                max_attempts_by_part[attempt.part_number] = attempt.attempt_number

        parts_sent = len(sent_parts)
        for part_number, text in enumerate(parts, start=1):
            if part_number in sent_parts:
                continue

            delivered = await self._deliver_part(
                digest_id=digest_id,
                part_number=part_number,
                text=text,
                chat_id=chat_id,
                prior_attempts=max_attempts_by_part.get(part_number, 0),
            )
            if not delivered:
                async with transaction_scope(self._session_factory) as session:
                    failed = await DigestRepository(session).get(digest_id)
                status = failed.status if failed is not None else DigestStatus.FAILED
                log_event(
                    "telegram.delivery_failed",
                    digest_id=digest_id,
                    parts_sent=parts_sent,
                    parts_total=len(parts),
                )
                return DeliveryOutcome(
                    digest_id=digest_id,
                    status=status,
                    parts_total=len(parts),
                    parts_sent=parts_sent,
                )
            parts_sent += 1

        async with transaction_scope(self._session_factory) as session:
            digest = await DigestRepository(session).transition_to(
                digest_id,
                DigestStatus.SENT,
            )

        log_event(
            "telegram.delivery_succeeded",
            digest_id=digest_id,
            parts_total=len(parts),
            parts_sent=parts_sent,
        )
        return DeliveryOutcome(
            digest_id=digest_id,
            status=digest.status,
            parts_total=len(parts),
            parts_sent=parts_sent,
        )

    async def _deliver_part(
        self,
        *,
        digest_id: UUID,
        part_number: int,
        text: str,
        chat_id: str,
        prior_attempts: int,
    ) -> bool:
        max_retries = self._settings.telegram_max_retries
        attempt_number = prior_attempts

        for trial in range(max_retries):
            attempt_number += 1
            attempt = DeliveryAttempt(
                digest_id=digest_id,
                part_number=part_number,
                attempt_number=attempt_number,
            )
            async with transaction_scope(self._session_factory) as session:
                await DeliveryAttemptRepository(session).add(attempt)

            try:
                result = await self._telegram_client.send_message(
                    chat_id=chat_id,
                    text=text,
                )
            except TelegramError as error:
                async with transaction_scope(self._session_factory) as session:
                    stored = await DeliveryAttemptRepository(session).get(attempt.id)
                    if stored is None:
                        raise
                    stored.mark_failed(
                        error_code=error.error_code,
                        error_summary=error.summary[:500],
                        http_status=error.http_status,
                        retry_after_seconds=error.retry_after_seconds,
                    )
                    await DeliveryAttemptRepository(session).save(stored)

                if not error.is_retryable or trial + 1 >= max_retries:
                    await self._fail_digest(
                        digest_id,
                        error_code=error.error_code,
                        error_summary=error.summary[:500] or TELEGRAM_DELIVERY_EXHAUSTED,
                    )
                    return False

                delay = float(error.retry_after_seconds or 0)
                if delay <= 0:
                    delay = min(2**trial, 8)
                await asyncio.sleep(delay)
                continue

            async with transaction_scope(self._session_factory) as session:
                stored = await DeliveryAttemptRepository(session).get(attempt.id)
                if stored is None:
                    raise LookupError(TELEGRAM_DIGEST_NOT_FOUND)
                stored.mark_sent(
                    telegram_message_id=result.message_id,
                    http_status=result.http_status,
                )
                await DeliveryAttemptRepository(session).save(stored)
            return True

        await self._fail_digest(
            digest_id,
            error_code=ErrorCode.TELEGRAM_TIMEOUT,
            error_summary=TELEGRAM_DELIVERY_EXHAUSTED,
        )
        return False

    async def _fail_digest(
        self,
        digest_id: UUID,
        *,
        error_code: ErrorCode,
        error_summary: str,
    ) -> None:
        async with transaction_scope(self._session_factory) as session:
            repo = DigestRepository(session)
            digest = await repo.get(digest_id)
            if digest is None:
                return
            if digest.status is DigestStatus.SENDING:
                await repo.transition_to(
                    digest_id,
                    DigestStatus.FAILED,
                    error_code=error_code,
                    error_summary=error_summary[:500],
                )
            elif digest.status is DigestStatus.GENERATED:
                await repo.transition_to(digest_id, DigestStatus.SENDING)
                await repo.transition_to(
                    digest_id,
                    DigestStatus.FAILED,
                    error_code=error_code,
                    error_summary=error_summary[:500],
                )

    @staticmethod
    async def _load_lines(
        session: AsyncSession,
        digest: Digest,
    ) -> tuple[RenderedDigestLine, ...]:
        news_repo = NewsItemRepository(session)
        source_repo = SourceRepository(session)
        lines: list[RenderedDigestLine] = []
        for item in digest.items:
            news = await news_repo.get(item.news_item_id)
            if news is None:
                raise LookupError(TELEGRAM_SPLIT_FAILED)
            source = await source_repo.get(news.source_id)
            if source is None:
                raise LookupError(TELEGRAM_SPLIT_FAILED)
            lines.append(
                RenderedDigestLine(item=item, news_item=news, source=source),
            )
        return tuple(lines)
