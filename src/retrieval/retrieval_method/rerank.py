from __future__ import annotations

from typing import Any
from domain.schemas import SearchHit


def apply_reranker(
    hits: list[SearchHit],
    query: str,
    reranker: Any,
    limit: int,
) -> list[SearchHit]:
    """
    Áp dụng Cross-Encoder Reranker để re-score danh sách candidates.
    """
    if not hits or reranker is None:
        return hits[:limit]
    try:
        return reranker.rerank(query, hits, limit=limit)
    except Exception:
        return hits[:limit]
