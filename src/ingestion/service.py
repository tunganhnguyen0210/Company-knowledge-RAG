from __future__ import annotations

import time
from hashlib import sha256
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from domain.schemas import Chunk, Document, DocumentStatus
from ingestion.chunker import chunk_document
from ingestion.enrichment import ChunkEnricher
from ingestion.parser import parse_document
from observability.tracing import Tracer
from retrieval.base import ChunkStore
from settings import Settings, TraceMode
from storage.registry import DocumentRegistry

CHUNK_MAX_CHARS = 1200


class IngestionService:
    def __init__(
        self,
        registry: DocumentRegistry,
        store: ChunkStore,
        upload_dir: Path | None = None,
        enricher: ChunkEnricher | None = None,
        tracer: Tracer | None = None,
        extracted_dir: Path | None = None,
    ) -> None:
        self.registry = registry
        self.store = store
        self.upload_dir = upload_dir
        self.extracted_dir = extracted_dir
        self.enricher = enricher
        self.tracer = tracer if tracer is not None else Tracer(Settings(_env_file=None, trace_mode=TraceMode.OFF))
        self._ingest_lock = Lock()

    def ingest_bytes(
        self,
        filename: str,
        content: bytes,
        metadata: dict[str, str] | None = None,
        *,
        force: bool = False,
    ) -> Document:
        with self._ingest_lock:
            with self.tracer.span(
                "ingestion",
                self.tracer.safe_payload({"source_name": filename, "file_bytes": len(content)}),
            ) as ingestion_observation:
                return self._ingest_bytes(
                    filename,
                    content,
                    metadata,
                    force=force,
                    ingestion_observation=ingestion_observation,
                )

    def _ingest_bytes(
        self,
        filename: str,
        content: bytes,
        metadata: dict[str, str] | None,
        *,
        force: bool,
        ingestion_observation: Any,
    ) -> Document:
        digest = sha256(content).hexdigest()
        previous = self.registry.find_by_source(filename)
        same_content = False
        if previous is not None and previous.content_hash == digest:
            same_content = True
            if not force:
                self.tracer.update(
                    ingestion_observation,
                    {
                        "outcome": "idempotent_skip",
                        "document_id": previous.id,
                        "version": previous.version,
                        "content_hash": previous.content_hash,
                    },
                )
                return previous
        document_id = previous.id if previous else str(uuid5(NAMESPACE_URL, filename))
        if previous is None:
            version = 1
        elif same_content:
            version = previous.version
        else:
            version = previous.version + 1
        parse_started = time.perf_counter()
        with self.tracer.span(
            "parse",
            self.tracer.safe_payload({"source_name": filename, "file_bytes": len(content)}),
        ) as parse_observation:
            text, mime_type = parse_document(filename, content)
            if text.strip():
                status = DocumentStatus.READY
            elif mime_type == "application/pdf":
                status = DocumentStatus.NEEDS_OCR
            else:
                status = DocumentStatus.FAILED
            self.tracer.update(
                parse_observation,
                {
                    "mime_type": mime_type,
                    "parsed_characters": len(text),
                    "parsed_text": text,
                    "status": status.value,
                    "latency_ms": (time.perf_counter() - parse_started) * 1000,
                },
            )
        document = Document(
            id=document_id,
            version=version,
            content_hash=digest,
            source_name=filename,
            mime_type=mime_type,
            status=status,
            metadata=metadata or {},
        )

        chunking_started = time.perf_counter()
        with self.tracer.span(
            "chunking",
            self.tracer.safe_payload({"document_id": document.id, "version": document.version}),
        ) as chunking_observation:
            chunks = chunk_document(document, text, max_chars=CHUNK_MAX_CHARS) if status is DocumentStatus.READY else []
            self.tracer.update(
                chunking_observation,
                {
                    "document_id": document.id,
                    "version": document.version,
                    "max_chars": CHUNK_MAX_CHARS,
                    "chunk_count": len(chunks),
                    "latency_ms": (time.perf_counter() - chunking_started) * 1000,
                    "chunks": [_chunk_trace_payload(chunk) for chunk in chunks],
                },
            )
        if self.enricher is not None:
            enrichment_started = time.perf_counter()
            with self.tracer.span(
                "enrichment",
                self.tracer.safe_payload({"document_id": document.id, "version": document.version}),
            ) as enrichment_observation:
                chunks = [self.enricher.enrich(chunk) for chunk in chunks]
                self.tracer.update(
                    enrichment_observation,
                    {
                        "document_id": document.id,
                        "version": document.version,
                        "chunk_count": len(chunks),
                        "latency_ms": (time.perf_counter() - enrichment_started) * 1000,
                    },
                )
        if self.upload_dir is not None:
            self.upload_dir.mkdir(parents=True, exist_ok=True)
            suffix = Path(filename).suffix.lower()
            (self.upload_dir / f"{document.id}.v{document.version}{suffix}").write_bytes(content)
        if self.extracted_dir is not None and text.strip():
            self.extracted_dir.mkdir(parents=True, exist_ok=True)
            stem = Path(filename).stem
            (self.extracted_dir / f"{stem}.md").write_text(text, encoding="utf-8")
        if status is DocumentStatus.READY:
            indexing_started = time.perf_counter()
            with self.tracer.span(
                "indexing",
                self.tracer.safe_payload({"document_id": document.id, "version": document.version}),
            ) as indexing_observation:
                self.store.replace_document(document.id, chunks)
                self.tracer.update(
                    indexing_observation,
                    {
                        "document_id": document.id,
                        "version": document.version,
                        "status": document.status.value,
                        "chunk_count": len(chunks),
                        "latency_ms": (time.perf_counter() - indexing_started) * 1000,
                    },
                )
        registry_started = time.perf_counter()
        with self.tracer.span(
            "registry",
            self.tracer.safe_payload({"document_id": document.id, "version": document.version}),
        ) as registry_observation:
            self.registry.upsert(document)
            self.tracer.update(
                registry_observation,
                {
                    "document_id": document.id,
                    "version": document.version,
                    "status": document.status.value,
                    "chunk_count": len(chunks),
                    "latency_ms": (time.perf_counter() - registry_started) * 1000,
                },
            )
        self.tracer.update(
            ingestion_observation,
            {
                "outcome": "completed",
                "document_id": document.id,
                "version": document.version,
                "content_hash": document.content_hash,
                "status": document.status.value,
            },
        )
        return document


def _chunk_trace_payload(chunk: Chunk) -> dict[str, Any]:
    return {
        "id": chunk.id,
        "document_id": chunk.document_id,
        "version": chunk.version,
        "position": chunk.position,
        "section": chunk.section,
        "content_hash": chunk.content_hash,
        "source_name": chunk.source_name,
        "mime_type": chunk.mime_type,
        "doc_id": chunk.coordinates.doc_id,
        "chapter": chunk.coordinates.chapter,
        "article": chunk.coordinates.article,
        "text": chunk.text,
    }
