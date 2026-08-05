from io import BytesIO
from pathlib import Path

import pytest
from pypdf import PdfWriter

from domain.schemas import DocumentStatus
from ingestion.parser import UnsupportedDocumentError, parse_document
from ingestion.service import IngestionService
from retrieval.memory_store import MemoryChunkStore
from storage.registry import DocumentRegistry


def test_scanned_pdf_is_marked_needs_ocr(tmp_path: Path) -> None:
    store = MemoryChunkStore()
    service = IngestionService(DocumentRegistry(tmp_path / "registry.json"), store)
    buffer = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.write(buffer)

    document = service.ingest_bytes("scan.pdf", buffer.getvalue())

    assert document.status is DocumentStatus.NEEDS_OCR
    assert store.all_chunks == []


def test_corrupt_pdf_is_rejected() -> None:
    with pytest.raises(UnsupportedDocumentError, match="Unable to parse PDF"):
        parse_document("corrupt.pdf", b"%PDF-1.4 invalid")
