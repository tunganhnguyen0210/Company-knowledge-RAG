from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from company_knowledge_rag.domain.schemas import Document, DocumentStatus
from company_knowledge_rag.ingestion.chunker import chunk_document
from company_knowledge_rag.ingestion.enrichment import ChunkEnricher
from company_knowledge_rag.ingestion.parser import parse_document
from company_knowledge_rag.retrieval.base import ChunkStore
from company_knowledge_rag.storage.registry import DocumentRegistry


class IngestionService:
    def __init__(
        self,
        registry: DocumentRegistry,
        store: ChunkStore,
        upload_dir: Path | None = None,
        enricher: ChunkEnricher | None = None,
    ) -> None:
        self.registry = registry
        self.store = store
        self.upload_dir = upload_dir
        self.enricher = enricher

    def ingest_bytes(
        self,
        filename: str,
        content: bytes,
        allowed_roles: set[str],
        metadata: dict[str, str] | None = None,
        *,
        force: bool = False,
    ) -> Document:
        digest = sha256(content).hexdigest()
        previous = self.registry.find_by_source(filename)
        same_content = False
        if previous is not None and previous.content_hash == digest:
            same_content = True
            if not force:
                return previous
        document_id = previous.id if previous else str(uuid5(NAMESPACE_URL, filename))
        if previous is None:
            version = 1
        elif same_content:
            version = previous.version
        else:
            version = previous.version + 1
        text, mime_type = parse_document(filename, content)
        status = DocumentStatus.READY if text.strip() else DocumentStatus.NEEDS_OCR
        document = Document(
            id=document_id,
            version=version,
            content_hash=digest,
            source_name=filename,
            mime_type=mime_type,
            status=status,
            allowed_roles=allowed_roles,
            metadata=metadata or {},
        )
        chunks = chunk_document(document, text) if status is DocumentStatus.READY else []
        if self.enricher is not None:
            chunks = [self.enricher.enrich(chunk) for chunk in chunks]
        self.store.replace_document(document.id, chunks)
        self.registry.upsert(document)
        if self.upload_dir is not None:
            self.upload_dir.mkdir(parents=True, exist_ok=True)
            suffix = Path(filename).suffix.lower()
            (self.upload_dir / f"{document.id}{suffix}").write_bytes(content)
        return document
