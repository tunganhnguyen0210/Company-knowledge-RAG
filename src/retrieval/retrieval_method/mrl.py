from __future__ import annotations

from domain.schemas import SearchHit
from retrieval.retrieval_method.mmr import cosine_similarity


def mrl_rescore(
    candidates: list[SearchHit],
    candidate_vectors: dict[str, list[float]],
    full_query_vector: list[float],
    top_n: int,
) -> list[SearchHit]:
    """
    Stage-2 precise cosine re-score cho MRL.
    Nhận candidates từ Stage-1 (128-d fast filter), tính cosine similarity với full_query_vector (1024-d)
    và trả về top_n SearchHit có điểm cao nhất.
    """
    if not candidates or not candidate_vectors or not full_query_vector:
        return candidates[:top_n]

    rescored_hits: list[SearchHit] = []
    for hit in candidates:
        full_cand_vector = candidate_vectors.get(hit.chunk.id)
        if full_cand_vector is not None:
            new_score = cosine_similarity(full_query_vector, full_cand_vector)
            rescored_hits.append(SearchHit(chunk=hit.chunk, score=new_score))
        else:
            rescored_hits.append(hit)

    rescored_hits.sort(key=lambda h: -h.score)
    return rescored_hits[:top_n]
