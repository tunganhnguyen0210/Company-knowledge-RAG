from __future__ import annotations

import re
from hashlib import sha256

from domain.schemas import Chunk, Document


def chunk_document(document: Document, text: str, max_chars: int = 1200) -> list[Chunk]:
    sections = _sections(text)
    output: list[Chunk] = []
    for section, body in sections:
        for piece in _split(body, max_chars):
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
                    section=section,
                    position=position,
                )
            )
    return output


def _sections(text: str) -> list[tuple[str | None, str]]:
    matches = list(re.finditer(r"(?m)^#{1,6}\s+(.+)$", text))
    if not matches:
        return [(None, text.strip())] if text.strip() else []
    sections: list[tuple[str | None, str]] = []
    prefix = text[: matches[0].start()].strip()
    if prefix:
        sections.append((None, prefix))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[match.end() : end].strip()
        if body:
            sections.append((match.group(1).strip(), body))
    return sections


def _split(text: str, max_chars: int) -> list[str]:
    paragraphs = [part.strip() for part in re.split(r"\n{2,}", text) if part.strip()]
    pieces: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if current and len(current) + len(paragraph) + 2 > max_chars:
            pieces.append(current)
            current = ""
        if len(paragraph) > max_chars:
            if current:
                pieces.append(current)
                current = ""
            pieces.extend(paragraph[start : start + max_chars] for start in range(0, len(paragraph), max_chars))
        else:
            current = f"{current}\n\n{paragraph}" if current else paragraph
    if current:
        pieces.append(current)
    return pieces

