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


class SourceCoordinates(BaseModel):
    doc_id: str = Field(min_length=1)
    chapter: str | None = None
    article: str | None = None


class Chunk(BaseModel):
    id: str
    document_id: str
    version: int
    text: str
    content_hash: str
    source_name: str
    mime_type: str
    status: DocumentStatus
    coordinates: SourceCoordinates
    section: str | None = None
    position: int = 0
    retrieval_text: str | None = None
    summary: str | None = None
    hypothesis_questions: list[str] = Field(default_factory=list)
    auto_metadata: dict[str, str] = Field(default_factory=dict)


class SearchHit(BaseModel):
    chunk: Chunk
    score: float


class Citation(BaseModel):
    id: str
    document_id: str
    chunk_id: str
    source_name: str
    version: int
    excerpt: str


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
