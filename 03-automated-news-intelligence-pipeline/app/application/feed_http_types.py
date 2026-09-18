"""Shared HTTP fetch result and error types for feed ingestion."""

from dataclasses import dataclass

from app.domain.enums import ErrorCode


@dataclass(frozen=True, slots=True, kw_only=True)
class FeedHttpResponse:
    """Outcome of one feed HTTP GET without storing the body in the database."""

    status_code: int
    body: bytes | None
    etag: str | None
    last_modified: str | None
    duration_ms: int


class FeedHttpError(Exception):
    """Signal a classified feed HTTP failure for persistence as FeedFetch."""

    def __init__(self, error_code: ErrorCode, summary: str) -> None:
        self.error_code = error_code
        self.summary = summary
        super().__init__(summary)
