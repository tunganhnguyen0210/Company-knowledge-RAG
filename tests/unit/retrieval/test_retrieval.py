from domain.schemas import Chunk, DocumentStatus, SourceCoordinates
from retrieval.memory_store import MemoryChunkStore


def _chunk(
    chunk_id: str,
    text: str,
    *,
    document_id: str | None = None,
    version: int = 1,
) -> Chunk:
    return Chunk(
        id=chunk_id,
        document_id=document_id or f"doc-{chunk_id}",
        version=version,
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


def test_list_document_chunks_filters_version() -> None:
    store = MemoryChunkStore()
    first = _chunk("v1", "first", document_id="doc", version=1)
    second = _chunk("v2", "second", document_id="doc", version=2)
    store.all_chunks = [first, second]

    assert store.list_document_chunks("doc", version=2) == [second]
