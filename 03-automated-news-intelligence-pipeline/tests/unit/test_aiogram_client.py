"""Unit tests for aiogram Telegram client HTML send options."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.enums import ParseMode
from aiogram.types import LinkPreviewOptions
from pydantic import SecretStr

from app.config import Settings
from app.infrastructure.telegram.aiogram_client import AiogramTelegramClient


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        APP_MODE="demo",
        DATABASE_URL="postgresql+asyncpg://news:news@localhost:5432/news",
        TELEGRAM_ENABLED=True,
        TELEGRAM_BOT_TOKEN=SecretStr("123456:ABC-DEF"),
        TELEGRAM_CHAT_ID="1",
        TELEGRAM_TIMEOUT_SECONDS=5,
    )


@pytest.mark.asyncio
async def test_send_message_uses_html_and_disables_link_preview() -> None:
    bot = SimpleNamespace(send_message=AsyncMock(return_value=SimpleNamespace(message_id=42)))
    client = AiogramTelegramClient(_settings(), bot=bot)  # type: ignore[arg-type]

    result = await client.send_message(chat_id="99", text="<b>hello</b>")

    assert result.message_id == 42
    assert result.http_status == 200
    kwargs = bot.send_message.await_args.kwargs
    assert kwargs["chat_id"] == "99"
    assert kwargs["text"] == "<b>hello</b>"
    assert kwargs["parse_mode"] == ParseMode.HTML
    preview = kwargs["link_preview_options"]
    assert isinstance(preview, LinkPreviewOptions)
    assert preview.is_disabled is True
