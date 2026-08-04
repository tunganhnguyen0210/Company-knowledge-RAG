from __future__ import annotations

import re

from domain.schemas import Chunk, DocumentStatus, Principal, SearchHit


class MemoryChunkStore:
    def __init__(self) -> None:
        self.all_chunks: list[Chunk] = []

    def replace_document(self, document_id: str, chunks: list[Chunk]) -> None:
        self.all_chunks = [chunk for chunk in self.all_chunks if chunk.document_id != document_id]
        self.all_chunks.extend(chunks)

    def search(self, query: str, principal: Principal | None = None, limit: int = 5) -> list[SearchHit]:
        query_tokens = _tokens(query)
        authorized = [
            chunk
            for chunk in self.all_chunks
            if chunk.status is DocumentStatus.READY
        ]
        scored = [
            SearchHit(chunk=chunk, score=_score(query_tokens, _tokens(chunk.text)))
            for chunk in authorized
        ]
        return sorted(scored, key=lambda hit: (-hit.score, hit.chunk.id))[:limit]

    def ready(self) -> bool:
        return True


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"\w+", text.casefold()))


def _score(query: set[str], document: set[str]) -> float:
    if not query or not document:
        return 0.0
    return len(query & document) / len(query)

