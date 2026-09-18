"""Fixture-backed LLM client for demo mode and tests."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from app.application.digest_schema import DigestModelOutput
from app.application.llm_types import LlmDigestResult, LlmError
from app.domain.enums import ErrorCode
from app.texts.llm import LLM_FIXTURE_MISSING, LLM_INVALID_OUTPUT


class MockDigestClient:
    """Return canned Structured Outputs from local JSON fixtures."""

    def __init__(
        self,
        *,
        happy_path: Path,
        invalid_candidate: Path | None = None,
        repair_ok: Path | None = None,
    ) -> None:
        self._happy_path = happy_path
        self._invalid_candidate = invalid_candidate
        self._repair_ok = repair_ok
        self._force_invalid_once = False
        self.calls = 0

    def force_invalid_once(self) -> None:
        """Make the next non-repair call return an invalid candidate fixture."""
        self._force_invalid_once = True

    async def generate_digest(
        self,
        *,
        system: str,
        articles_json: str,
        model: str,
        max_output_tokens: int,
        repair_errors: str | None = None,
    ) -> LlmDigestResult:
        self.calls += 1
        _ = (system, articles_json, model, max_output_tokens)

        if repair_errors is not None:
            path = self._repair_ok or self._happy_path
            payload = self._load(path)
            return self._to_result(payload, response_id="mock-repair-1")

        if self._force_invalid_once and self._invalid_candidate is not None:
            self._force_invalid_once = False
            payload = self._load(self._invalid_candidate)
            return self._to_result(payload, response_id="mock-invalid-1")

        payload = self._load(self._happy_path)
        return self._to_result(payload, response_id="mock-happy-1")

    def _load(self, path: Path) -> dict[str, object]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise LlmError(ErrorCode.INVALID_STRUCTURED_OUTPUT, LLM_FIXTURE_MISSING) from error
        if not isinstance(payload, dict):
            raise LlmError(ErrorCode.INVALID_STRUCTURED_OUTPUT, LLM_INVALID_OUTPUT)
        return {str(key): value for key, value in payload.items()}

    def _to_result(self, payload: dict[str, object], *, response_id: str) -> LlmDigestResult:
        try:
            output = DigestModelOutput.model_validate(payload.get("output", payload))
        except ValidationError as error:
            raise LlmError(ErrorCode.INVALID_STRUCTURED_OUTPUT, LLM_INVALID_OUTPUT) from error

        usage = payload.get("usage", {})
        input_tokens = usage.get("input_tokens") if isinstance(usage, dict) else None
        output_tokens = usage.get("output_tokens") if isinstance(usage, dict) else None

        return LlmDigestResult(
            output=output,
            response_id=str(payload.get("response_id", response_id)),
            input_tokens=int(input_tokens) if input_tokens is not None else 120,
            output_tokens=int(output_tokens) if output_tokens is not None else 80,
        )
