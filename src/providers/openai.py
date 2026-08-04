from typing import Any

import instructor
from openai import OpenAI

from providers.base import (
    GenerationRequest,
    GenerationResult,
    ProviderError,
    StructuredResult,
    StructuredT,
)
from providers.structured import STRUCTURED_MAX_RETRIES, create_structured

TRANSIENT_STATUS_CODES = {408, 429, 500, 502, 503, 504}

# Native function calling: the schema is enforced by the API, not by prompt text.
STRUCTURED_MODE = instructor.Mode.TOOLS


def is_transient_openai_error(exc: Exception) -> bool:
    status = getattr(exc, "status_code", 0)
    return status in TRANSIENT_STATUS_CODES or exc.__class__.__name__ in {
        "APIConnectionError",
        "APITimeoutError",
    }


def chat_completion_usage(response: Any) -> dict[str, int]:
    usage = getattr(response, "usage", None)
    return {
        "input_tokens": int(getattr(usage, "prompt_tokens", 0) or 0),
        "output_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
    }


class OpenAIProvider:
    name = "openai"

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout: float,
        structured_max_retries: int = STRUCTURED_MAX_RETRIES,
    ) -> None:
        if not api_key:
            raise ValueError("OpenAI API key is required")
        self.model = model
        self.structured_max_retries = structured_max_retries
        self._client = OpenAI(api_key=api_key, timeout=timeout, max_retries=0)
        self._structured_client = instructor.from_openai(self._client, mode=STRUCTURED_MODE)

    def generate(self, request: GenerationRequest) -> GenerationResult:
        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": request.system_instruction},
                    {"role": "user", "content": request.user_prompt},
                ],
                temperature=request.temperature,
                max_tokens=request.max_output_tokens,
            )
            text = response.choices[0].message.content or ""
            if not text:
                raise ProviderError("OpenAI returned an empty response", transient=False)
            return GenerationResult(text, self.name, self.model, chat_completion_usage(response))
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(
                f"OpenAI request failed: {exc}", transient=is_transient_openai_error(exc)
            ) from exc

    def generate_structured(
        self,
        request: GenerationRequest,
        response_model: type[StructuredT],
    ) -> StructuredResult[StructuredT]:
        value, completion = create_structured(
            self._structured_client,
            provider_name="OpenAI",
            model=self.model,
            request=request,
            response_model=response_model,
            max_retries=self.structured_max_retries,
            is_transient=is_transient_openai_error,
            temperature=request.temperature,
            max_tokens=request.max_output_tokens,
        )
        return StructuredResult(value, self.name, self.model, chat_completion_usage(completion))

    def ready(self) -> bool:
        return bool(self._client and self.model)
