import pytest
import httpx
from domain.schemas import Chunk, SearchHit
from providers.base import ProviderError
from providers.jina import JinaEmbeddingProvider, JinaReranker
from providers.key_pool import ApiKeyPool


def test_jina_embedding_rotates_on_429(monkeypatch):
    pool = ApiKeyPool.from_environment(
        "JINA",
        {"JINA_API_KEY": "key-1", "JINA_API_FALLBACK_KEY": "key-2"},
        cooldown_seconds=30.0,
    )
    provider = JinaEmbeddingProvider(pool, output_dimension=2)

    used_keys = []

    def mock_post(url, headers, json):
        auth = headers.get("Authorization", "")
        key = auth.replace("Bearer ", "")
        used_keys.append(key)
        if key == "key-1":
            return httpx.Response(429, json={"error": "Rate limit exceeded"})
        return httpx.Response(
            200,
            json={
                "data": [
                    {"embedding": [0.1, 0.2]}
                ]
            },
        )

    monkeypatch.setattr(httpx.Client, "post", lambda self, url, headers, json: mock_post(url, headers, json))

    res = provider.embed_query("test query")
    assert res == [0.1, 0.2]
    assert used_keys == ["key-1", "key-2"]


def test_jina_reranker_rotates_on_429(monkeypatch):
    pool = ApiKeyPool.from_environment(
        "JINA",
        {"JINA_API_KEY": "key-1", "JINA_API_FALLBACK_KEY": "key-2"},
        cooldown_seconds=30.0,
    )
    reranker = JinaReranker(pool)

    used_keys = []

    def mock_post(url, headers, json):
        auth = headers.get("Authorization", "")
        key = auth.replace("Bearer ", "")
        used_keys.append(key)
        if key == "key-1":
            return httpx.Response(429, json={"error": "Quota exhausted"})
        return httpx.Response(
            200,
            json={
                "results": [
                    {"index": 0, "relevance_score": 0.95}
                ]
            },
        )

    monkeypatch.setattr(httpx.Client, "post", lambda self, url, headers, json: mock_post(url, headers, json))

    hit = SearchHit(chunk=Chunk(doc_id="d1", chunk_id="c1", text="hello"), score=0.5)
    reranked = reranker.rerank("query", [hit], top_n=1)
    assert len(reranked) == 1
    assert reranked[0].score == 0.95
    assert used_keys == ["key-1", "key-2"]
