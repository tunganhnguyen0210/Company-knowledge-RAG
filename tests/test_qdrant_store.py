from threading import Lock
from types import SimpleNamespace

import pytest

from domain.schemas import Chunk, DocumentStatus
from retrieval import qdrant_store
from retrieval.qdrant_store import QdrantChunkStore, _point_id


def test_point_ids_are_stable_and_unique_for_chunks_in_same_document() -> None:
    first = _point_id("document:v1:0")
    second = _point_id("document:v1:1")

    assert first == _point_id("document:v1:0")
    assert first != second


def test_qdrant_client_uses_write_friendly_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class Client:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

    class Embedder:
        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            return []

        def embed_query(self, text: str) -> list[float]:
            return []

    monkeypatch.setattr(qdrant_store, "QdrantClient", Client)

    QdrantChunkStore("https://qdrant.example", "secret", "test", 3072, Embedder())

    assert captured["timeout"] == 60


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
    )

    with pytest.raises(RuntimeError, match="embedding unavailable"):
        store.replace_document("doc", [chunk])

    assert not store.client.deleted


def test_large_document_is_upserted_in_bounded_batches(monkeypatch: pytest.MonkeyPatch) -> None:
    class Embedder:
        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            return [[float(index)] for index, _ in enumerate(texts)]

        def embed_query(self, text: str) -> list[float]:
            return []

    class RecordingClient:
        def __init__(self) -> None:
            self.upsert_batch_sizes: list[int] = []

        def upsert(self, collection: str, *, points: list[object], wait: bool) -> None:
            self.upsert_batch_sizes.append(len(points))

        def delete(self, *args: object, **kwargs: object) -> None:
            pass

    store = object.__new__(QdrantChunkStore)
    store.client = RecordingClient()  # type: ignore[assignment]
    store.collection = "test"
    store.embedder = Embedder()
    monkeypatch.setattr(store, "ensure_collection", lambda: None)
    chunks = [
        Chunk(
            id=f"chunk-{index}",
            document_id="doc",
            version=1,
            text=f"chunk {index}",
            content_hash=f"hash-{index}",
            source_name="policy.md",
            mime_type="text/markdown",
            status=DocumentStatus.READY,
        )
        for index in range(53)
    ]

    store.replace_document("doc", chunks)

    assert store.client.upsert_batch_sizes == [25, 25, 3]


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


def test_reindex_sweeps_points_the_new_run_did_not_write(monkeypatch: pytest.MonkeyPatch) -> None:
    """A forced reindex keeps the version, so stale positions must go by point id."""

    class Embedder:
        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            return [[1.0] for _ in texts]

        def embed_query(self, text: str) -> list[float]:
            return []

    class RecordingClient:
        def __init__(self) -> None:
            self.delete_filter: object = None

        def upsert(self, collection: str, *, points: list[object], wait: bool) -> None:
            pass

        def delete(self, collection: str, *, points_selector: object, wait: bool) -> None:
            self.delete_filter = points_selector.filter  # type: ignore[attr-defined]

    store = object.__new__(QdrantChunkStore)
    store.client = RecordingClient()  # type: ignore[assignment]
    store.collection = "test"
    store.embedder = Embedder()
    monkeypatch.setattr(store, "ensure_collection", lambda: None)
    chunks = [
        Chunk(
            id=f"doc:v1:{index}",
            document_id="doc",
            version=1,
            text=f"chunk {index}",
            content_hash=f"hash-{index}",
            source_name="policy.md",
            mime_type="text/markdown",
            status=DocumentStatus.READY,
        )
        for index in range(2)
    ]

    store.replace_document("doc", chunks)

    kept = store.client.delete_filter.must_not[0].has_id
    assert kept == [_point_id("doc:v1:0"), _point_id("doc:v1:1")]
