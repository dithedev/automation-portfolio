"""Demo-mode feed client that serves local fixtures without outbound HTTP."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from pathlib import Path

from app.application.feed_http_types import FeedHttpError, FeedHttpResponse
from app.config import PROJECT_ROOT, Settings
from app.domain.enums import ErrorCode
from app.domain.feed_policy import ensure_feed_url
from app.texts.feeds import FEED_HTTP_UNSAFE

_FIXTURE_BY_HOST: dict[str, str] = {
    "openai.com": "demo_openai.xml",
    "blog.google": "demo_google.xml",
    "github.blog": "demo_github.xml",
}


def _demo_feeds_dir() -> Path:
    return PROJECT_ROOT / "demo" / "feeds"


def _render_fixture(template: str, *, now: datetime) -> bytes:
    """Fill relative pubDate placeholders so items stay inside the age window."""
    mapping = {
        "{{PUB_DATE_HOURS_AGO_6}}": format_datetime(now - timedelta(hours=6)),
        "{{PUB_DATE_HOURS_AGO_12}}": format_datetime(now - timedelta(hours=12)),
        "{{PUB_DATE_HOURS_AGO_18}}": format_datetime(now - timedelta(hours=18)),
        "{{PUB_DATE_HOURS_AGO_30}}": format_datetime(now - timedelta(hours=30)),
    }
    rendered = template
    for key, value in mapping.items():
        rendered = rendered.replace(key, value)
    return rendered.encode("utf-8")


class DemoFixtureFeedHttpClient:
    """Return trusted fixture bytes keyed by allowed_host (demo mode only)."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._feeds_dir = _demo_feeds_dir()

    async def aclose(self) -> None:
        return None

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
        del read_timeout_seconds, last_modified  # unused — fixtures are local
        try:
            ensure_feed_url(feed_url, allowed_host=allowed_host)
        except ValueError as error:
            raise FeedHttpError(ErrorCode.UNSAFE_FEED_URL, FEED_HTTP_UNSAFE) from error

        filename = _FIXTURE_BY_HOST.get(allowed_host)
        if filename is None:
            raise FeedHttpError(
                ErrorCode.FEED_CONNECTION_FAILED,
                f"No demo fixture mapped for host {allowed_host}",
            )

        path = self._feeds_dir / filename
        template = path.read_text(encoding="utf-8")
        body = _render_fixture(template, now=datetime.now(UTC))
        if len(body) > max_bytes:
            raise FeedHttpError(
                ErrorCode.FEED_RESPONSE_TOO_LARGE,
                "Demo fixture exceeds configured max bytes",
            )

        digest = hashlib.sha256(body).hexdigest()[:16]
        current_etag = f'"{digest}"'
        if etag is not None and etag == current_etag:
            return FeedHttpResponse(
                status_code=304,
                body=None,
                etag=current_etag,
                last_modified=None,
                duration_ms=1,
            )

        return FeedHttpResponse(
            status_code=200,
            body=body,
            etag=current_etag,
            last_modified=None,
            duration_ms=1,
        )
