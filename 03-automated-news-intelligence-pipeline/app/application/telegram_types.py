"""Telegram delivery result and error types."""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.enums import ErrorCode


@dataclass(frozen=True, slots=True, kw_only=True)
class TelegramSendResult:
    """Successful Bot API sendMessage response fields."""

    message_id: int
    http_status: int = 200


class TelegramError(Exception):
    """Controlled Telegram delivery failure."""

    def __init__(
        self,
        error_code: ErrorCode,
        summary: str,
        *,
        http_status: int | None = None,
        retry_after_seconds: int | None = None,
    ) -> None:
        self.error_code = error_code
        self.summary = summary
        self.http_status = http_status
        self.retry_after_seconds = retry_after_seconds
        super().__init__(summary)

    @property
    def is_retryable(self) -> bool:
        return self.error_code in {
            ErrorCode.TELEGRAM_TIMEOUT,
            ErrorCode.TELEGRAM_RATE_LIMITED,
        }
