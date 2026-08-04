from io import BytesIO
from pathlib import Path
from typing import Any, cast

import pytest
from pypdf import PdfWriter

from api.app import create_app
from domain.schemas import Chunk, DocumentStatus
from ingestion.parser import UnsupportedDocumentError, parse_document
from ingestion.service import IngestionService
from observability.tracing import Tracer
from providers.base import GenerationProvider
from retrieval.memory_store import MemoryChunkStore
from settings import Settings, TraceMode
from storage.registry import DocumentRegistry


class RecordingObservation:
    def __init__(self, name: str, metadata: dict[str, Any]) -> None:
        self.name = name
        self.initial_metadata = metadata
        self.updates: list[dict[str, Any]] = []
        self.active = False

    def __enter__(self) -> "RecordingObservation":
        self.active = True
        return self

    def __exit__(self, *args: object) -> None:
        self.active = False

    def update(self, *, metadata: dict[str, Any]) -> None:
        assert self.active, "trace updated after span closed"
        self.updates.append(metadata)


class RecordingTracer:
    def __init__(self, mode: TraceMode = TraceMode.FULL) -> None:
        self._tracer = Tracer(
            Settings(
                _env_file=None,
                trace_mode=mode,
                allow_sensitive_tracing=mode is TraceMode.FULL,
            )
        )
        self.observations: list[RecordingObservation] = []

    @property
    def names(self) -> list[str]:
        return [observation.name for observation in self.observations]

    def span(self, name: str, metadata: dict[str, Any]) -> RecordingObservation:
        observation = RecordingObservation(name, metadata)
        self.observations.append(observation)
        return observation

    def safe_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._tracer.safe_payload(payload)

    def update(self, observation: RecordingObservation, metadata: dict[str, Any]) -> None:
        self._tracer.update(observation, metadata)

    def updated(self, name: str) -> dict[str, Any]:
        observation = next(item for item in self.observations if item.name == name)
        return observation.updates[-1]

    def clear(self) -> None:
        self.observations.clear()


class RecordingEnricher:
    def enrich(self, chunk: Chunk) -> Chunk:
        return chunk.model_copy(update={"summary": "Policy summary"})


def test_create_app_shares_tracer_between_ingestion_and_chat(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        registry_path=tmp_path / "registry.json",
        upload_dir=tmp_path / "uploads",
    )

    app = create_app(
        settings=settings,
        provider=cast(GenerationProvider, object()),
        store=MemoryChunkStore(),
    )

    assert app.state.ingestion.tracer is app.state.chat.tracer


def test_reingesting_same_content_is_idempotent(tmp_path: Path) -> None:
    store = MemoryChunkStore()
    service = IngestionService(DocumentRegistry(tmp_path / "registry.json"), store)
    content = b"# Nghi phep\n\nNhan vien duoc nghi 15 ngay."

    first = service.ingest_bytes("policy.md", content, {"employee"})
    second = service.ingest_bytes("policy.md", content, {"employee"})

    assert first.id == second.id
    assert first.version == second.version == 1
    assert len(store.all_chunks) == 1


def test_full_ingestion_trace_contains_lifecycle_data(tmp_path: Path) -> None:
    tracer = RecordingTracer()
    service = IngestionService(
        DocumentRegistry(tmp_path / "registry.json"),
        MemoryChunkStore(),
        tracer=tracer,
    )

    document = service.ingest_bytes(
        "policy.md",
        b"# Leave\n\nNhan vien duoc nghi 15 ngay.",
    )

    assert tracer.names == ["ingestion", "parse", "chunking", "indexing", "registry"]
    parse = tracer.updated("parse")
    assert parse["mime_type"] == "text/markdown"
    assert parse["parsed_characters"] == 37
    assert parse["parsed_text"] == "# Leave\n\nNhan vien duoc nghi 15 ngay."
    assert parse["status"] == "ready"
    assert parse["latency_ms"] >= 0

    chunking = tracer.updated("chunking")
    assert chunking["document_id"] == document.id
    assert chunking["version"] == 1
    assert chunking["max_chars"] == 1200
    assert chunking["chunk_count"] == 1
    assert chunking["latency_ms"] >= 0
    assert chunking["chunks"] == [
        {
            "id": f"{document.id}:v1:0",
            "document_id": document.id,
            "version": 1,
            "position": 0,
            "section": "Leave",
            "content_hash": "e2177be7a8ca89422666b323b28aa6a6f5919a2107fb7fc56b64c17210de536b",
            "source_name": "policy.md",
            "mime_type": "text/markdown",
            "text": "Nhan vien duoc nghi 15 ngay.",
        }
    ]

    for name in ("indexing", "registry"):
        phase = tracer.updated(name)
        assert phase["document_id"] == document.id
        assert phase["version"] == 1
        assert phase["status"] == "ready"
        assert phase["chunk_count"] == 1
        assert phase["latency_ms"] >= 0


def test_idempotent_ingestion_trace_marks_skip_without_child_spans(tmp_path: Path) -> None:
    tracer = RecordingTracer()
    service = IngestionService(
        DocumentRegistry(tmp_path / "registry.json"),
        MemoryChunkStore(),
        tracer=tracer,
    )
    content = b"Same policy"
    existing = service.ingest_bytes("policy.md", content)
    tracer.clear()

    service.ingest_bytes("policy.md", content)

    assert tracer.names == ["ingestion"]
    assert tracer.updated("ingestion") == {
        "outcome": "idempotent_skip",
        "document_id": existing.id,
        "version": 1,
        "content_hash": existing.content_hash,
    }


def test_metadata_only_ingestion_trace_redacts_parsed_and_chunk_text(tmp_path: Path) -> None:
    tracer = RecordingTracer(TraceMode.METADATA_ONLY)
    service = IngestionService(
        DocumentRegistry(tmp_path / "registry.json"),
        MemoryChunkStore(),
        tracer=tracer,
    )

    service.ingest_bytes("policy.md", b"Confidential content")

    assert "parsed_text" not in tracer.updated("parse")
    assert "text" not in tracer.updated("chunking")["chunks"][0]


def test_ingestion_trace_includes_enrichment_when_enricher_exists(tmp_path: Path) -> None:
    tracer = RecordingTracer()
    service = IngestionService(
        DocumentRegistry(tmp_path / "registry.json"),
        MemoryChunkStore(),
        enricher=RecordingEnricher(),
        tracer=tracer,
    )

    service.ingest_bytes("policy.md", b"Enrich this policy")

    assert tracer.names == [
        "ingestion",
        "parse",
        "chunking",
        "enrichment",
        "indexing",
        "registry",
    ]
    enrichment = tracer.updated("enrichment")
    assert enrichment["chunk_count"] == 1
    assert enrichment["latency_ms"] >= 0


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
        "ingestion.service.parse_document",
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


def test_ingestion_service_allows_reingestion_of_same_source(tmp_path: Path) -> None:
    """In single-user mode, re-ingesting the same source always succeeds."""
    store = MemoryChunkStore()
    service = IngestionService(DocumentRegistry(tmp_path / "registry.json"), store)
    first = service.ingest_bytes("policy.md", b"HR policy")

    second = service.ingest_bytes("policy.md", b"Updated policy content")

    assert first.id == second.id
    assert second.version == first.version + 1
