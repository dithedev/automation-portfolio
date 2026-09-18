"""aiogram-backed Telegram Bot API client."""

from __future__ import annotations

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramUnauthorizedError,
)
from aiogram.types import LinkPreviewOptions

from app.application.telegram_types import TelegramError, TelegramSendResult
from app.config import Settings
from app.domain.enums import ErrorCode
from app.texts.telegram import (
    TELEGRAM_PERMANENT_FAILURE,
    TELEGRAM_RATE_LIMITED,
    TELEGRAM_REQUEST_FAILED,
    TELEGRAM_TIMEOUT,
)


class AiogramTelegramClient:
    """Send HTML digest messages through aiogram without holding DB transactions."""

    def __init__(
        self,
        settings: Settings,
        *,
        bot: Bot | None = None,
    ) -> None:
        self._settings = settings
        if bot is not None:
            self._bot = bot
            self._owns_bot = False
        else:
            token = settings.telegram_bot_token
            if token is None:
                raise TelegramError(
                    ErrorCode.TELEGRAM_PERMANENT_FAILURE,
                    TELEGRAM_REQUEST_FAILED,
                )
            self._bot = Bot(
                token=token.get_secret_value(),
                default=DefaultBotProperties(),
            )
            self._owns_bot = True

    async def aclose(self) -> None:
        if self._owns_bot:
            await self._bot.session.close()

    async def send_message(self, *, chat_id: str, text: str) -> TelegramSendResult:
        try:
            message = await self._bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=ParseMode.HTML,
                link_preview_options=LinkPreviewOptions(is_disabled=True),
                request_timeout=int(self._settings.telegram_timeout_seconds),
            )
        except TelegramRetryAfter as error:
            raise TelegramError(
                ErrorCode.TELEGRAM_RATE_LIMITED,
                TELEGRAM_RATE_LIMITED,
                http_status=429,
                retry_after_seconds=int(error.retry_after),
            ) from error
        except TelegramNetworkError as error:
            raise TelegramError(
                ErrorCode.TELEGRAM_TIMEOUT,
                TELEGRAM_TIMEOUT,
            ) from error
        except (TelegramBadRequest, TelegramForbiddenError, TelegramUnauthorizedError) as error:
            raise TelegramError(
                ErrorCode.TELEGRAM_PERMANENT_FAILURE,
                TELEGRAM_PERMANENT_FAILURE,
                http_status=400,
            ) from error
        except Exception as error:
            raise TelegramError(
                ErrorCode.TELEGRAM_PERMANENT_FAILURE,
                TELEGRAM_REQUEST_FAILED,
            ) from error

        return TelegramSendResult(message_id=int(message.message_id), http_status=200)
