from domain.schemas import Chunk, DocumentStatus, SearchHit
from retrieval.hybrid import filter_by_min_score, reciprocal_rank_fusion


def _hit(chunk_id: str, score: float) -> SearchHit:
    return SearchHit(
        chunk=Chunk(
            id=chunk_id,
            document_id=chunk_id,
            version=1,
            text=chunk_id,
            content_hash=chunk_id,
            source_name=f"{chunk_id}.md",
            mime_type="text/markdown",
            status=DocumentStatus.READY,
        ),
        score=score,
    )


def test_rrf_promotes_results_found_by_dense_and_lexical_search() -> None:
    dense = [_hit("dense-only", 0.9), _hit("both", 0.8)]
    lexical = [_hit("both", 10.0), _hit("lexical-only", 8.0)]

    fused = reciprocal_rank_fusion(dense, lexical, limit=3)

    assert fused[0].chunk.id == "both"
    assert {hit.chunk.id for hit in fused} == {"both", "dense-only", "lexical-only"}


def test_dense_relevance_gate_removes_weak_candidates() -> None:
    results = filter_by_min_score([_hit("weak", 0.2), _hit("strong", 0.8)], 0.35)

    assert [hit.chunk.id for hit in results] == ["strong"]
