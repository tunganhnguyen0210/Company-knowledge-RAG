"""Jina AI Embedding and Reranker providers using HTTP REST API."""

from __future__ import annotations

import time
from typing import Any

import httpx

from domain.schemas import SearchHit
from providers.base import ProviderError
from providers.embedding import batched, normalize_embedding
from providers.key_pool import ApiKeyLease, ApiKeyPool, ApiKeysExhausted

TRANSIENT_STATUS_CODES = {408, 429, 500, 502, 503, 504}
JINA_API_BASE = "https://api.jina.ai/v1"
DEFAULT_BATCH_SIZE = 64
MAX_ATTEMPTS = 5
BASE_RETRY_DELAY = 1.0
MAX_RETRY_DELAY = 30.0


def _jina_pool_from(api_key: str | ApiKeyPool) -> ApiKeyPool:
    if isinstance(api_key, ApiKeyPool):
        return api_key
    if isinstance(api_key, str):
        keys = [api_key.strip()] if api_key.strip() else []
        return ApiKeyPool(keys, provider_name="jina")
    raise ValueError("Jina API key or ApiKeyPool is required")


def is_jina_quota_error(exc: Exception) -> bool:
    text = str(exc).casefold()
    return (
        "429" in text
        or "quota" in text
        or "rate limit" in text
        or "insufficient" in text
        or "authz_insufficient_balance" in text
    )


class JinaEmbeddingProvider:
    """Jina AI embedding provider (v5-omni, v5-text, v3, v4, etc.)."""

    def __init__(
        self,
        api_key: str | ApiKeyPool,
        model: str = "jina-embeddings-v5-omni-small",
        output_dimension: int = 1024,
        timeout_seconds: float = 30.0,
        batch_size: int = DEFAULT_BATCH_SIZE,
        max_attempts: int = MAX_ATTEMPTS,
    ) -> None:
        self._pool = _jina_pool_from(api_key)
        self.model = model
        self.output_dimension = output_dimension
        self.timeout_seconds = timeout_seconds
        self.batch_size = max(1, batch_size)
        self.max_attempts = max(1, max_attempts)

    @property
    def api_key(self) -> str:
        return self._pool.primary_key

    def ready(self) -> bool:
        return bool(self._pool.key_count > 0 and self.model)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors: list[list[float]] = []
        for batch in batched(texts, self.batch_size):
            batch_vectors = self._embed_with_retry(batch, task="retrieval.passage")
            vectors.extend(batch_vectors)
        if len(vectors) != len(texts):
            raise ProviderError(
                f"Jina returned {len(vectors)} embeddings for {len(texts)} chunks",
                transient=False,
            )
        return vectors

    def embed_query(self, text: str) -> list[float]:
        vectors = self._embed_with_retry([text], task="retrieval.query")
        if not vectors:
            raise ProviderError("Jina returned no embedding", transient=False)
        return vectors[0]

    def _embed_batch(
        self, lease: ApiKeyLease, texts: list[str], task: str
    ) -> list[list[float]]:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {lease.api_key}",
        }
        payload: dict[str, Any] = {
            "model": self.model,
            "input": texts,
            "task": task,
            "dimensions": self.output_dimension,
            "normalized": True,
        }
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                resp = client.post(f"{JINA_API_BASE}/embeddings", headers=headers, json=payload)
            if resp.status_code != 200:
                transient = resp.status_code in TRANSIENT_STATUS_CODES
                raise ProviderError(
                    f"Jina Embedding API returned status {resp.status_code}: {resp.text}",
                    transient=transient,
                )
            data = resp.json()
            items = data.get("data", [])
            return [
                normalize_embedding([float(v) for v in item.get("embedding", [])])
                for item in items
            ]
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(
                f"Jina Embedding request failed: {exc}",
                transient=isinstance(exc, (httpx.TransportError, TimeoutError)),
            ) from exc

    def _embed_with_retry(self, texts: list[str], task: str) -> list[list[float]]:
        last_error: Exception | None = None
        for attempt in range(self.max_attempts):
            try:
                return self._pool.invoke(
                    lambda lease: self._embed_batch(lease, texts, task),
                    is_quota_limited=is_jina_quota_error,
                )
            except ApiKeysExhausted as exc:
                if last_error is not None:
                    raise ProviderError(
                        f"Jina Embedding request failed: {last_error}", transient=True
                    ) from last_error
                raise ProviderError(
                    f"All configured Jina API keys exhausted: {exc}", transient=True
                ) from exc
            except ProviderError as exc:
                if not exc.transient:
                    raise
                last_error = exc
                if attempt + 1 < self.max_attempts:
                    delay = min(BASE_RETRY_DELAY * (2.0**attempt), MAX_RETRY_DELAY)
                    time.sleep(delay)
            except Exception as exc:
                raise ProviderError(
                    f"Jina Embedding request failed unexpectedly: {exc}", transient=False
                ) from exc
        raise ProviderError(
            f"Jina Embedding request failed after {self.max_attempts} attempts: {last_error}",
            transient=True,
        ) from last_error


class JinaReranker:
    """Jina AI reranker provider (v3.5, v3, v2, etc.)."""

    def __init__(
        self,
        api_key: str | ApiKeyPool,
        model: str = "jina-reranker-v3.5",
        timeout_seconds: float = 30.0,
        max_attempts: int = MAX_ATTEMPTS,
    ) -> None:
        self._pool = _jina_pool_from(api_key)
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max(1, max_attempts)

    @property
    def api_key(self) -> str:
        return self._pool.primary_key

    def ready(self) -> bool:
        return bool(self._pool.key_count > 0 and self.model)

    def rerank(self, query: str, hits: list[SearchHit], top_n: int) -> list[SearchHit]:
        """Rerank SearchHit candidates against query using Jina Reranker API."""
        if not hits:
            return []
        documents = [hit.chunk.retrieval_text or hit.chunk.text for hit in hits]
        results = self._rerank_with_retry(query, documents, top_n)

        reranked_hits: list[SearchHit] = []
        for res in results:
            idx = int(res["index"])
            score = float(res["relevance_score"])
            if 0 <= idx < len(hits):
                original_hit = hits[idx]
                reranked_hits.append(SearchHit(chunk=original_hit.chunk, score=score))
        return reranked_hits

    def _rerank_api(
        self, lease: ApiKeyLease, query: str, documents: list[str], top_n: int
    ) -> list[dict[str, Any]]:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {lease.api_key}",
        }
        payload = {
            "model": self.model,
            "query": query,
            "documents": documents,
            "top_n": top_n,
        }
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                resp = client.post(f"{JINA_API_BASE}/rerank", headers=headers, json=payload)
            if resp.status_code != 200:
                transient = resp.status_code in TRANSIENT_STATUS_CODES
                raise ProviderError(
                    f"Jina Reranker API returned status {resp.status_code}: {resp.text}",
                    transient=transient,
                )
            data = resp.json()
            return list(data.get("results", []))
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(
                f"Jina Reranker request failed: {exc}",
                transient=isinstance(exc, (httpx.TransportError, TimeoutError)),
            ) from exc

    def _rerank_with_retry(
        self, query: str, documents: list[str], top_n: int
    ) -> list[dict[str, Any]]:
        last_error: Exception | None = None
        for attempt in range(self.max_attempts):
            try:
                return self._pool.invoke(
                    lambda lease: self._rerank_api(lease, query, documents, top_n),
                    is_quota_limited=is_jina_quota_error,
                )
            except ApiKeysExhausted as exc:
                if last_error is not None:
                    raise ProviderError(
                        f"Jina Reranker request failed: {last_error}", transient=True
                    ) from last_error
                raise ProviderError(
                    f"All configured Jina API keys exhausted: {exc}", transient=True
                ) from exc
            except ProviderError as exc:
                if not exc.transient:
                    raise
                last_error = exc
                if attempt + 1 < self.max_attempts:
                    delay = min(BASE_RETRY_DELAY * (2.0**attempt), MAX_RETRY_DELAY)
                    time.sleep(delay)
            except Exception as exc:
                raise ProviderError(
                    f"Jina Reranker request failed unexpectedly: {exc}", transient=False
                ) from exc
        raise ProviderError(
            f"Jina Reranker request failed after {self.max_attempts} attempts: {last_error}",
            transient=True,
        ) from last_error
