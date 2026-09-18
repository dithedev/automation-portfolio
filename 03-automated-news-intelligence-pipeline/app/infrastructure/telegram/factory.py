"""Telegram client factory for live and demo modes."""

from app.application.ports import TelegramClient
from app.config import Settings
from app.infrastructure.telegram.aiogram_client import AiogramTelegramClient
from app.infrastructure.telegram.mock_client import MockTelegramClient


def build_telegram_client(settings: Settings) -> TelegramClient:
    """Return the aiogram client in live mode and the mock client in demo mode."""
    if settings.app_mode == "demo":
        return MockTelegramClient()
    return AiogramTelegramClient(settings)
