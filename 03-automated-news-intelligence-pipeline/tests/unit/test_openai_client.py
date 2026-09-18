"""Unit tests for OpenAI digest client error mapping."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from openai import APIConnectionError, APIStatusError, APITimeoutError, RateLimitError
from pydantic import SecretStr, ValidationError

from app.application.digest_schema import DigestModelOutput
from app.application.llm_types import LlmError
from app.config import Settings
from app.domain.enums import ErrorCode
from app.infrastructure.llm.openai_client import OpenAIDigestClient
from app.prompts import SYSTEM_PROMPT

VALID_SUMMARY = (
    "Teams shipping AI features get a concrete product update that clarifies "
    "automation defaults and reduces operational surprise during rollout."
)


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        APP_MODE="demo",
        DATABASE_URL="postgresql+asyncpg://news:news@localhost:5432/news",
        OPENAI_API_KEY=SecretStr("sk-test"),
        OPENAI_MAX_RETRIES=1,
        OPENAI_TIMEOUT_SECONDS=5,
    )


def _client_with_parse(parse: AsyncMock) -> OpenAIDigestClient:
    sdk = SimpleNamespace(responses=SimpleNamespace(parse=parse))
    return OpenAIDigestClient(_settings(), client=sdk)  # type: ignore[arg-type]


def _httpx_response(status_code: int) -> httpx.Response:
    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    return httpx.Response(status_code, request=request)


async def _call(client: OpenAIDigestClient) -> object:
    return await client.generate_digest(
        system=SYSTEM_PROMPT,
        articles_json='{"articles":[]}',
        model="gpt-4o-mini",
        max_output_tokens=800,
    )


@pytest.mark.asyncio
async def test_maps_timeout_to_openai_timeout() -> None:
    parse = AsyncMock(side_effect=APITimeoutError(request=_httpx_response(408).request))
    client = _client_with_parse(parse)
    with pytest.raises(LlmError) as raised:
        await _call(client)
    assert raised.value.error_code is ErrorCode.OPENAI_TIMEOUT


@pytest.mark.asyncio
async def test_maps_rate_limit_error() -> None:
    parse = AsyncMock(
        side_effect=RateLimitError(
            message="rate",
            response=_httpx_response(429),
            body=None,
        )
    )
    client = _client_with_parse(parse)
    with pytest.raises(LlmError) as raised:
        await _call(client)
    assert raised.value.error_code is ErrorCode.OPENAI_RATE_LIMITED


@pytest.mark.asyncio
async def test_maps_connection_error_to_timeout() -> None:
    parse = AsyncMock(
        side_effect=APIConnectionError(request=_httpx_response(500).request),
    )
    client = _client_with_parse(parse)
    with pytest.raises(LlmError) as raised:
        await _call(client)
    assert raised.value.error_code is ErrorCode.OPENAI_TIMEOUT


@pytest.mark.asyncio
async def test_maps_validation_error_to_invalid_structured_output() -> None:
    try:
        DigestModelOutput.model_validate({"digest_title": "x", "items": []})
    except ValidationError as sample:
        parse = AsyncMock(side_effect=sample)
    else:
        raise AssertionError("expected ValidationError for empty items")
    client = _client_with_parse(parse)
    with pytest.raises(LlmError) as raised:
        await _call(client)
    assert raised.value.error_code is ErrorCode.INVALID_STRUCTURED_OUTPUT


@pytest.mark.asyncio
async def test_maps_server_status_error_to_timeout() -> None:
    parse = AsyncMock(
        side_effect=APIStatusError(
            message="down",
            response=_httpx_response(503),
            body=None,
        ),
    )
    client = _client_with_parse(parse)
    with pytest.raises(LlmError) as raised:
        await _call(client)
    assert raised.value.error_code is ErrorCode.OPENAI_TIMEOUT


@pytest.mark.asyncio
async def test_happy_path_returns_parsed_output() -> None:
    output = DigestModelOutput.model_validate(
        {
            "digest_title": "AI Digest",
            "items": [
                {
                    "candidate_id": "c_01",
                    "summary": VALID_SUMMARY,
                    "tag": "PRODUCT",
                    "relevance_score": 0.9,
                    "selection_reason": "Useful",
                }
            ],
        }
    )
    parse = AsyncMock(
        return_value=SimpleNamespace(
            output_parsed=output,
            id="resp_1",
            usage=SimpleNamespace(input_tokens=10, output_tokens=20),
        )
    )
    client = _client_with_parse(parse)
    result = await _call(client)
    assert result.output.digest_title == "AI Digest"
    assert result.response_id == "resp_1"
    assert result.input_tokens == 10
    assert result.output_tokens == 20
