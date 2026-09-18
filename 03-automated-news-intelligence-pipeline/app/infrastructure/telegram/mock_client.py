"""Fixture-backed Telegram client for demo mode and tests."""

from __future__ import annotations

from app.application.telegram_types import TelegramError, TelegramSendResult
from app.domain.enums import ErrorCode
from app.texts.telegram import TELEGRAM_PERMANENT_FAILURE, TELEGRAM_RATE_LIMITED


class MockTelegramClient:
    """Record outbound messages and optionally inject controlled failures."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self._next_message_id = 1000
        self._force_rate_limited_once = False
        self._force_permanent = False
        self._retry_after_seconds = 1

    def force_rate_limited_once(self, *, retry_after_seconds: int = 1) -> None:
        self._force_rate_limited_once = True
        self._retry_after_seconds = retry_after_seconds

    def force_permanent_failure(self) -> None:
        self._force_permanent = True

    async def send_message(self, *, chat_id: str, text: str) -> TelegramSendResult:
        if self._force_permanent:
            raise TelegramError(
                ErrorCode.TELEGRAM_PERMANENT_FAILURE,
                TELEGRAM_PERMANENT_FAILURE,
                http_status=400,
            )

        if self._force_rate_limited_once:
            self._force_rate_limited_once = False
            raise TelegramError(
                ErrorCode.TELEGRAM_RATE_LIMITED,
                TELEGRAM_RATE_LIMITED,
                http_status=429,
                retry_after_seconds=self._retry_after_seconds,
            )

        self.calls.append((chat_id, text))
        self._next_message_id += 1
        return TelegramSendResult(message_id=self._next_message_id, http_status=200)
