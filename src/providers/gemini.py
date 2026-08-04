from __future__ import annotations

from typing import Any

import httpx
import instructor

from providers.base import (
    GenerationRequest,
    GenerationResult,
    ProviderError,
    StructuredResult,
    StructuredT,
)
from providers.structured import STRUCTURED_MAX_RETRIES, create_structured

TRANSIENT_STATUS_CODES = {408, 429, 500, 502, 503, 504}

# Native responseSchema: Gemini constrains decoding to the Pydantic schema.
STRUCTURED_MODE = instructor.Mode.GENAI_STRUCTURED_OUTPUTS


def is_transient_provider_error(exc: Exception) -> bool:
    is_transport_error = isinstance(exc, (TimeoutError, httpx.TransportError))
    code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    if not isinstance(code, (int, str)):
        return is_transport_error
    try:
        return int(code) in TRANSIENT_STATUS_CODES or is_transport_error
    except ValueError:
        return is_transport_error


def generate_content_usage(response: Any) -> dict[str, int]:
    usage_metadata = getattr(response, "usage_metadata", None)
    return {
        "input_tokens": int(getattr(usage_metadata, "prompt_token_count", 0) or 0),
        "output_tokens": int(getattr(usage_metadata, "candidates_token_count", 0) or 0),
    }


class GeminiProvider:
    name = "gemini"

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout_seconds: float = 30.0,
        structured_max_retries: int = STRUCTURED_MAX_RETRIES,
    ) -> None:
        if not api_key:
            raise ValueError("Gemini API key is required")
        from google import genai
        from google.genai import types

        self.model = model
        self.structured_max_retries = structured_max_retries
        self._types = types
        self._client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=int(timeout_seconds * 1000)),
        )
        self._structured_client = instructor.from_genai(self._client, mode=STRUCTURED_MODE)

    def generate(self, request: GenerationRequest) -> GenerationResult:
        try:
            response = self._client.models.generate_content(
                model=self.model,
                contents=request.user_prompt,
                config=self._types.GenerateContentConfig(
                    system_instruction=request.system_instruction,
                    temperature=request.temperature,
                    max_output_tokens=request.max_output_tokens,
                ),
            )
            if not response.text:
                raise ProviderError("Gemini returned an empty response", transient=False)
            return GenerationResult(
                response.text, self.name, self.model, generate_content_usage(response)
            )
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(
                f"Gemini request failed: {exc}",
                transient=is_transient_provider_error(exc),
            ) from exc

    def generate_structured(
        self,
        request: GenerationRequest,
        response_model: type[StructuredT],
    ) -> StructuredResult[StructuredT]:
        value, completion = create_structured(
            self._structured_client,
            provider_name="Gemini",
            model=self.model,
            request=request,
            response_model=response_model,
            max_retries=self.structured_max_retries,
            is_transient=is_transient_provider_error,
            # instructor maps these OpenAI-style keys onto GenerateContentConfig.
            generation_config={
                "temperature": request.temperature,
                "max_tokens": request.max_output_tokens,
            },
        )
        return StructuredResult(value, self.name, self.model, generate_content_usage(completion))

    def ready(self) -> bool:
        return bool(self._client and self.model)
