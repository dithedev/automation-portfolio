"""OpenAI Responses API client for structured digest generation."""

from __future__ import annotations

from typing import Any

from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI, RateLimitError
from pydantic import ValidationError
from tenacity import (
    AsyncRetrying,
    retry_if_exception,
    stop_after_attempt,
    wait_random_exponential,
)

from app.application.digest_schema import DigestModelOutput
from app.application.llm_types import LlmDigestResult, LlmError
from app.config import Settings
from app.domain.enums import ErrorCode
from app.prompts import REPAIR_PROMPT, SYSTEM_PROMPT
from app.texts.llm import (
    LLM_INVALID_OUTPUT,
    LLM_RATE_LIMITED,
    LLM_REQUEST_FAILED,
    LLM_TIMEOUT,
)


def _is_retryable(error: BaseException) -> bool:
    return isinstance(error, LlmError) and error.error_code in {
        ErrorCode.OPENAI_TIMEOUT,
        ErrorCode.OPENAI_RATE_LIMITED,
    }


class OpenAIDigestClient:
    """Call OpenAI Responses API with Structured Outputs."""

    def __init__(
        self,
        settings: Settings,
        *,
        client: AsyncOpenAI | None = None,
    ) -> None:
        self._settings = settings
        api_key = settings.openai_api_key
        if client is not None:
            self._client = client
        else:
            if api_key is None:
                raise LlmError(ErrorCode.INVALID_STRUCTURED_OUTPUT, LLM_REQUEST_FAILED)
            self._client = AsyncOpenAI(
                api_key=api_key.get_secret_value(),
                timeout=settings.openai_timeout_seconds,
                max_retries=0,
            )

    async def generate_digest(
        self,
        *,
        system: str,
        articles_json: str,
        model: str,
        max_output_tokens: int,
        repair_errors: str | None = None,
    ) -> LlmDigestResult:
        attempts = max(1, self._settings.openai_max_retries)
        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(attempts),
                wait=wait_random_exponential(multiplier=0.5, max=8),
                retry=retry_if_exception(_is_retryable),
                reraise=True,
            ):
                with attempt:
                    return await self._request_once(
                        system=system,
                        articles_json=articles_json,
                        model=model,
                        max_output_tokens=max_output_tokens,
                        repair_errors=repair_errors,
                    )
        except LlmError:
            raise
        except Exception as error:
            raise LlmError(ErrorCode.INVALID_STRUCTURED_OUTPUT, LLM_REQUEST_FAILED) from error

        raise LlmError(ErrorCode.INVALID_STRUCTURED_OUTPUT, LLM_REQUEST_FAILED)

    async def _request_once(
        self,
        *,
        system: str,
        articles_json: str,
        model: str,
        max_output_tokens: int,
        repair_errors: str | None,
    ) -> LlmDigestResult:
        instructions = system
        input_messages: list[Any] = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": articles_json,
                    }
                ],
            }
        ]
        if repair_errors:
            instructions = f"{SYSTEM_PROMPT}\n\n{REPAIR_PROMPT}"
            input_messages.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": repair_errors,
                        }
                    ],
                }
            )

        try:
            response = await self._client.responses.parse(
                model=model,
                instructions=instructions,
                input=input_messages,
                max_output_tokens=max_output_tokens,
                text_format=DigestModelOutput,
            )
        except APITimeoutError as error:
            raise LlmError(ErrorCode.OPENAI_TIMEOUT, LLM_TIMEOUT) from error
        except RateLimitError as error:
            raise LlmError(ErrorCode.OPENAI_RATE_LIMITED, LLM_RATE_LIMITED) from error
        except APIConnectionError as error:
            raise LlmError(ErrorCode.OPENAI_TIMEOUT, LLM_TIMEOUT) from error
        except APIStatusError as error:
            if error.status_code == 429 or error.status_code >= 500:
                code = (
                    ErrorCode.OPENAI_RATE_LIMITED
                    if error.status_code == 429
                    else ErrorCode.OPENAI_TIMEOUT
                )
                raise LlmError(code, LLM_REQUEST_FAILED) from error
            raise LlmError(ErrorCode.INVALID_STRUCTURED_OUTPUT, LLM_REQUEST_FAILED) from error
        except ValidationError as error:
            raise LlmError(ErrorCode.INVALID_STRUCTURED_OUTPUT, LLM_INVALID_OUTPUT) from error

        parsed = response.output_parsed
        if parsed is None:
            raise LlmError(ErrorCode.INVALID_STRUCTURED_OUTPUT, LLM_INVALID_OUTPUT)

        try:
            output = DigestModelOutput.model_validate(parsed)
        except ValidationError as error:
            raise LlmError(ErrorCode.INVALID_STRUCTURED_OUTPUT, LLM_INVALID_OUTPUT) from error

        usage = getattr(response, "usage", None)
        input_tokens = getattr(usage, "input_tokens", None) if usage is not None else None
        output_tokens = getattr(usage, "output_tokens", None) if usage is not None else None

        return LlmDigestResult(
            output=output,
            response_id=getattr(response, "id", None),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
