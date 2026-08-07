from __future__ import annotations

import math
from domain.schemas import SearchHit


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b, strict=True))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def maximal_marginal_relevance(
    hits: list[SearchHit],
    chunk_vectors: dict[str, list[float]],
    lambda_param: float = 0.7,
    top_n: int = 5,
) -> list[SearchHit]:
    """
    Maximal Marginal Relevance (MMR) diversification.
    MMR = argmax_{d in R\\S} [lambda * Sim1(d,q) - (1-lambda) * max_{dj in S} Sim2(d,dj)]
    """
    if not hits or top_n <= 0:
        return []
    if len(hits) <= top_n:
        return hits
    if not chunk_vectors:
        return hits[:top_n]

    # Normalize relevance scores to [0, 1]
    scores = [hit.score for hit in hits]
    min_s, max_s = min(scores), max(scores)
    range_s = max_s - min_s if max_s > min_s else 1.0

    def norm_score(h: SearchHit) -> float:
        return (h.score - min_s) / range_s

    unselected = list(hits)
    selected: list[SearchHit] = []

    while unselected and len(selected) < top_n:
        best_hit: SearchHit | None = None
        best_mmr_score = -float("inf")

        for candidate in unselected:
            cand_vector = chunk_vectors.get(candidate.chunk.id)
            rel = norm_score(candidate)

            if not selected or cand_vector is None:
                max_sim = 0.0
            else:
                sims: list[float] = []
                for sel in selected:
                    sel_vector = chunk_vectors.get(sel.chunk.id)
                    if sel_vector is not None:
                        sims.append(cosine_similarity(cand_vector, sel_vector))
                max_sim = max(sims) if sims else 0.0

            mmr_val = lambda_param * rel - (1.0 - lambda_param) * max_sim

            if mmr_val > best_mmr_score:
                best_mmr_score = mmr_val
                best_hit = candidate

        if best_hit is None:
            break

        selected.append(best_hit)
        unselected.remove(best_hit)

    return selected
