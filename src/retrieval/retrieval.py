from __future__ import annotations

from typing import Any
from domain.schemas import SearchHit
from providers.base import GenerationProvider
from retrieval.base import ChunkStore
from retrieval.retrieval_method import (
    QueryTransformer,
    apply_reranker,
    filter_by_min_score,
    lexical_rank,
    maximal_marginal_relevance,
    mrl_rescore,
    reciprocal_rank_fusion,
)


class UnifiedRetriever:
    """
    Module chung tập hợp tất cả các phương pháp Retrieval từ folder retrieval_method.
    Cho phép bật/tắt linh hoạt các kỹ thuật (Reranker, MMR, HyDE, Multi-Query, MRL) qua flags.
    """

    def __init__(
        self,
        store: ChunkStore,
        provider: GenerationProvider | None = None,
        reranker: Any | None = None,
        enable_mmr: bool = False,
        mmr_lambda: float = 0.7,
        enable_mrl: bool = False,
        mrl_fast_dim: int = 128,
        query_transform_mode: str = "none",  # "none" | "hyde" | "multi_query"
        multi_query_n: int = 3,
    ) -> None:
        self.store = store
        self.provider = provider
        self.reranker = reranker
        self.enable_mmr = enable_mmr
        self.mmr_lambda = mmr_lambda
        self.enable_mrl = enable_mrl
        self.mrl_fast_dim = mrl_fast_dim
        self.query_transform_mode = query_transform_mode
        self.multi_query_n = multi_query_n
        self.query_transformer = QueryTransformer() if query_transform_mode != "none" else None

    def search(self, query: str, limit: int = 5) -> list[SearchHit]:
        """
        Quy trình Retrieval tổng hợp:
        1. Query Transformation (Multi-Query Expansion / HyDE) nếu bật
        2. Candidate Search từ Vector Store (Dense + BM25 Hybrid)
        3. Re-scoring bằng Reranker nếu bật
        4. Diversification bằng MMR nếu bật
        """
        # Step 1: Query Transformation
        if self.query_transformer and self.provider:
            if self.query_transform_mode == "multi_query":
                queries = self.query_transformer.expand(query, self.provider, n=self.multi_query_n)
                all_hits: list[SearchHit] = []
                for q in queries:
                    all_hits.extend(self.store.search(q, limit=limit * 2))
                seen: dict[str, SearchHit] = {}
                for hit in all_hits:
                    if hit.chunk.id not in seen or hit.score > seen[hit.chunk.id].score:
                        seen[hit.chunk.id] = hit
                hits = sorted(seen.values(), key=lambda h: -h.score)[: limit * 2]
            elif self.query_transform_mode == "hyde":
                hyde_doc = self.query_transformer.hyde(query, self.provider)
                hits_raw = self.store.search(query, limit=limit * 2)
                hits_hyde = self.store.search(hyde_doc, limit=limit * 2)
                hits = reciprocal_rank_fusion(hits_raw, hits_hyde, limit=limit * 2)
            else:
                hits = self.store.search(query, limit=limit * 2)
        else:
            hits = self.store.search(query, limit=limit * 2)

        # Step 2: Cross-Encoder Reranking
        if self.reranker:
            hits = apply_reranker(hits, query, self.reranker, limit=limit * 2)

        # Step 3: MMR Diversification
        if self.enable_mmr and len(hits) > limit:
            chunk_vectors: dict[str, list[float]] = {}
            if hasattr(self.store, "get_chunk_vectors"):
                chunk_vectors = self.store.get_chunk_vectors([h.chunk.id for h in hits])
            hits = maximal_marginal_relevance(
                hits, chunk_vectors, lambda_param=self.mmr_lambda, top_n=limit
            )
        else:
            hits = hits[:limit]

        return hits


__all__ = [
    "UnifiedRetriever",
    "filter_by_min_score",
    "lexical_rank",
    "reciprocal_rank_fusion",
    "maximal_marginal_relevance",
    "mrl_rescore",
    "QueryTransformer",
    "apply_reranker",
]
