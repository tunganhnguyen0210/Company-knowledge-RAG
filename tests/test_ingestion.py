from pathlib import Path

from company_knowledge_rag.domain.schemas import DocumentStatus
from company_knowledge_rag.ingestion.service import IngestionService
from company_knowledge_rag.retrieval.memory_store import MemoryChunkStore
from company_knowledge_rag.storage.registry import DocumentRegistry


def test_reingesting_same_content_is_idempotent(tmp_path: Path) -> None:
    store = MemoryChunkStore()
    service = IngestionService(DocumentRegistry(tmp_path / "registry.json"), store)
    content = b"# Nghi phep\n\nNhan vien duoc nghi 15 ngay."

    first = service.ingest_bytes("policy.md", content, {"employee"})
    second = service.ingest_bytes("policy.md", content, {"employee"})

    assert first.id == second.id
    assert first.version == second.version == 1
    assert len(store.all_chunks) == 1


def test_new_content_replaces_active_document_version(tmp_path: Path) -> None:
    store = MemoryChunkStore()
    service = IngestionService(DocumentRegistry(tmp_path / "registry.json"), store)

    old = service.ingest_bytes("policy.md", b"Old policy", {"employee"})
    new = service.ingest_bytes("policy.md", b"New policy", {"employee"})

    assert new.id == old.id
    assert new.version == 2
    assert {chunk.text for chunk in store.all_chunks} == {"New policy"}


def test_scanned_pdf_is_marked_needs_ocr(tmp_path: Path) -> None:
    store = MemoryChunkStore()
    service = IngestionService(DocumentRegistry(tmp_path / "registry.json"), store)

    document = service.ingest_bytes("scan.pdf", b"%PDF-1.4 invalid", {"employee"})

    assert document.status is DocumentStatus.NEEDS_OCR
    assert store.all_chunks == []


def test_force_reindex_replaces_chunks_without_creating_new_version(tmp_path: Path) -> None:
    store = MemoryChunkStore()
    service = IngestionService(DocumentRegistry(tmp_path / "registry.json"), store)
    content = b"Current policy"
    document = service.ingest_bytes("policy.md", content, {"employee"})
    store.all_chunks = []

    reindexed = service.ingest_bytes("policy.md", content, {"employee"}, force=True)

    assert reindexed.version == document.version
    assert [chunk.text for chunk in store.all_chunks] == ["Current policy"]
