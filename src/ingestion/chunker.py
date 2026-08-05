from __future__ import annotations

from hashlib import sha256

from domain.schemas import Chunk, Document
from ingestion.structure import extract_legal_sections


def chunk_document(document: Document, text: str, max_chars: int = 1200) -> list[Chunk]:
    canonical_doc_id = document.metadata.get("canonical_doc_id", document.source_name)
    output: list[Chunk] = []
    for legal_section in extract_legal_sections(text, canonical_doc_id):
        for piece in _split(legal_section.text, max_chars):
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
                )
            )
    return output


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
