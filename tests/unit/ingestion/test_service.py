from io import BytesIO
from pathlib import Path

import pytest

from domain.schemas import DocumentStatus
from ingestion.service import IngestionService
from retrieval.memory_store import MemoryChunkStore
from storage.registry import DocumentRegistry


def _docx_bytes(build) -> bytes:
    pytest.importorskip("docx")
    from docx import Document as DocxDocument

    document = DocxDocument()
    build(document)
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def test_reingesting_same_content_is_idempotent(tmp_path: Path) -> None:
    store = MemoryChunkStore()
    service = IngestionService(DocumentRegistry(tmp_path / "registry.json"), store)
    content = b"# Nghi phep\n\nNhan vien duoc nghi 15 ngay."

    first = service.ingest_bytes("policy.md", content)
    second = service.ingest_bytes("policy.md", content)

    assert first.id == second.id
    assert first.version == second.version == 1
    assert len(store.all_chunks) == 1


def test_new_content_replaces_active_document_version(tmp_path: Path) -> None:
    store = MemoryChunkStore()
    service = IngestionService(DocumentRegistry(tmp_path / "registry.json"), store)

    old = service.ingest_bytes("policy.md", b"Old policy")
    new = service.ingest_bytes("policy.md", b"New policy")

    assert new.id == old.id
    assert new.version == 2
    assert {chunk.text for chunk in store.all_chunks} == {"New policy"}


def test_docx_sections_survive_chunking(tmp_path: Path) -> None:
    def build(document) -> None:
        document.add_heading("Quy trinh su co", level=1)
        document.add_paragraph("Bao cao trong 24 gio.")

    store = MemoryChunkStore()
    service = IngestionService(DocumentRegistry(tmp_path / "registry.json"), store)

    document = service.ingest_bytes("suco.docx", _docx_bytes(build))

    assert document.status is DocumentStatus.READY
    assert [chunk.section for chunk in store.all_chunks] == ["Quy trinh su co"]


def test_empty_markdown_is_failed_not_needs_ocr(tmp_path: Path) -> None:
    service = IngestionService(
        DocumentRegistry(tmp_path / "registry.json"),
        MemoryChunkStore(),
    )

    document = service.ingest_bytes("empty.md", b"")

    assert document.status is DocumentStatus.FAILED


def test_force_reindex_replaces_chunks_without_creating_new_version(tmp_path: Path) -> None:
    store = MemoryChunkStore()
    service = IngestionService(DocumentRegistry(tmp_path / "registry.json"), store)
    content = b"Current policy"
    document = service.ingest_bytes("policy.md", content)
    store.all_chunks = []

    reindexed = service.ingest_bytes("policy.md", content, force=True)

    assert reindexed.version == document.version
    assert [chunk.text for chunk in store.all_chunks] == ["Current policy"]


def test_unprocessable_new_version_keeps_last_ready_chunks(
    tmp_path: Path, monkeypatch
) -> None:
    store = MemoryChunkStore()
    service = IngestionService(DocumentRegistry(tmp_path / "registry.json"), store)
    responses = iter([("Active policy", "application/pdf"), ("", "application/pdf")])
    monkeypatch.setattr(
        "ingestion.service.parse_document",
        lambda filename, content: next(responses),
    )

    active = service.ingest_bytes("policy.pdf", b"version-1")
    pending = service.ingest_bytes("policy.pdf", b"version-2-scan")

    assert active.status is DocumentStatus.READY
    assert pending.status is DocumentStatus.NEEDS_OCR
    assert [chunk.text for chunk in store.all_chunks] == ["Active policy"]


def test_upload_storage_failure_does_not_publish_document(
    tmp_path: Path, monkeypatch
) -> None:
    store = MemoryChunkStore()
    registry = DocumentRegistry(tmp_path / "registry.json")
    service = IngestionService(registry, store, tmp_path / "uploads")

    def fail_write(self: Path, content: bytes) -> int:
        raise OSError("disk full")

    monkeypatch.setattr(Path, "write_bytes", fail_write)

    with pytest.raises(OSError, match="disk full"):
        service.ingest_bytes("policy.md", b"New policy")

    assert registry.list() == []
    assert store.all_chunks == []


def test_ingestion_service_allows_reingestion_of_same_source(tmp_path: Path) -> None:
    """In single-user mode, re-ingesting the same source always succeeds."""
    store = MemoryChunkStore()
    service = IngestionService(DocumentRegistry(tmp_path / "registry.json"), store)
    first = service.ingest_bytes("policy.md", b"HR policy")

    second = service.ingest_bytes("policy.md", b"Updated policy content")

    assert first.id == second.id
    assert second.version == first.version + 1
