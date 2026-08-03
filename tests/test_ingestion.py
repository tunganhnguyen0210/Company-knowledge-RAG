from io import BytesIO
from pathlib import Path

import pytest
from pypdf import PdfWriter

from company_knowledge_rag.domain.schemas import DocumentStatus
from company_knowledge_rag.ingestion.parser import UnsupportedDocumentError, parse_document
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
    buffer = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.write(buffer)

    document = service.ingest_bytes("scan.pdf", buffer.getvalue(), {"employee"})

    assert document.status is DocumentStatus.NEEDS_OCR
    assert store.all_chunks == []


def test_corrupt_pdf_is_rejected() -> None:
    with pytest.raises(UnsupportedDocumentError, match="Unable to parse PDF"):
        parse_document("corrupt.pdf", b"%PDF-1.4 invalid")


def test_empty_markdown_is_failed_not_needs_ocr(tmp_path: Path) -> None:
    service = IngestionService(
        DocumentRegistry(tmp_path / "registry.json"),
        MemoryChunkStore(),
    )

    document = service.ingest_bytes("empty.md", b"", {"employee"})

    assert document.status is DocumentStatus.FAILED


def test_force_reindex_replaces_chunks_without_creating_new_version(tmp_path: Path) -> None:
    store = MemoryChunkStore()
    service = IngestionService(DocumentRegistry(tmp_path / "registry.json"), store)
    content = b"Current policy"
    document = service.ingest_bytes("policy.md", content, {"employee"})
    store.all_chunks = []

    reindexed = service.ingest_bytes("policy.md", content, {"employee"}, force=True)

    assert reindexed.version == document.version
    assert [chunk.text for chunk in store.all_chunks] == ["Current policy"]


def test_unprocessable_new_version_keeps_last_ready_chunks(
    tmp_path: Path, monkeypatch,
) -> None:
    store = MemoryChunkStore()
    service = IngestionService(DocumentRegistry(tmp_path / "registry.json"), store)
    responses = iter([("Active policy", "application/pdf"), ("", "application/pdf")])
    monkeypatch.setattr(
        "company_knowledge_rag.ingestion.service.parse_document",
        lambda filename, content: next(responses),
    )

    active = service.ingest_bytes("policy.pdf", b"version-1", {"employee"})
    pending = service.ingest_bytes("policy.pdf", b"version-2-scan", {"employee"})

    assert active.status is DocumentStatus.READY
    assert pending.status is DocumentStatus.NEEDS_OCR
    assert [chunk.text for chunk in store.all_chunks] == ["Active policy"]


def test_upload_storage_failure_does_not_publish_document(
    tmp_path: Path, monkeypatch,
) -> None:
    store = MemoryChunkStore()
    registry = DocumentRegistry(tmp_path / "registry.json")
    service = IngestionService(registry, store, tmp_path / "uploads")

    def fail_write(self: Path, content: bytes) -> int:
        raise OSError("disk full")

    monkeypatch.setattr(Path, "write_bytes", fail_write)

    with pytest.raises(OSError, match="disk full"):
        service.ingest_bytes("policy.md", b"New policy", {"employee"})

    assert registry.list() == []
    assert store.all_chunks == []


def test_ingestion_service_rejects_acl_change_for_existing_source(tmp_path: Path) -> None:
    store = MemoryChunkStore()
    service = IngestionService(DocumentRegistry(tmp_path / "registry.json"), store)
    service.ingest_bytes("policy.md", b"HR policy", {"hr"}, actor_roles={"hr"})

    with pytest.raises(PermissionError, match="Existing document ACL"):
        service.ingest_bytes(
            "policy.md",
            b"Attacker policy",
            {"employee"},
            actor_roles={"employee"},
        )
