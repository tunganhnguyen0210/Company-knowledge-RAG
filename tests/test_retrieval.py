from company_knowledge_rag.domain.schemas import Chunk, DocumentStatus, Principal
from company_knowledge_rag.retrieval.memory_store import MemoryChunkStore


def _chunk(chunk_id: str, text: str, roles: set[str]) -> Chunk:
    return Chunk(
        id=chunk_id,
        document_id=f"doc-{chunk_id}",
        version=1,
        text=text,
        content_hash=chunk_id,
        source_name=f"{chunk_id}.md",
        mime_type="text/markdown",
        status=DocumentStatus.READY,
        allowed_roles=roles,
    )


def test_search_filters_unauthorized_documents_before_ranking() -> None:
    store = MemoryChunkStore()
    store.replace_document("doc-public", [_chunk("public", "nghi phep 15 ngay", {"employee"})])
    store.replace_document("doc-secret", [_chunk("secret", "luong giam doc", {"executive"})])

    results = store.search(
        "luong nghi phep",
        Principal(subject="demo", roles={"employee"}),
        limit=10,
    )

    assert [result.chunk.id for result in results] == ["public"]
