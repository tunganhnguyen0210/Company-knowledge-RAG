import os
from uuid import uuid4

import pytest

from company_knowledge_rag.domain.schemas import Chunk, DocumentStatus, Principal
from company_knowledge_rag.retrieval.qdrant_store import QdrantChunkStore

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


def _chunk(chunk_id: str, document_id: str, text: str, roles: set[str]) -> Chunk:
    return Chunk(
        id=chunk_id,
        document_id=document_id,
        version=1,
        text=text,
        content_hash=chunk_id,
        source_name=f"{document_id}.md",
        mime_type="text/markdown",
        status=DocumentStatus.READY,
        allowed_roles=roles,
    )


def test_qdrant_enforces_acl_and_replaces_document_chunks() -> None:
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
        store.replace_document("leave", [_chunk("leave-v1", "leave", "Nghỉ 12 ngày", {"employee"})])
        store.replace_document("salary", [_chunk("salary-v1", "salary", "Lương giám đốc", {"executive"})])
        store.replace_document("leave", [_chunk("leave-v2", "leave", "Nghỉ 15 ngày", {"employee"})])

        results = store.search(
            "lương và nghỉ phép",
            Principal(subject="employee", roles={"employee"}),
            limit=10,
        )

        assert [hit.chunk.id for hit in results] == ["leave-v2"]
    finally:
        if store.client.collection_exists(collection):
            store.client.delete_collection(collection)
