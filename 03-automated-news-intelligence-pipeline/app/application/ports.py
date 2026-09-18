"""Application-facing protocols for external dependencies."""

from typing import Protocol

from app.application.feed_http_types import FeedHttpResponse
from app.application.llm_types import LlmDigestResult
from app.application.telegram_types import TelegramSendResult


class FeedHttpClient(Protocol):
    """Fetch one trusted feed URL without following redirects."""

    async def fetch(
        self,
        *,
        feed_url: str,
        allowed_host: str,
        etag: str | None,
        last_modified: str | None,
        read_timeout_seconds: float,
        max_bytes: int,
    ) -> FeedHttpResponse:
        """Return status, optional body, and conditional-request headers."""


class LlmClient(Protocol):
    """Generate a structured digest from candidate article JSON."""

    async def generate_digest(
        self,
        *,
        system: str,
        articles_json: str,
        model: str,
        max_output_tokens: int,
        repair_errors: str | None = None,
    ) -> LlmDigestResult:
        """Return schema-valid digest output and usage metadata."""


class TelegramClient(Protocol):
    """Send one Telegram HTML message to a configured chat."""

    async def send_message(self, *, chat_id: str, text: str) -> TelegramSendResult:
        """Deliver one message part and return the Telegram message id."""
