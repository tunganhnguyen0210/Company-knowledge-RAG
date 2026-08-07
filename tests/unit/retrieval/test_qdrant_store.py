from threading import Lock
from types import SimpleNamespace

import pytest

from domain.schemas import Chunk, DocumentStatus, SourceCoordinates
from providers.base import ProviderError
from retrieval.hierarchical import DEFAULT_EXPANSION
from retrieval.qdrant_store import QdrantChunkStore, _chunk_from_payload, _chunk_payload, _point_id
from tests.support.builders import make_chunk


def test_point_ids_are_stable_and_unique_for_chunks_in_same_document() -> None:
    first = _point_id("document:v1:0")
    second = _point_id("document:v1:1")

    assert first == _point_id("document:v1:0")
    assert first != second


def test_embedding_failure_does_not_delete_active_document(monkeypatch: pytest.MonkeyPatch) -> None:
    class FailingEmbedder:
        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            raise RuntimeError("embedding unavailable")

        def embed_query(self, text: str) -> list[float]:
            return []

    class RecordingClient:
        deleted = False

        def delete(self, *args: object, **kwargs: object) -> None:
            self.deleted = True

    store = object.__new__(QdrantChunkStore)
    store.client = RecordingClient()  # type: ignore[assignment]
    store.collection = "test"
    store.embedder = FailingEmbedder()
    monkeypatch.setattr(store, "ensure_collection", lambda: None)
    chunk = Chunk(
        id="chunk",
        document_id="doc",
        version=2,
        text="new version",
        content_hash="hash",
        source_name="policy.md",
        mime_type="text/markdown",
        status=DocumentStatus.READY,
        coordinates=SourceCoordinates(doc_id="policy.md"),
    )

    with pytest.raises(RuntimeError, match="embedding unavailable"):
        store.replace_document("doc", [chunk])

    assert not store.client.deleted


def test_existing_collection_with_wrong_vector_size_is_rejected() -> None:
    class SchemaClient:
        def collection_exists(self, collection: str) -> bool:
            return True

        def get_collection(self, collection: str):
            return SimpleNamespace(
                config=SimpleNamespace(
                    params=SimpleNamespace(vectors=SimpleNamespace(size=768))
                ),
                payload_schema={},
            )

    store = object.__new__(QdrantChunkStore)
    store.client = SchemaClient()  # type: ignore[assignment]
    store.collection = "existing"
    store.vector_size = 3072
    store._init_lock = Lock()
    store._initialized = False

    with pytest.raises(RuntimeError, match="vector size"):
        store.ensure_collection()


def test_chunk_payload_flattens_source_coordinates() -> None:
    chunk = Chunk(
        id="chunk",
        document_id="doc",
        version=1,
        text="Điều 1",
        content_hash="hash",
        source_name="law.docx",
        mime_type="application/docx",
        status=DocumentStatus.READY,
        coordinates=SourceCoordinates(doc_id="law.md", chapter="Chương I", article="Điều 1"),
    )

    payload = _chunk_payload(chunk)

    assert payload["doc_id"] == "law.md"
    assert payload["chapter"] == "Chương I"
    assert payload["article"] == "Điều 1"


def test_legacy_payload_requires_corpus_reindex() -> None:
    legacy_payload = {
        "id": "chunk",
        "document_id": "doc",
        "version": 1,
        "text": "legacy",
        "content_hash": "hash",
        "source_name": "law.docx",
        "mime_type": "application/docx",
        "status": "ready",
    }

    with pytest.raises(RuntimeError, match="re-index the corpus"):
        _chunk_from_payload(legacy_payload)


def _search_store(*, reranker: object, candidate_limit: int = 7) -> QdrantChunkStore:
    chunks = [make_chunk(chunk_id=f"chunk-{index}", text=f"policy clause {index}") for index in range(25)]

    class Client:
        def query_points(self, **_: object):
            return SimpleNamespace(
                points=[
                    SimpleNamespace(payload=_chunk_payload(chunk), score=0.9 - index * 0.01)
                    for index, chunk in enumerate(chunks)
                ]
            )

        def scroll(self, **_: object):
            return [SimpleNamespace(payload=_chunk_payload(chunk)) for chunk in chunks], None

    class Embedder:
        def embed_query(self, _: str) -> list[float]:
            return [1.0]

    store = object.__new__(QdrantChunkStore)
    store.client = Client()
    store.collection = "test"
    store.embedder = Embedder()
    store.lexical_candidate_limit = candidate_limit
    store.rerank_candidate_limit = candidate_limit
    store.min_dense_score = 0.0
    store.reranker = reranker
    store.expansion = DEFAULT_EXPANSION
    store.ensure_collection = lambda: None
    return store


def test_reranker_receives_configured_candidate_pool() -> None:
    class RecordingReranker:
        received_count = 0

        def rerank(self, _: str, hits: list[object], top_n: int):
            self.received_count = len(hits)
            return hits[:top_n]

    reranker = RecordingReranker()
    store = _search_store(reranker=reranker)

    assert len(store.search("policy", limit=2)) == 2
    assert reranker.received_count == 7


def test_reranker_failure_returns_rrf_results() -> None:
    class FailingReranker:
        def rerank(self, _: str, hits: list[object], top_n: int):
            raise ProviderError("reranker unavailable", transient=True)

    store = _search_store(reranker=FailingReranker())

    assert [hit.chunk.id for hit in store.search("policy", limit=2)] == ["chunk-0", "chunk-1"]


def test_rrf_only_search_preserves_expanded_candidate_pool() -> None:
    class Client:
        dense_limit = 0

        def query_points(self, **kwargs: object):
            self.dense_limit = int(kwargs["limit"])
            return SimpleNamespace(points=[])

        def scroll(self, **_: object):
            return [], None

    class Embedder:
        def embed_query(self, _: str) -> list[float]:
            return [1.0]

    store = object.__new__(QdrantChunkStore)
    store.client = Client()
    store.collection = "test"
    store.embedder = Embedder()
    store.lexical_candidate_limit = 10
    store.rerank_candidate_limit = 50
    store.min_dense_score = 0.0
    store.reranker = None
    store.expansion = DEFAULT_EXPANSION
    store.ensure_collection = lambda: None

    store.search("policy", limit=2)

    assert store.client.dense_limit == 8


def test_transient_read_error_classification() -> None:
    from httpx import ConnectError
    from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse

    from retrieval.qdrant_store import _is_transient_qdrant_error

    assert _is_transient_qdrant_error(ResponseHandlingException(ConnectError("reset")))
    assert _is_transient_qdrant_error(UnexpectedResponse(503, "Service Unavailable", b"", {}))
    assert not _is_transient_qdrant_error(UnexpectedResponse(404, "Not Found", b"", {}))
    assert not _is_transient_qdrant_error(ValueError("bad payload"))


def test_read_retry_recovers_from_a_disconnect(monkeypatch: pytest.MonkeyPatch) -> None:
    from httpx import ReadTimeout
    from qdrant_client.http.exceptions import ResponseHandlingException

    from retrieval import qdrant_store

    monkeypatch.setattr(qdrant_store.time, "sleep", lambda _seconds: None)
    attempts = {"count": 0}

    def flaky() -> str:
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise ResponseHandlingException(ReadTimeout("timed out"))
        return "ok"

    assert qdrant_store._read_with_retry(flaky, "test read") == "ok"
    assert attempts["count"] == 3


def test_read_retry_gives_up_after_max_attempts(monkeypatch: pytest.MonkeyPatch) -> None:
    from httpx import ConnectError
    from qdrant_client.http.exceptions import ResponseHandlingException

    from retrieval import qdrant_store

    monkeypatch.setattr(qdrant_store.time, "sleep", lambda _seconds: None)
    attempts = {"count": 0}

    def always_down() -> str:
        attempts["count"] += 1
        raise ResponseHandlingException(ConnectError("connection reset"))

    with pytest.raises(RuntimeError, match="failed after 3 attempts"):
        qdrant_store._read_with_retry(always_down, "test read")
    assert attempts["count"] == qdrant_store.MAX_READ_ATTEMPTS


def test_read_retry_does_not_replay_a_client_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from qdrant_client.http.exceptions import UnexpectedResponse

    from retrieval import qdrant_store

    monkeypatch.setattr(qdrant_store.time, "sleep", lambda _seconds: None)
    attempts = {"count": 0}

    def bad_request() -> str:
        attempts["count"] += 1
        raise UnexpectedResponse(400, "Bad Request", b"", {})

    with pytest.raises(UnexpectedResponse):
        qdrant_store._read_with_retry(bad_request, "test read")
    assert attempts["count"] == 1
