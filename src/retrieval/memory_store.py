from __future__ import annotations

import re

from domain.schemas import Chunk, DocumentStatus, SearchHit
from retrieval.hierarchical import DEFAULT_EXPANSION, ExpansionConfig, expand_with_siblings


class MemoryChunkStore:
    def __init__(self, expansion: ExpansionConfig = DEFAULT_EXPANSION) -> None:
        self.all_chunks: list[Chunk] = []
        self.expansion = expansion

    def replace_document(self, document_id: str, chunks: list[Chunk]) -> None:
        self.all_chunks = [chunk for chunk in self.all_chunks if chunk.document_id != document_id]
        self.all_chunks.extend(chunks)

    def search(self, query: str, limit: int = 5) -> list[SearchHit]:
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
        ranked = sorted(scored, key=lambda hit: (-hit.score, hit.chunk.id))
        return expand_with_siblings(
            ranked[:limit],
            sibling_pool=authorized,
            ranking_pool=ranked[: max(limit * 4, limit)],
            config=self.expansion,
        )

    def list_document_chunks(
        self,
        document_id: str,
        version: int | None = None,
    ) -> list[Chunk]:
        return sorted(
            (
                chunk
                for chunk in self.all_chunks
                if chunk.document_id == document_id
                and (version is None or chunk.version == version)
            ),
            key=lambda chunk: chunk.position,
        )

    def list_indexed_documents(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for chunk in self.all_chunks:
            counts[chunk.document_id] = counts.get(chunk.document_id, 0) + 1
        return counts

    def purge_documents(self, document_ids: list[str]) -> int:
        targets = set(document_ids)
        before = len(self.all_chunks)
        self.all_chunks = [chunk for chunk in self.all_chunks if chunk.document_id not in targets]
        return before - len(self.all_chunks)

    def ready(self) -> bool:
        return True


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"\w+", text.casefold()))


def _score(query: set[str], document: set[str]) -> float:
    if not query or not document:
        return 0.0
    return len(query & document) / len(query)

