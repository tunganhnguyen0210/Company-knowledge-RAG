from pathlib import Path

from domain.schemas import Chunk
from ingestion.service import IngestionService
from retrieval.memory_store import MemoryChunkStore
from settings import TraceMode
from storage.registry import DocumentRegistry
from tests.support.tracing import RecordingTracer


class RecordingEnricher:
    def enrich(self, chunk: Chunk) -> Chunk:
        return chunk.model_copy(update={"summary": "Policy summary"})


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
    parse = tracer.observation("parse").updates[-1]
    assert parse["mime_type"] == "text/markdown"
    assert parse["parsed_characters"] == 37
    assert parse["parsed_text"] == "# Leave\n\nNhan vien duoc nghi 15 ngay."
    assert parse["status"] == "ready"
    assert parse["latency_ms"] >= 0

    chunking = tracer.observation("chunking").updates[-1]
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
            "content_hash": "c87af98332a0eb46b36639dfb98967b6d236102a13bf10c86e86daf1722a37dc",
            "source_name": "policy.md",
            "mime_type": "text/markdown",
            "doc_id": "policy.md",
            "chapter": None,
            "article": None,
            "text": "# Leave\n\nNhan vien duoc nghi 15 ngay.",
        }
    ]

    for name in ("indexing", "registry"):
        phase = tracer.observation(name).updates[-1]
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
    tracer.observations.clear()

    service.ingest_bytes("policy.md", content)

    assert tracer.names == ["ingestion"]
    assert tracer.observation("ingestion").updates[-1] == {
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

    assert "parsed_text" not in tracer.observation("parse").updates[-1]
    assert "text" not in tracer.observation("chunking").updates[-1]["chunks"][0]


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
    enrichment = tracer.observation("enrichment").updates[-1]
    assert enrichment["chunk_count"] == 1
    assert enrichment["latency_ms"] >= 0
