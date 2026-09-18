"""Telegram delivery adapters."""

from app.infrastructure.telegram.factory import build_telegram_client

__all__ = ["build_telegram_client"]
