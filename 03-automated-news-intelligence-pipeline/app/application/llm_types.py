"""Shared LLM digest generation result and error types."""

from dataclasses import dataclass

from app.application.digest_schema import DigestModelOutput
from app.domain.enums import ErrorCode


@dataclass(frozen=True, slots=True, kw_only=True)
class LlmDigestResult:
    """Parsed model output plus usage metadata for audit storage."""

    output: DigestModelOutput
    response_id: str | None
    input_tokens: int | None
    output_tokens: int | None


class LlmError(Exception):
    """Classified LLM failure for pipeline error handling."""

    def __init__(self, error_code: ErrorCode, summary: str) -> None:
        self.error_code = error_code
        self.summary = summary
        super().__init__(summary)
