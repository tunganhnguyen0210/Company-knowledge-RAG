from typing import Any

import httpx
import pytest

from providers.base import ProviderError
from providers.jina import (
    DOCUMENT_TASK,
    QUERY_TASK,
    JinaEmbeddingProvider,
)


def _provider(handler: Any, batch_size: int = 64) -> JinaEmbeddingProvider:
    provider = JinaEmbeddingProvider("key", "jina-embeddings-v3", 4, batch_size=batch_size)
    provider._client = httpx.Client(transport=httpx.MockTransport(handler))
    return provider


def _embedding_response(request: httpx.Request, vector: list[float]) -> httpx.Response:
    import json

    payload = json.loads(request.content)
    data = [
        {"object": "embedding", "index": index, "embedding": vector}
        for index, _ in enumerate(payload["input"])
    ]
    return httpx.Response(200, json={"data": data, "usage": {"total_tokens": 1}})


def test_passages_and_queries_use_different_task_heads() -> None:
    tasks: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        tasks.append(json.loads(request.content)["task"])
        return _embedding_response(request, [3.0, 4.0, 0.0, 0.0])

    provider = _provider(handler)

    provider.embed_documents(["passage"])
    provider.embed_query("question")

    # Asymmetric retrieval collapses if both sides share one task head.
    assert tasks == [DOCUMENT_TASK, QUERY_TASK]


def test_documents_are_split_into_batches_and_renormalized() -> None:
    sizes: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        sizes.append(len(json.loads(request.content)["input"]))
        return _embedding_response(request, [3.0, 4.0, 0.0, 0.0])

    provider = _provider(handler, batch_size=10)

    vectors = provider.embed_documents([f"chunk-{index}" for index in range(25)])

    assert sizes == [10, 10, 5]
    assert len(vectors) == 25
    assert vectors[0] == pytest.approx([0.6, 0.8, 0.0, 0.0])


def test_embeddings_are_ordered_by_index_not_response_order() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        # Jina may return items out of order; index is the only reliable ordering.
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 1, "embedding": [0.0, 1.0, 0.0, 0.0]},
                    {"index": 0, "embedding": [1.0, 0.0, 0.0, 0.0]},
                ]
            },
        )

    provider = _provider(handler)

    vectors = provider.embed_documents(["first", "second"])

    assert vectors[0] == pytest.approx([1.0, 0.0, 0.0, 0.0])
    assert vectors[1] == pytest.approx([0.0, 1.0, 0.0, 0.0])


@pytest.mark.parametrize(("status", "transient"), [(429, True), (503, True)])
def test_persistent_transient_failures_give_up_after_max_attempts(
    status: int, transient: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("providers.jina.time.sleep", lambda _: None)
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(status, json={"detail": "slow down"})

    provider = _provider(handler)
    provider.max_attempts = 3

    with pytest.raises(ProviderError) as error:
        provider.embed_documents(["chunk"])

    assert attempts == 3
    assert error.value.transient is transient


@pytest.mark.parametrize("status", [401, 422])
def test_permanent_failures_are_not_retried(status: int, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("providers.jina.time.sleep", lambda _: None)
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(status, json={"detail": "nope"})

    provider = _provider(handler)

    with pytest.raises(ProviderError) as error:
        provider.embed_documents(["chunk"])

    # A bad key never becomes good; retrying only burns quota.
    assert attempts == 1
    assert error.value.transient is False


def test_rate_limited_request_recovers_on_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    delays: list[float] = []
    monkeypatch.setattr("providers.jina.time.sleep", delays.append)
    responses = iter([429, 429, 200])

    def handler(request: httpx.Request) -> httpx.Response:
        status = next(responses)
        if status != 200:
            return httpx.Response(status, headers={"Retry-After": "2"}, json={"detail": "wait"})
        return _embedding_response(request, [3.0, 4.0, 0.0, 0.0])

    provider = _provider(handler)

    vectors = provider.embed_documents(["chunk"])

    # Bulk ingest must survive per-minute limits instead of aborting the whole run.
    assert delays == [2.0, 2.0]
    assert vectors[0] == pytest.approx([0.6, 0.8, 0.0, 0.0])


def test_missing_api_key_is_rejected_at_construction() -> None:
    with pytest.raises(ValueError, match="Jina API key is required"):
        JinaEmbeddingProvider("", "jina-embeddings-v3", 1024)
