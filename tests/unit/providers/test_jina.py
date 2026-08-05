from unittest.mock import MagicMock, patch

import pytest

from domain.schemas import Chunk, SearchHit
from providers.base import ProviderError
from providers.jina import JinaEmbeddingProvider, JinaReranker


def test_jina_embedding_provider_ready():
    provider = JinaEmbeddingProvider(api_key="jina_test", model="jina-embeddings-v5-omni-small")
    assert provider.ready() is True

    unready = JinaEmbeddingProvider(api_key="", model="")
    assert unready.ready() is False


@patch("httpx.Client.post")
def test_jina_embed_documents(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "data": [
            {"embedding": [0.6, 0.8]},
            {"embedding": [1.0, 0.0]},
        ]
    }
    mock_post.return_value = mock_resp

    provider = JinaEmbeddingProvider(api_key="test_key", output_dimension=2)
    embeddings = provider.embed_documents(["doc 1", "doc 2"])

    assert len(embeddings) == 2
    assert pytest.approx(embeddings[0]) == [0.6, 0.8]
    assert pytest.approx(embeddings[1]) == [1.0, 0.0]


@patch("httpx.Client.post")
def test_jina_embed_query(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "data": [
            {"embedding": [0.0, 1.0]},
        ]
    }
    mock_post.return_value = mock_resp

    provider = JinaEmbeddingProvider(api_key="test_key", output_dimension=2)
    embedding = provider.embed_query("test query")

    assert pytest.approx(embedding) == [0.0, 1.0]


@patch("httpx.Client.post")
def test_jina_embed_error_handling(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.text = "Unauthorized"
    mock_post.return_value = mock_resp

    provider = JinaEmbeddingProvider(api_key="invalid_key", max_attempts=1)
    with pytest.raises(ProviderError) as exc_info:
        provider.embed_query("test")
    assert "401" in str(exc_info.value)
    assert exc_info.value.transient is False


def test_jina_reranker_ready():
    reranker = JinaReranker(api_key="jina_test", model="jina-reranker-v3.5")
    assert reranker.ready() is True


@patch("httpx.Client.post")
def test_jina_reranker_rerank(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "results": [
            {"index": 1, "relevance_score": 0.95},
            {"index": 0, "relevance_score": 0.20},
        ]
    }
    mock_post.return_value = mock_resp

    chunk1 = Chunk(
        id="c1", document_id="d1", chunk_index=0, text="doc 1",
        version=1, content_hash="hash1", source_name="doc1.txt", mime_type="text/plain", status="ready"
    )
    chunk2 = Chunk(
        id="c2", document_id="d1", chunk_index=1, text="doc 2",
        version=1, content_hash="hash2", source_name="doc2.txt", mime_type="text/plain", status="ready"
    )
    hits = [SearchHit(chunk=chunk1, score=0.5), SearchHit(chunk=chunk2, score=0.6)]

    reranker = JinaReranker(api_key="test_key")
    reranked = reranker.rerank("query", hits, top_n=2)

    assert len(reranked) == 2
    assert reranked[0].chunk.id == "c2"
    assert reranked[0].score == 0.95
    assert reranked[1].chunk.id == "c1"
    assert reranked[1].score == 0.20
