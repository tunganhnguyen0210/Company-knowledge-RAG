from domain.schemas import Chunk, DocumentStatus, SourceCoordinates
from retrieval.memory_store import MemoryChunkStore


def _chunk(chunk_id: str, text: str) -> Chunk:
    return Chunk(
        id=chunk_id,
        document_id=f"doc-{chunk_id}",
        version=1,
        text=text,
        content_hash=chunk_id,
        source_name=f"{chunk_id}.md",
        mime_type="text/markdown",
        status=DocumentStatus.READY,
        coordinates=SourceCoordinates(doc_id="policy.md"),
    )


def test_search_returns_all_ready_chunks_regardless_of_roles() -> None:
    """In single-user mode all ready chunks are searchable without role filtering."""
    store = MemoryChunkStore()
    store.replace_document("doc-a", [_chunk("a", "nghi phep 15 ngay")])
    store.replace_document("doc-b", [_chunk("b", "luong giam doc")])

    results = store.search("luong nghi phep", limit=10)

    chunk_ids = {result.chunk.id for result in results}
    assert "a" in chunk_ids
    assert "b" in chunk_ids


def test_search_excludes_non_ready_chunks() -> None:
    """Chunks not in READY status are never returned."""
    store = MemoryChunkStore()
    store.replace_document(
        "doc-processing",
        [
            Chunk(
                id="proc",
                document_id="doc-processing",
                version=1,
                text="nghi phep processing",
                content_hash="proc",
                source_name="proc.md",
                mime_type="text/markdown",
                status=DocumentStatus.PROCESSING,
                coordinates=SourceCoordinates(doc_id="policy.md"),
            )
        ],
    )

    results = store.search("nghi phep", limit=10)

    assert results == []
