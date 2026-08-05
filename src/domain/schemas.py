from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class DocumentStatus(StrEnum):
    PROCESSING = "processing"
    READY = "ready"
    NEEDS_OCR = "needs_ocr"
    FAILED = "failed"


class Document(BaseModel):
    id: str
    version: int
    content_hash: str
    source_name: str
    mime_type: str
    uploaded_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    status: DocumentStatus
    metadata: dict[str, str] = Field(default_factory=dict)


class Chunk(BaseModel):
    id: str
    document_id: str
    version: int
    text: str
    content_hash: str
    source_name: str
    mime_type: str
    status: DocumentStatus
    section: str | None = None
    position: int = 0
    retrieval_text: str | None = None
    summary: str | None = None
    hypothesis_questions: list[str] = Field(default_factory=list)
    auto_metadata: dict[str, str] = Field(default_factory=dict)


class SearchHit(BaseModel):
    chunk: Chunk
    score: float


class ChunkPage(BaseModel):
    """A slice of the chunks stored for one document, ordered by position."""

    document_id: str
    source_name: str
    version: int
    total: int
    offset: int
    limit: int
    chunks: list[Chunk]


class ChunkStats(BaseModel):
    chunk_count: int
    total_chars: int
    min_chars: int
    median_chars: int
    max_chars: int
    sections_detected: int
    chunks_without_section: int
    chunks_at_max_chars: int


class ChunkPreview(BaseModel):
    """Result of parse + chunk without embedding, indexing or touching the registry."""

    source_name: str
    mime_type: str
    status: DocumentStatus
    parsed_characters: int
    max_chars: int
    stats: ChunkStats
    chunks: list[Chunk]


class RankedHit(BaseModel):
    rank: int
    score: float
    chunk: Chunk


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    limit: int | None = Field(default=None, ge=1, le=50)


class SearchResponse(BaseModel):
    query: str
    limit: int
    result_count: int
    latency_ms: float
    hits: list[RankedHit]


class Citation(BaseModel):
    id: str
    document_id: str
    chunk_id: str
    source_name: str
    version: int
    excerpt: str
    section: str | None = None


class RetrievalInfo(BaseModel):
    result_count: int
    latency_ms: float


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = None


class ChatResponse(BaseModel):
    answer: str
    citations: list[Citation]
    retrieval: RetrievalInfo
    request_id: str
    provider: str | None = None
    model: str | None = None
