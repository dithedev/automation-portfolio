"""Safe HTTPS client for configured RSS/Atom feeds."""

from __future__ import annotations

import time
from collections.abc import Mapping
from urllib.parse import urlsplit, urlunsplit

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception,
    stop_after_attempt,
    wait_random_exponential,
)

from app.application.feed_http_types import FeedHttpError, FeedHttpResponse
from app.config import Settings
from app.domain.enums import ErrorCode
from app.domain.feed_policy import ensure_feed_url
from app.infrastructure.feeds.dns import FeedDNSResolutionError, resolve_public_addresses
from app.texts.feeds import (
    FEED_DNS_RESOLUTION_FAILED,
    FEED_HTTP_CONNECTION_FAILED,
    FEED_HTTP_CONTENT_TYPE_FAILED,
    FEED_HTTP_RETRY_EXHAUSTED,
    FEED_HTTP_STATUS_FAILED,
    FEED_HTTP_TIMEOUT,
    FEED_HTTP_TOO_LARGE,
    FEED_HTTP_UNSAFE,
)

_ALLOWED_CONTENT_TYPES = frozenset(
    {
        "application/rss+xml",
        "application/atom+xml",
        "application/xml",
        "text/xml",
        "application/xhtml+xml",
    }
)


def _is_retryable(error: BaseException) -> bool:
    return isinstance(error, FeedHttpError) and error.error_code in {
        ErrorCode.FEED_TIMEOUT,
        ErrorCode.FEED_CONNECTION_FAILED,
    }


def _normalize_content_type(value: str | None) -> str | None:
    if value is None:
        return None
    return value.split(";", 1)[0].strip().lower()


def _header_value(headers: Mapping[str, str], name: str) -> str | None:
    for key, value in headers.items():
        if key.lower() == name.lower():
            stripped = value.strip()
            return stripped or None
    return None


class SafeFeedHttpClient:
    """Fetch feed bytes with DNS checks, size limits, and no redirects."""

    def __init__(self, settings: Settings, *, client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._client = client
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

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
        try:
            ensure_feed_url(feed_url, allowed_host=allowed_host)
        except ValueError as error:
            raise FeedHttpError(ErrorCode.UNSAFE_FEED_URL, FEED_HTTP_UNSAFE) from error

        parsed = urlsplit(feed_url)
        hostname = parsed.hostname or ""

        try:
            addresses = await resolve_public_addresses(hostname)
        except ValueError as error:
            raise FeedHttpError(ErrorCode.UNSAFE_FEED_URL, FEED_HTTP_UNSAFE) from error
        except FeedDNSResolutionError as error:
            raise FeedHttpError(
                ErrorCode.FEED_CONNECTION_FAILED,
                FEED_DNS_RESOLUTION_FAILED,
            ) from error

        connect_url = urlunsplit(
            (
                "https",
                addresses[0],
                parsed.path or "/",
                parsed.query,
                "",
            )
        )

        headers = {
            "User-Agent": self._settings.user_agent,
            "Accept": (
                "application/rss+xml, application/atom+xml, application/xml, text/xml, */*;q=0.1"
            ),
            "Host": hostname,
        }
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified

        timeout = httpx.Timeout(
            connect=self._settings.http_connect_timeout_seconds,
            read=read_timeout_seconds,
            write=self._settings.http_write_timeout_seconds,
            pool=self._settings.http_pool_timeout_seconds,
        )

        attempts = max(1, self._settings.http_max_retries)

        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(attempts),
                wait=wait_random_exponential(multiplier=0.25, max=4),
                retry=retry_if_exception(_is_retryable),
                reraise=True,
            ):
                with attempt:
                    return await self._request_once(
                        connect_url=connect_url,
                        headers=headers,
                        request_timeout=timeout,
                        max_bytes=max_bytes,
                        sni_hostname=hostname,
                    )
        except FeedHttpError:
            raise
        except Exception as error:
            raise FeedHttpError(
                ErrorCode.FEED_CONNECTION_FAILED,
                FEED_HTTP_RETRY_EXHAUSTED,
            ) from error

        raise FeedHttpError(ErrorCode.FEED_CONNECTION_FAILED, FEED_HTTP_RETRY_EXHAUSTED)

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                follow_redirects=False,
                verify=True,
                trust_env=False,
            )
        return self._client

    async def _request_once(
        self,
        *,
        connect_url: str,
        headers: dict[str, str],
        request_timeout: httpx.Timeout,
        max_bytes: int,
        sni_hostname: str,
    ) -> FeedHttpResponse:
        client = await self._ensure_client()
        started = time.perf_counter()

        try:
            async with client.stream(
                "GET",
                connect_url,
                headers=headers,
                timeout=request_timeout,
                extensions={"sni_hostname": sni_hostname},
            ) as response:
                status_code = response.status_code

                if status_code == 304:
                    duration_ms = int((time.perf_counter() - started) * 1000)
                    return FeedHttpResponse(
                        status_code=304,
                        body=None,
                        etag=_header_value(response.headers, "ETag"),
                        last_modified=_header_value(response.headers, "Last-Modified"),
                        duration_ms=duration_ms,
                    )

                if status_code in {429} or status_code >= 500:
                    await response.aread()
                    raise FeedHttpError(
                        ErrorCode.FEED_CONNECTION_FAILED,
                        FEED_HTTP_STATUS_FAILED,
                    )

                if status_code >= 400:
                    await response.aread()
                    raise FeedHttpError(
                        ErrorCode.FEED_CONNECTION_FAILED,
                        FEED_HTTP_STATUS_FAILED,
                    )

                if not 200 <= status_code <= 299:
                    await response.aread()
                    raise FeedHttpError(
                        ErrorCode.FEED_CONNECTION_FAILED,
                        FEED_HTTP_STATUS_FAILED,
                    )

                content_type = _normalize_content_type(
                    _header_value(response.headers, "Content-Type")
                )
                chunks: list[bytes] = []
                total = 0
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
                    if total > max_bytes:
                        raise FeedHttpError(
                            ErrorCode.FEED_RESPONSE_TOO_LARGE,
                            FEED_HTTP_TOO_LARGE,
                        )
                    chunks.append(chunk)

                body = b"".join(chunks)
                xml_prefix = body.lstrip().startswith((b"<?xml", b"<rss", b"<feed", b"<RDF"))
                if (
                    content_type is not None
                    and content_type not in _ALLOWED_CONTENT_TYPES
                    and not xml_prefix
                ):
                    raise FeedHttpError(
                        ErrorCode.FEED_PARSE_FAILED,
                        FEED_HTTP_CONTENT_TYPE_FAILED,
                    )

                duration_ms = int((time.perf_counter() - started) * 1000)
                return FeedHttpResponse(
                    status_code=status_code,
                    body=body,
                    etag=_header_value(response.headers, "ETag"),
                    last_modified=_header_value(response.headers, "Last-Modified"),
                    duration_ms=duration_ms,
                )
        except FeedHttpError:
            raise
        except httpx.TimeoutException as error:
            raise FeedHttpError(ErrorCode.FEED_TIMEOUT, FEED_HTTP_TIMEOUT) from error
        except httpx.HTTPError as error:
            raise FeedHttpError(
                ErrorCode.FEED_CONNECTION_FAILED,
                FEED_HTTP_CONNECTION_FAILED,
            ) from error
