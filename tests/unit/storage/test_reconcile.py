from pathlib import Path

from domain.schemas import Document, DocumentStatus
from retrieval.memory_store import MemoryChunkStore
from storage.reconcile import purge_orphans, reconcile
from storage.registry import DocumentRegistry
from tests.support.builders import make_chunk


def _document(document_id: str, source_name: str) -> Document:
    return Document(
        id=document_id,
        version=1,
        content_hash=f"hash-{document_id}",
        source_name=source_name,
        mime_type="text/markdown",
        status=DocumentStatus.READY,
    )


def _store_with(*groups: tuple[str, int]) -> MemoryChunkStore:
    store = MemoryChunkStore()
    for document_id, count in groups:
        store.replace_document(
            document_id,
            [
                make_chunk(chunk_id=f"{document_id}-{index}", document_id=document_id, position=index)
                for index in range(count)
            ],
        )
    return store


def test_clean_index_reports_no_orphans_or_missing(tmp_path: Path) -> None:
    registry = DocumentRegistry(tmp_path / "registry.json")
    registry.upsert(_document("doc-a", "a.md"))
    store = _store_with(("doc-a", 3))

    report = reconcile(registry, store)

    assert report.is_clean
    assert report.orphan_chunk_count == 0


def test_document_absent_from_registry_is_reported_as_orphan(tmp_path: Path) -> None:
    """The live-collection failure: chunks indexed under a source the registry lost."""
    registry = DocumentRegistry(tmp_path / "registry.json")
    registry.upsert(_document("doc-md", "policy.md"))
    store = _store_with(("doc-md", 244), ("doc-docx", 243))

    report = reconcile(registry, store)

    assert report.orphans == {"doc-docx": 243}
    assert report.orphan_chunk_count == 243
    assert not report.is_clean


def test_document_absent_from_index_is_reported_as_missing_not_orphan(tmp_path: Path) -> None:
    registry = DocumentRegistry(tmp_path / "registry.json")
    registry.upsert(_document("doc-a", "a.md"))
    registry.upsert(_document("doc-b", "b.md"))
    store = _store_with(("doc-a", 2))

    report = reconcile(registry, store)

    assert report.missing == {"doc-b": "b.md"}
    assert report.orphans == {}


def test_purge_removes_only_orphans_and_leaves_registered_documents(tmp_path: Path) -> None:
    registry = DocumentRegistry(tmp_path / "registry.json")
    registry.upsert(_document("doc-md", "policy.md"))
    store = _store_with(("doc-md", 4), ("doc-docx", 3))

    report, removed = purge_orphans(registry, store)

    assert removed == 3
    assert report.orphans == {"doc-docx": 3}
    assert store.list_indexed_documents() == {"doc-md": 4}


def test_purge_is_a_noop_on_a_clean_index(tmp_path: Path) -> None:
    registry = DocumentRegistry(tmp_path / "registry.json")
    registry.upsert(_document("doc-a", "a.md"))
    store = _store_with(("doc-a", 2))

    _, removed = purge_orphans(registry, store)

    assert removed == 0
    assert store.list_indexed_documents() == {"doc-a": 2}


def test_purge_never_touches_documents_only_missing_from_the_index(tmp_path: Path) -> None:
    registry = DocumentRegistry(tmp_path / "registry.json")
    registry.upsert(_document("doc-a", "a.md"))
    registry.upsert(_document("doc-gone", "gone.md"))
    store = _store_with(("doc-a", 2))

    _, removed = purge_orphans(registry, store)

    assert removed == 0
    assert store.list_indexed_documents() == {"doc-a": 2}
