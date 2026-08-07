from types import SimpleNamespace

from domain.schemas import Chunk, DocumentStatus, SourceCoordinates
from retrieval.hierarchical import ExpansionConfig
from retrieval.memory_store import MemoryChunkStore
from retrieval.qdrant_store import QdrantChunkStore, _chunk_payload
from tests.support.builders import make_family


class _UnitEmbedder:
    def embed_query(self, _: str) -> list[float]:
        return [1.0]


class _FamilyClient:
    """Fake Qdrant client serving one chunk family; counts scroll round trips."""

    def __init__(self, family: list[Chunk]) -> None:
        self.family = family
        self.scroll_calls = 0

    def query_points(self, **_: object) -> SimpleNamespace:
        return SimpleNamespace(
            points=[
                SimpleNamespace(payload=_chunk_payload(chunk), score=0.9 - index * 0.01)
                for index, chunk in enumerate(self.family)
            ]
        )

    def scroll(self, **_: object) -> tuple[list[SimpleNamespace], None]:
        self.scroll_calls += 1
        return [SimpleNamespace(payload=_chunk_payload(chunk)) for chunk in self.family], None


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


def test_expansion_disabled_by_default_returns_only_ranked_hits() -> None:
    family = make_family(texts=["nghi phep phan dau. ", "nghi phep phan cuoi."])
    store = MemoryChunkStore()
    store.replace_document("doc-1", family)

    results = store.search("nghi phep phan dau", limit=1)

    assert len(results) == 1


def test_memory_store_expansion_pulls_in_sibling() -> None:
    family = make_family(texts=["nghi phep phan dau. ", "nghi phep phan cuoi."])
    store = MemoryChunkStore(ExpansionConfig(enabled=True))
    store.replace_document("doc-1", family)

    results = store.search("nghi phep phan dau", limit=1)

    assert [hit.chunk.id for hit in results] == [family[0].id, family[1].id]


def test_both_stores_agree_on_expanded_chunk_set() -> None:
    """Contract test: the shared helper must not diverge between backends."""
    family = make_family(texts=["alpha phan dau. ", "beta phan giua. ", "gamma phan cuoi."])
    expansion = ExpansionConfig(enabled=True)

    memory = MemoryChunkStore(expansion)
    memory.replace_document("doc-1", family)
    memory_ids = {hit.chunk.id for hit in memory.search("alpha phan dau", limit=1)}

    qdrant = object.__new__(QdrantChunkStore)
    qdrant.client = _FamilyClient(family)
    qdrant.collection = "test"
    qdrant.embedder = _UnitEmbedder()
    qdrant.lexical_candidate_limit = 100
    qdrant.rerank_candidate_limit = 100
    qdrant.min_dense_score = 0.0
    qdrant.reranker = None
    qdrant.expansion = expansion
    qdrant.ensure_collection = lambda: None
    qdrant_ids = {hit.chunk.id for hit in qdrant.search("alpha phan dau", limit=1)}

    assert memory_ids == qdrant_ids == {chunk.id for chunk in family}


def test_expansion_uses_existing_scroll_without_extra_round_trip() -> None:
    family = make_family(texts=["alpha phan dau. ", "beta phan cuoi."])
    client = _FamilyClient(family)
    store = object.__new__(QdrantChunkStore)
    store.client = client
    store.collection = "test"
    store.embedder = _UnitEmbedder()
    store.lexical_candidate_limit = 100
    store.rerank_candidate_limit = 100
    store.min_dense_score = 0.0
    store.reranker = None
    store.expansion = ExpansionConfig(enabled=True)
    store.ensure_collection = lambda: None

    results = store.search("alpha", limit=1)

    assert len(results) == 2
    assert client.scroll_calls == 1, "sibling pool must reuse the BM25 scroll"
