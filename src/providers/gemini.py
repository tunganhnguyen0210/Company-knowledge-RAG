from __future__ import annotations

from math import sqrt

import httpx

from providers.base import (
    GenerationRequest,
    GenerationResult,
    ProviderError,
)

TRANSIENT_STATUS_CODES = {408, 429, 500, 502, 503, 504}


def is_transient_provider_error(exc: Exception) -> bool:
    is_transport_error = isinstance(exc, (TimeoutError, httpx.TransportError))
    code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    if not isinstance(code, (int, str)):
        return is_transport_error
    try:
        return int(code) in TRANSIENT_STATUS_CODES or is_transport_error
    except ValueError:
        return is_transport_error


def normalize_embedding(values: list[float]) -> list[float]:
    norm = sqrt(sum(value * value for value in values))
    return [value / norm for value in values] if norm else values


class GeminiProvider:
    name = "gemini"

    def __init__(self, api_key: str, model: str, timeout_seconds: float = 30.0) -> None:
        if not api_key:
            raise ValueError("Gemini API key is required")
        from google import genai
        from google.genai import types

        self.model = model
        self._types = types
        self._client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=int(timeout_seconds * 1000)),
        )

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
            usage_metadata = response.usage_metadata
            usage = {
                "input_tokens": int(getattr(usage_metadata, "prompt_token_count", 0) or 0),
                "output_tokens": int(getattr(usage_metadata, "candidates_token_count", 0) or 0),
            }
            return GenerationResult(response.text, self.name, self.model, usage)
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(
                f"Gemini request failed: {exc}",
                transient=is_transient_provider_error(exc),
            ) from exc

    def ready(self) -> bool:
        return bool(self._client and self.model)


class GeminiEmbeddingProvider:
    def __init__(self, api_key: str, model: str, output_dimension: int) -> None:
        if not api_key:
            raise ValueError("Gemini API key is required for embeddings")
        from google import genai
        from google.genai import types

        self.model = model
        self.output_dimension = output_dimension
        self._types = types
        self._client = genai.Client(api_key=api_key)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        response = self._client.models.embed_content(
            model=self.model,
            contents=texts,
            config=self._types.EmbedContentConfig(
                task_type="RETRIEVAL_DOCUMENT",
                output_dimensionality=self.output_dimension,
            ),
        )
        return [normalize_embedding(list(embedding.values or [])) for embedding in response.embeddings or []]

    def embed_query(self, text: str) -> list[float]:
        response = self._client.models.embed_content(
            model=self.model,
            contents=text,
            config=self._types.EmbedContentConfig(
                task_type="RETRIEVAL_QUERY",
                output_dimensionality=self.output_dimension,
            ),
        )
        embeddings = response.embeddings or []
        if not embeddings:
            raise ProviderError("Gemini returned no embedding", transient=False)
        return normalize_embedding(list(embeddings[0].values or []))
