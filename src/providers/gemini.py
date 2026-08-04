from __future__ import annotations

from math import sqrt
from typing import Any

import httpx

from providers.base import (
    GenerationRequest,
    GenerationResult,
    ProviderError,
)
from providers.gemini_key_pool import GeminiKeyLease, GeminiKeyPool, GeminiKeysExhausted
from providers.llm_rotation import is_gemini_quota_error, is_gemini_transient_error

TRANSIENT_STATUS_CODES = {408, 429, 500, 502, 503, 504}


def is_transient_provider_error(exc: Exception) -> bool:
    if isinstance(exc, GeminiKeysExhausted):
        return True
    is_transport_error = isinstance(exc, (TimeoutError, httpx.TransportError))
    code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    if not isinstance(code, (int, str)):
        return is_transport_error or is_gemini_transient_error(exc)
    try:
        return int(code) in TRANSIENT_STATUS_CODES or is_transport_error
    except ValueError:
        return is_transport_error or is_gemini_transient_error(exc)


def normalize_embedding(values: list[float]) -> list[float]:
    norm = sqrt(sum(value * value for value in values))
    return [value / norm for value in values] if norm else values


class GeminiProvider:
    name = "gemini"

    def __init__(
        self,
        api_key: str | GeminiKeyPool,
        model: str,
        timeout_seconds: float = 30.0,
    ) -> None:
        if isinstance(api_key, str):
            if not api_key:
                raise ValueError("Gemini API key is required")
            self._pool = GeminiKeyPool([api_key])
        elif isinstance(api_key, GeminiKeyPool):
            if api_key.key_count == 0:
                raise ValueError("Gemini API key is required")
            self._pool = api_key
        else:
            raise ValueError("Gemini API key is required")

        self.model = model
        self.timeout_seconds = timeout_seconds
        self._clients: dict[str, Any] = {}

    def _get_client(self, key: str) -> Any:
        if key not in self._clients:
            from google import genai
            from google.genai import types

            self._types = types
            self._clients[key] = genai.Client(
                api_key=key,
                http_options=types.HttpOptions(timeout=int(self.timeout_seconds * 1000)),
            )
        return self._clients[key]

    def generate(self, request: GenerationRequest) -> GenerationResult:
        def _operation(lease: GeminiKeyLease) -> GenerationResult:
            from google.genai import types

            client = self._get_client(lease.api_key)
            response = client.models.generate_content(
                model=self.model,
                contents=request.user_prompt,
                config=types.GenerateContentConfig(
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

        try:
            return self._pool.invoke(_operation, is_quota_limited=is_gemini_quota_error)
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(
                f"Gemini request failed: {exc}",
                transient=is_transient_provider_error(exc),
            ) from exc

    def ready(self) -> bool:
        return bool(self._pool and self._pool.key_count > 0 and self.model)


class GeminiEmbeddingProvider:
    def __init__(
        self,
        api_key: str | GeminiKeyPool,
        model: str,
        output_dimension: int,
    ) -> None:
        if isinstance(api_key, str):
            if not api_key:
                raise ValueError("Gemini API key is required for embeddings")
            self._pool = GeminiKeyPool([api_key])
        elif isinstance(api_key, GeminiKeyPool):
            if api_key.key_count == 0:
                raise ValueError("Gemini API key is required for embeddings")
            self._pool = api_key
        else:
            raise ValueError("Gemini API key is required for embeddings")

        self.model = model
        self.output_dimension = output_dimension
        self._clients: dict[str, Any] = {}

    def _get_client(self, key: str) -> Any:
        if key not in self._clients:
            from google import genai
            from google.genai import types

            self._clients[key] = genai.Client(
                api_key=key,
                http_options=types.HttpOptions(timeout=30000),
            )
        return self._clients[key]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        def _operation(lease: GeminiKeyLease) -> list[list[float]]:
            from google.genai import types

            client = self._get_client(lease.api_key)
            response = client.models.embed_content(
                model=self.model,
                contents=texts,
                config=types.EmbedContentConfig(
                    task_type="RETRIEVAL_DOCUMENT",
                    output_dimensionality=self.output_dimension,
                ),
            )
            return [
                normalize_embedding(list(embedding.values or []))
                for embedding in response.embeddings or []
            ]

        return self._pool.invoke(_operation, is_quota_limited=is_gemini_quota_error)

    def embed_query(self, text: str) -> list[float]:
        def _operation(lease: GeminiKeyLease) -> list[float]:
            from google.genai import types

            client = self._get_client(lease.api_key)
            response = client.models.embed_content(
                model=self.model,
                contents=text,
                config=types.EmbedContentConfig(
                    task_type="RETRIEVAL_QUERY",
                    output_dimensionality=self.output_dimension,
                ),
            )
            embeddings = response.embeddings or []
            if not embeddings:
                raise ProviderError("Gemini returned no embedding", transient=False)
            return normalize_embedding(list(embeddings[0].values or []))

        return self._pool.invoke(_operation, is_quota_limited=is_gemini_quota_error)
