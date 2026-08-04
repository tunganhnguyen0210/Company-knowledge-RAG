from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any, TypeVar

import httpx
import instructor

from providers.base import (
    GenerationRequest,
    GenerationResult,
    ProviderError,
    StructuredResult,
    StructuredT,
)
from providers.embedding import batched, normalize_embedding
from providers.gemini_key_pool import GeminiKeyLease, GeminiKeyPool, GeminiKeysExhausted
from providers.llm_rotation import is_gemini_quota_error, is_gemini_transient_error
from providers.structured import STRUCTURED_MAX_RETRIES, create_structured

InvokedT = TypeVar("InvokedT")

TRANSIENT_STATUS_CODES = {408, 429, 500, 502, 503, 504}

# Native responseSchema: Gemini constrains decoding to the Pydantic schema.
STRUCTURED_MODE = instructor.Mode.GENAI_STRUCTURED_OUTPUTS

# Asymmetric retrieval: passages and queries are embedded with different task types.
DOCUMENT_TASK = "RETRIEVAL_DOCUMENT"
QUERY_TASK = "RETRIEVAL_QUERY"

# The embeddings endpoint caps how many texts one request may carry.
EMBED_BATCH_SIZE = 100

# Bulk ingest walks straight into per-minute rate limits, and unlike generation
# there is no router to fail over to, so retrying here is the only recovery.
EMBED_MAX_ATTEMPTS = 5
BASE_RETRY_DELAY_SECONDS = 1.0
MAX_RETRY_DELAY_SECONDS = 30.0


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


def generate_content_usage(response: Any) -> dict[str, int]:
    usage_metadata = getattr(response, "usage_metadata", None)
    return {
        "input_tokens": int(getattr(usage_metadata, "prompt_token_count", 0) or 0),
        "output_tokens": int(getattr(usage_metadata, "candidates_token_count", 0) or 0),
    }


def _pool_from(api_key: str | GeminiKeyPool, purpose: str) -> GeminiKeyPool:
    message = f"Gemini API key is required{purpose}"
    if isinstance(api_key, GeminiKeyPool):
        if api_key.key_count == 0:
            raise ValueError(message)
        return api_key
    if isinstance(api_key, str) and api_key:
        return GeminiKeyPool([api_key])
    raise ValueError(message)


class GeminiProvider:
    name = "gemini"

    def __init__(
        self,
        api_key: str | GeminiKeyPool,
        model: str,
        timeout_seconds: float = 30.0,
        structured_max_retries: int = STRUCTURED_MAX_RETRIES,
    ) -> None:
        self._pool = _pool_from(api_key, "")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.structured_max_retries = structured_max_retries
        self._clients: dict[str, Any] = {}
        self._structured_clients: dict[str, instructor.Instructor] = {}

    def _get_client(self, key: str) -> Any:
        if key not in self._clients:
            from google import genai
            from google.genai import types

            self._clients[key] = genai.Client(
                api_key=key,
                http_options=types.HttpOptions(timeout=int(self.timeout_seconds * 1000)),
            )
        return self._clients[key]

    def _get_structured_client(self, key: str) -> instructor.Instructor:
        if key not in self._structured_clients:
            self._structured_clients[key] = instructor.from_genai(
                self._get_client(key), mode=STRUCTURED_MODE
            )
        return self._structured_clients[key]

    def generate(self, request: GenerationRequest) -> GenerationResult:
        def _operation(lease: GeminiKeyLease) -> GenerationResult:
            from google.genai import types

            response = self._get_client(lease.api_key).models.generate_content(
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
            return GenerationResult(
                response.text, self.name, self.model, generate_content_usage(response)
            )

        return self._invoke(_operation)

    def generate_structured(
        self,
        request: GenerationRequest,
        response_model: type[StructuredT],
    ) -> StructuredResult[StructuredT]:
        def _operation(lease: GeminiKeyLease) -> StructuredResult[StructuredT]:
            value, completion = create_structured(
                self._get_structured_client(lease.api_key),
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
            return StructuredResult(
                value, self.name, self.model, generate_content_usage(completion)
            )

        return self._invoke(_operation)

    def _invoke(self, operation: Callable[[GeminiKeyLease], InvokedT]) -> InvokedT:
        try:
            return self._pool.invoke(operation, is_quota_limited=is_gemini_quota_error)
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(
                f"Gemini request failed: {exc}",
                transient=is_transient_provider_error(exc),
            ) from exc

    def ready(self) -> bool:
        return bool(self._pool.key_count > 0 and self.model)


class GeminiEmbeddingProvider:
    """Gemini embeddings over the same key pool, with Matryoshka truncation."""

    def __init__(
        self,
        api_key: str | GeminiKeyPool,
        model: str,
        output_dimension: int,
        timeout_seconds: float = 30.0,
        batch_size: int = EMBED_BATCH_SIZE,
        max_attempts: int = EMBED_MAX_ATTEMPTS,
    ) -> None:
        self._pool = _pool_from(api_key, " for embeddings")
        self.model = model
        self.output_dimension = output_dimension
        self.timeout_seconds = timeout_seconds
        self.batch_size = max(1, batch_size)
        self.max_attempts = max(1, max_attempts)
        self._clients: dict[str, Any] = {}

    def _get_client(self, key: str) -> Any:
        if key not in self._clients:
            from google import genai
            from google.genai import types

            self._clients[key] = genai.Client(
                api_key=key,
                http_options=types.HttpOptions(timeout=int(self.timeout_seconds * 1000)),
            )
        return self._clients[key]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for batch in batched(texts, self.batch_size):
            vectors.extend(self._embed(batch, DOCUMENT_TASK))
        if len(vectors) != len(texts):
            raise ProviderError(
                f"Gemini returned {len(vectors)} embeddings for {len(texts)} chunks",
                transient=False,
            )
        return vectors

    def embed_query(self, text: str) -> list[float]:
        vectors = self._embed([text], QUERY_TASK)
        if not vectors:
            raise ProviderError("Gemini returned no embedding", transient=False)
        return vectors[0]

    def _embed(self, texts: list[str], task_type: str) -> list[list[float]]:
        def _operation(lease: GeminiKeyLease) -> list[list[float]]:
            from google.genai import types

            response = self._get_client(lease.api_key).models.embed_content(
                model=self.model,
                contents=texts,
                config=types.EmbedContentConfig(
                    task_type=task_type,
                    output_dimensionality=self.output_dimension,
                ),
            )
            return [
                # Truncated Matryoshka vectors need renormalizing before cosine search.
                normalize_embedding([float(value) for value in embedding.values or []])
                for embedding in response.embeddings or []
            ]

        return self._embed_with_retry(_operation)

    def _embed_with_retry(
        self, operation: Callable[[GeminiKeyLease], list[list[float]]]
    ) -> list[list[float]]:
        last_error: Exception | None = None
        for attempt in range(self.max_attempts):
            try:
                return list(
                    self._pool.invoke(operation, is_quota_limited=is_gemini_quota_error)
                )
            except Exception as exc:
                if not self._is_retryable(exc):
                    raise ProviderError(
                        f"Gemini embedding request failed: {exc}", transient=False
                    ) from exc
                last_error = exc
                if attempt + 1 < self.max_attempts:
                    time.sleep(self._retry_delay(exc, attempt))
        raise ProviderError(
            f"Gemini embedding request failed after {self.max_attempts} attempts: {last_error}",
            transient=True,
        ) from last_error

    def _retry_delay(self, exc: Exception, attempt: int) -> float:
        if isinstance(exc, GeminiKeysExhausted):
            # Every key is parked on quota cooldown; a shorter nap would only
            # burn attempts on a pool that cannot answer yet.
            return self._pool.cooldown_seconds
        return min(BASE_RETRY_DELAY_SECONDS * (2.0**attempt), MAX_RETRY_DELAY_SECONDS)

    @staticmethod
    def _is_retryable(exc: Exception) -> bool:
        return (
            isinstance(exc, GeminiKeysExhausted)
            or is_gemini_quota_error(exc)
            or is_transient_provider_error(exc)
        )

    def ready(self) -> bool:
        return bool(self._pool.key_count > 0 and self.model)
