from __future__ import annotations

import re
from dataclasses import dataclass
from hashlib import sha256

from domain.schemas import Chunk, Document
from ingestion.structure import extract_legal_sections
from providers.base import EmbeddingProvider

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+")


@dataclass(frozen=True)
class ChunkingConfig:
    """Feature flags for Level 1 chunking upgrades. All default to the legacy behavior."""

    max_chars: int = 1200
    semantic_enabled: bool = False
    semantic_threshold: float = 0.85
    embedder: EmbeddingProvider | None = None
    parent_child_enabled: bool = False
    parent_max_chars: int = 6000


def chunk_document(
    document: Document,
    text: str,
    max_chars: int = 1200,
    *,
    config: ChunkingConfig | None = None,
) -> list[Chunk]:
    resolved = config if config is not None else ChunkingConfig(max_chars=max_chars)
    canonical_doc_id = document.metadata.get("canonical_doc_id", document.source_name)
    output: list[Chunk] = []
    for section_index, legal_section in enumerate(extract_legal_sections(text, canonical_doc_id)):
        pieces = _split_section(legal_section.text, resolved)
        parent_text = _parent_text_for(legal_section.text, pieces, resolved)
        # Version-scoped so a re-ingest at v2 never collides with v1 families.
        parent_id = f"{document.id}:v{document.version}:p{section_index}"
        for child_index, piece in enumerate(pieces):
            position = len(output)
            chunk_hash = sha256(piece.encode("utf-8")).hexdigest()
            output.append(
                Chunk(
                    id=f"{document.id}:v{document.version}:{position}",
                    document_id=document.id,
                    version=document.version,
                    text=piece,
                    content_hash=chunk_hash,
                    source_name=document.source_name,
                    mime_type=document.mime_type,
                    status=document.status,
                    section=legal_section.heading,
                    position=position,
                    coordinates=legal_section.coordinates,
                    parent_id=parent_id,
                    parent_child_count=len(pieces),
                    child_index=child_index,
                    parent_text=parent_text if parent_text != piece else None,
                )
            )
    return output


def _split_section(text: str, config: ChunkingConfig) -> list[str]:
    if config.semantic_enabled and config.embedder is not None:
        return _semantic_split(text, config.max_chars, config.embedder, config.semantic_threshold)
    return _split(text, config.max_chars)


def _parent_text_for(section_text: str, pieces: list[str], config: ChunkingConfig) -> str | None:
    """Larger surrounding window for Parent-Child chunking (roadmap Level 1 #1).

    The parent is the whole legal section (capped at `parent_max_chars`), so a
    consumer can inject more context than the small indexed child chunk without
    a separate Chunk/index entry. Only meaningful when the section actually
    contains more text than a single child piece.
    """
    if not config.parent_child_enabled or len(pieces) < 1:
        return None
    source = section_text.strip()
    if not source or len(source) <= len(pieces[0]):
        return None
    return source[: config.parent_max_chars]


def _split(text: str, max_chars: int) -> list[str]:
    """Return contiguous slices whose concatenation exactly equals text.strip()."""
    source = text.strip()
    if not source:
        return []
    pieces: list[str] = []
    cursor = 0
    while len(source) - cursor > max_chars:
        window = source[cursor : cursor + max_chars]
        minimum = max_chars // 2
        split_at = max_chars
        for separator in ("\n\n", "\n", " "):
            candidate = window.rfind(separator)
            if candidate >= minimum:
                split_at = candidate + len(separator)
                break
        pieces.append(source[cursor : cursor + split_at])
        cursor += split_at
    pieces.append(source[cursor:])
    return pieces


def _semantic_split(
    text: str, max_chars: int, embedder: EmbeddingProvider, threshold: float
) -> list[str]:
    """Cắt theo ranh giới đổi chủ đề: cosine similarity giữa câu liên tiếp.

    Sentence "spans" are exact contiguous slices of `source` (including their
    trailing separator whitespace), never rejoined with a synthesized
    separator -- so, like `_split`, concatenating the output always
    reconstructs `text.strip()` exactly. This matters: golden-set evaluation
    validates that ordered chunk text can be losslessly reassembled per legal
    article, so silently normalizing whitespace between sentences would
    corrupt citations.

    Falls back to the char-window `_split` when there's nothing to compare
    (no sentence boundary found) and always re-splits any oversized piece with
    `_split` so `max_chars` stays a hard ceiling regardless of sentence length.
    """
    source = text.strip()
    if not source:
        return []
    boundaries = list(_SENTENCE_SPLIT_RE.finditer(source))
    if not boundaries:
        return _split(source, max_chars)

    spans: list[str] = []
    cursor = 0
    for match in boundaries:
        spans.append(source[cursor : match.end()])
        cursor = match.end()
    spans.append(source[cursor:])

    vectors = embedder.embed_documents([span.strip() for span in spans])
    pieces: list[str] = []
    current = spans[0]
    for index in range(1, len(spans)):
        similarity = _cosine_similarity(vectors[index - 1], vectors[index])
        candidate = current + spans[index]
        topic_boundary = similarity < threshold and len(current) >= max_chars // 2
        if topic_boundary or len(candidate) > max_chars:
            pieces.append(current)
            current = spans[index]
        else:
            current = candidate
    if current:
        pieces.append(current)

    final: list[str] = []
    for piece in pieces:
        if len(piece) > max_chars:
            final.extend(_split(piece, max_chars))
        else:
            final.append(piece)
    return final


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return float(dot / (norm_a * norm_b))
