from __future__ import annotations

import re

from rank_bm25 import BM25Okapi  # type: ignore[import-untyped]

from domain.schemas import Chunk, SearchHit


def filter_by_min_score(hits: list[SearchHit], min_score: float) -> list[SearchHit]:
    return [hit for hit in hits if hit.score >= min_score]


def lexical_rank(query: str, chunks: list[Chunk], limit: int) -> list[SearchHit]:
    if not chunks:
        return []
    tokenized = [_tokens(chunk.retrieval_text or chunk.text) for chunk in chunks]
    scores = BM25Okapi(tokenized).get_scores(_tokens(query))
    ranked = sorted(
        (SearchHit(chunk=chunk, score=float(score)) for chunk, score in zip(chunks, scores, strict=True)),
        key=lambda hit: (-hit.score, hit.chunk.id),
    )
    return [hit for hit in ranked if hit.score > 0][:limit]


def reciprocal_rank_fusion(
    dense: list[SearchHit],
    lexical: list[SearchHit],
    limit: int,
    rank_constant: int = 60,
) -> list[SearchHit]:
    by_id: dict[str, Chunk] = {}
    scores: dict[str, float] = {}
    for ranking in (dense, lexical):
        for rank, hit in enumerate(ranking, start=1):
            by_id[hit.chunk.id] = hit.chunk
            scores[hit.chunk.id] = scores.get(hit.chunk.id, 0.0) + 1.0 / (rank_constant + rank)
    ordered = sorted(scores, key=lambda chunk_id: (-scores[chunk_id], chunk_id))[:limit]
    return [SearchHit(chunk=by_id[chunk_id], score=scores[chunk_id]) for chunk_id in ordered]


def _tokens(text: str) -> list[str]:
    return re.findall(r"\w+", text.casefold())
