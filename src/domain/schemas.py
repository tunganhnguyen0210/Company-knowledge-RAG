from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field

RAPTOR_SECTION_PREFIX = "__raptor_summary_L"
"""Marks a synthetic RAPTOR summary chunk rather than real document text.

Lives here (not in `ingestion.raptor`) so `retrieval` can recognize these nodes
without importing from `ingestion` -- `ingestion.service` already imports
`retrieval.base`, and the reverse edge would invert the layering.
"""


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
    parent_id: str | None = None
    """Stable identity of the legal section this chunk was split from.

    Siblings (chunks of the same section) share this value, so retrieval can
    group a family and re-assemble the whole section. `None` means unknown --
    either a legacy payload indexed before this field existed, or a synthetic
    node (RAPTOR summaries) that has no real parent. Consumers must treat
    `None` as "not expandable" rather than "own group".
    """
    parent_child_count: int | None = None
    """How many chunks the parent section was split into.

    Lets a consumer tell "I have the whole family" from "the pool is missing a
    member" without seeing the pool. `None` = unknown (legacy payload), which
    must fail closed, hence not defaulted to 1 -- that would be
    indistinguishable from a genuine single-child section.
    """
    child_index: int = 0
    """Ordinal within the parent section. `position` stays document-global."""
    parent_text: str | None = None
    """Larger surrounding window (section-level) for Parent-Child chunking.

    Populated by chunker.py when parent-child chunking is enabled. `text`/
    `retrieval_text` stay the small "child" excerpt used for indexing and
    citation; consumers that want to inject a bigger context window into the
    generation prompt should prefer this field over `text` when it is set.
    Not consumed anywhere yet — left for the generation/citation owner to wire.
    """
    mrl_vector_128: list[float] | None = None
    """Matryoshka (MRL) truncated-dimension embedding of `retrieval_text`.

    Populated by enrichment.py when MRL is enabled. Intended for a future
    two-stage retrieval (coarse filter on this vector, rerank on the full
    vector) — not consumed by search() yet; left for the retrieval owner.
    """


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
