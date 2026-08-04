import os
from uuid import uuid4

import pytest

from domain.schemas import Chunk, DocumentStatus
from retrieval.qdrant_store import QdrantChunkStore

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_QDRANT_INTEGRATION") != "1",
    reason="Set RUN_QDRANT_INTEGRATION=1 with Qdrant running",
)


class FakeEmbedder:
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_query(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        lowered = text.casefold()
        return [
            1.0 if "nghỉ" in lowered else 0.0,
            1.0 if "lương" in lowered else 0.0,
            0.1,
            0.1,
        ]


def _chunk(chunk_id: str, document_id: str, text: str) -> Chunk:
    return Chunk(
        id=chunk_id,
        document_id=document_id,
        version=1,
        text=text,
        content_hash=chunk_id,
        source_name=f"{document_id}.md",
        mime_type="text/markdown",
        status=DocumentStatus.READY,
    )


def test_qdrant_replaces_document_chunks() -> None:
    collection = f"test_company_rag_{uuid4().hex}"
    store = QdrantChunkStore(
        "http://localhost:6333",
        "",
        collection,
        4,
        FakeEmbedder(),
        100,
    )
    try:
        store.replace_document("leave", [_chunk("leave-v1", "leave", "Nghỉ 12 ngày")])
        store.replace_document("salary", [_chunk("salary-v1", "salary", "Lương giám đốc")])
        store.replace_document("leave", [_chunk("leave-v2", "leave", "Nghỉ 15 ngày")])

        results = store.search(
            "lương và nghỉ phép",
            limit=10,
        )

        chunk_ids = {hit.chunk.id for hit in results}
        assert "leave-v2" in chunk_ids
        assert "leave-v1" not in chunk_ids
    finally:
        if store.client.collection_exists(collection):
            store.client.delete_collection(collection)
