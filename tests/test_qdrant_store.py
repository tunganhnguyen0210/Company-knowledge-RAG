from threading import Lock
from types import SimpleNamespace

import pytest

from company_knowledge_rag.domain.schemas import Chunk, DocumentStatus
from company_knowledge_rag.retrieval.qdrant_store import QdrantChunkStore, _point_id


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
        allowed_roles={"employee"},
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
