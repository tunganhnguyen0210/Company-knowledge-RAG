from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from providers.base import ProviderError
from providers.gemini import DOCUMENT_TASK, QUERY_TASK, GeminiEmbeddingProvider
from providers.gemini_key_pool import GeminiKeyPool


def _embedding(values: list[float]) -> Any:
    embedding = MagicMock()
    embedding.values = values
    return embedding


def _provider(
    handler: Any,
    *,
    batch_size: int = 100,
    max_attempts: int = 5,
    pool: GeminiKeyPool | None = None,
) -> GeminiEmbeddingProvider:
    provider = GeminiEmbeddingProvider(
        pool if pool is not None else GeminiKeyPool(["key-1"]),
        "gemini-embedding-001",
        3,
        batch_size=batch_size,
        max_attempts=max_attempts,
    )
    client = MagicMock()
    client.models.embed_content.side_effect = handler
    provider._get_client = lambda _key: client  # type: ignore[method-assign]
    return provider


def test_passages_and_queries_use_different_task_types() -> None:
    tasks: list[str] = []

    def handler(**kwargs: Any) -> Any:
        tasks.append(kwargs["config"].task_type)
        response = MagicMock()
        response.embeddings = [_embedding([1.0, 0.0, 0.0]) for _ in kwargs["contents"]]
        return response

    provider = _provider(handler)

    provider.embed_documents(["passage"])
    provider.embed_query("question")

    # Asymmetric retrieval collapses if both sides share one task type.
    assert tasks == [DOCUMENT_TASK, QUERY_TASK]


def test_documents_are_split_into_batches_and_renormalized() -> None:
    sizes: list[int] = []

    def handler(**kwargs: Any) -> Any:
        sizes.append(len(kwargs["contents"]))
        response = MagicMock()
        response.embeddings = [_embedding([3.0, 4.0, 0.0]) for _ in kwargs["contents"]]
        return response

    provider = _provider(handler, batch_size=10)

    vectors = provider.embed_documents([f"chunk-{index}" for index in range(25)])

    assert sizes == [10, 10, 5]
    assert len(vectors) == 25
    # Truncated Matryoshka vectors are unusable for cosine search until renormalized.
    assert vectors[0] == pytest.approx([0.6, 0.8, 0.0])


def test_short_response_is_rejected_instead_of_misaligning_chunks() -> None:
    def handler(**kwargs: Any) -> Any:
        response = MagicMock()
        response.embeddings = [_embedding([1.0, 0.0, 0.0])]
        return response

    provider = _provider(handler)

    with pytest.raises(ProviderError, match="returned 1 embeddings for 2 chunks"):
        provider.embed_documents(["first", "second"])


def _sleepless_clock(monkeypatch: pytest.MonkeyPatch, delays: list[float]) -> GeminiKeyPool:
    """A single-key pool whose cooldown expires as the retry loop sleeps."""
    now = [0.0]

    def sleep(seconds: float) -> None:
        delays.append(seconds)
        now[0] += seconds

    monkeypatch.setattr("providers.gemini.time.sleep", sleep)
    return GeminiKeyPool(["key-1"], clock=lambda: now[0], cooldown_seconds=60.0)


def test_persistent_rate_limits_give_up_after_max_attempts(monkeypatch: pytest.MonkeyPatch) -> None:
    delays: list[float] = []
    pool = _sleepless_clock(monkeypatch, delays)
    attempts = 0

    def handler(**kwargs: Any) -> Any:
        nonlocal attempts
        attempts += 1
        raise RuntimeError("429 RESOURCE_EXHAUSTED: slow down")

    provider = _provider(handler, max_attempts=3, pool=pool)

    with pytest.raises(ProviderError) as error:
        provider.embed_documents(["chunk"])

    # The middle attempt finds the only key still parked, so it waits out the
    # cooldown instead of spending a call.
    assert attempts == 2
    assert delays == [1.0, 60.0]
    assert error.value.transient is True


def test_rate_limited_request_recovers_on_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    delays: list[float] = []
    pool = _sleepless_clock(monkeypatch, delays)
    failures = iter([True, False])

    def handler(**kwargs: Any) -> Any:
        if next(failures):
            raise RuntimeError("429 RESOURCE_EXHAUSTED")
        response = MagicMock()
        response.embeddings = [_embedding([3.0, 4.0, 0.0]) for _ in kwargs["contents"]]
        return response

    provider = _provider(handler, pool=pool)

    vectors = provider.embed_documents(["chunk"])

    # Bulk ingest must survive per-minute limits instead of aborting the whole run.
    assert delays == [1.0, 60.0]
    assert vectors[0] == pytest.approx([0.6, 0.8, 0.0])


def test_permanent_failures_are_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("providers.gemini.time.sleep", lambda _: None)
    attempts = 0

    def handler(**kwargs: Any) -> Any:
        nonlocal attempts
        attempts += 1
        raise RuntimeError("400 INVALID_ARGUMENT: API key not valid")

    provider = _provider(handler)

    with pytest.raises(ProviderError) as error:
        provider.embed_documents(["chunk"])

    # A bad key never becomes good; retrying only burns quota.
    assert attempts == 1
    assert error.value.transient is False


def test_missing_api_key_is_rejected_at_construction() -> None:
    with pytest.raises(ValueError, match="Gemini API key is required for embeddings"):
        GeminiEmbeddingProvider("", "gemini-embedding-001", 1024)

    with pytest.raises(ValueError, match="Gemini API key is required for embeddings"):
        GeminiEmbeddingProvider(GeminiKeyPool([]), "gemini-embedding-001", 1024)
