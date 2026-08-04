from __future__ import annotations

import time
from typing import Any, cast

import httpx

from providers.base import ProviderError
from providers.embedding import batched, normalize_embedding

EMBEDDINGS_URL = "https://api.jina.ai/v1/embeddings"
TRANSIENT_STATUS_CODES = {408, 429, 500, 502, 503, 504}

# Conservative: the sync endpoint is bounded by total tokens, not just item count.
EMBED_BATCH_SIZE = 64

# Bulk ingest walks straight into per-minute rate limits, and unlike generation
# there is no router to fail over to, so retrying here is the only recovery.
EMBED_MAX_ATTEMPTS = 5
BASE_RETRY_DELAY_SECONDS = 1.0
MAX_RETRY_DELAY_SECONDS = 30.0

# Asymmetric retrieval: passages and queries are embedded with different task heads.
DOCUMENT_TASK = "retrieval.passage"
QUERY_TASK = "retrieval.query"


def is_transient_jina_error(exc: Exception) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in TRANSIENT_STATUS_CODES
    return isinstance(exc, (TimeoutError, httpx.TransportError))


def retry_delay_seconds(exc: Exception, attempt: int) -> float:
    """Honour the server's own pacing when it sends one, else back off exponentially."""
    if isinstance(exc, httpx.HTTPStatusError):
        retry_after = exc.response.headers.get("Retry-After", "")
        try:
            return min(float(retry_after), MAX_RETRY_DELAY_SECONDS)
        except ValueError:
            pass
    return min(BASE_RETRY_DELAY_SECONDS * (2.0**attempt), MAX_RETRY_DELAY_SECONDS)


class JinaEmbeddingProvider:
    """Jina embeddings v3/v5 over the REST API, with Matryoshka truncation."""

    def __init__(
        self,
        api_key: str,
        model: str,
        output_dimension: int,
        timeout_seconds: float = 30.0,
        batch_size: int = EMBED_BATCH_SIZE,
        max_attempts: int = EMBED_MAX_ATTEMPTS,
    ) -> None:
        if not api_key:
            raise ValueError("Jina API key is required for embeddings")
        self.model = model
        self.output_dimension = output_dimension
        self.batch_size = batch_size
        self.max_attempts = max(1, max_attempts)
        self._client = httpx.Client(
            timeout=timeout_seconds,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
            },
        )

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for batch in batched(texts, self.batch_size):
            vectors.extend(self._embed(batch, DOCUMENT_TASK))
        if len(vectors) != len(texts):
            raise ProviderError(
                f"Jina returned {len(vectors)} embeddings for {len(texts)} chunks",
                transient=False,
            )
        return vectors

    def embed_query(self, text: str) -> list[float]:
        vectors = self._embed([text], QUERY_TASK)
        if not vectors:
            raise ProviderError("Jina returned no embedding", transient=False)
        return vectors[0]

    def _embed(self, texts: list[str], task: str) -> list[list[float]]:
        payload: dict[str, Any] = {
            "model": self.model,
            "task": task,
            "input": texts,
            "dimensions": self.output_dimension,
            "embedding_type": "float",
            "normalized": True,
            # Long chunks are worth degrading, not worth failing the whole batch.
            "truncate": True,
        }
        body = self._post_with_retry(payload)
        return [
            # Truncated Matryoshka vectors need renormalizing before cosine search.
            normalize_embedding([float(value) for value in item["embedding"]])
            for item in sorted(body.get("data", []), key=lambda item: int(item.get("index", 0)))
        ]

    def _post_with_retry(self, payload: dict[str, Any]) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(self.max_attempts):
            try:
                response = self._client.post(EMBEDDINGS_URL, json=payload)
                response.raise_for_status()
                return cast(dict[str, Any], response.json())
            except Exception as exc:
                if not is_transient_jina_error(exc):
                    raise ProviderError(
                        f"Jina embedding request failed: {exc}", transient=False
                    ) from exc
                last_error = exc
                if attempt + 1 < self.max_attempts:
                    time.sleep(retry_delay_seconds(exc, attempt))
        raise ProviderError(
            f"Jina embedding request failed after {self.max_attempts} attempts: {last_error}",
            transient=True,
        ) from last_error
