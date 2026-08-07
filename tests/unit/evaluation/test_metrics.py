from domain.schemas import Chunk, DocumentStatus, SearchHit, SourceCoordinates
from evaluation.golden import (
    Difficulty,
    GoldenCase,
    GoldenContext,
    GoldenMetadata,
    GoldenType,
)
from evaluation.metrics import (
    compare_to_target,
    percentile_95,
    score_generation_case,
    score_retrieval_case,
    segment_aggregates,
)


def _context(article: str, text: str) -> GoldenContext:
    return GoldenContext(
        golden_truth_context=text,
        golden_metadata=GoldenMetadata(
            doc_id="law.md",
            chapter="Chương I",
            article=article,
        ),
    )


def _case(case_id: str, kind: GoldenType, contexts: list[GoldenContext]) -> GoldenCase:
    return GoldenCase(
        id=case_id,
        type=kind,
        question="Question",
        expected_answer="Answer",
        golden_truth_contexts=contexts,
        difficulty=Difficulty.EASY,
    )


def _multi_hop_case_with_articles(first: str, second: str) -> GoldenCase:
    return _case(
        "MH-001",
        GoldenType.MULTI_HOP,
        [_context(first, "first evidence"), _context(second, "second evidence")],
    )


def _unanswerable_case() -> GoldenCase:
    return _case("UA-001", GoldenType.UNANSWERABLE, [])


def _direct_case() -> GoldenCase:
    return _case("DL-001", GoldenType.DIRECT_LOOKUP, [_context("Điều 1", "evidence")])


def _hit(*, article: str, text: str) -> SearchHit:
    return SearchHit(
        chunk=Chunk(
            id=f"chunk-{article}",
            document_id="document-1",
            version=1,
            text=text,
            content_hash=f"hash-{article}",
            source_name="law.docx",
            mime_type="application/docx",
            status=DocumentStatus.READY,
            position=0,
            coordinates=SourceCoordinates(doc_id="law.md", chapter="Chương I", article=article),
        ),
        score=0.9,
    )


def test_multi_hop_coordinate_recall_requires_every_unique_coordinate() -> None:
    case = _multi_hop_case_with_articles("Điều 1", "Điều 2")
    hits = [_hit(article="Điều 1", text="first evidence")]

    scores = score_retrieval_case(case, hits)

    assert scores["coordinate_recall"] == 0.5


def test_unanswerable_is_excluded_from_retrieval_recall() -> None:
    assert score_retrieval_case(_unanswerable_case(), []) == {
        "coordinate_recall": None,
        "evidence_recall": None,
    }


def test_invalid_citation_is_detected() -> None:
    scores = score_generation_case(
        _direct_case(),
        answer="Trả lời [C1].",
        cited_chunk_ids={"not-retrieved"},
        retrieved_chunk_ids={"retrieved"},
        retrieval_latency_ms=10.0,
        generation_latency_ms=20.0,
    )
    assert scores["citation_validity"] == 0.0


def test_segment_aggregates_exclude_nulls_and_report_latency_p95() -> None:
    cases = [_direct_case(), _unanswerable_case()]
    rows = [
        {"coordinate_recall": 0.5, "retrieval_latency_ms": 10.0},
        {"coordinate_recall": None, "retrieval_latency_ms": 30.0},
    ]

    aggregates = segment_aggregates(cases, rows)

    assert aggregates["overall"]["coordinate_recall"] == 0.5
    assert aggregates["overall"]["retrieval_latency_ms_p95"] == 30.0
    assert percentile_95([10.0, 30.0]) == 30.0


def test_target_comparison_is_report_only_metadata() -> None:
    comparison = compare_to_target(
        {"overall": {"coordinate_recall": 0.84, "retrieval_latency_ms": 10.0}}
    )

    assert comparison == {
        "overall": {
            "coordinate_recall": {"target": 0.85, "meets_target": False}
        }
    }


def _sibling_hit(*, position: int, text: str) -> SearchHit:
    """Chunk of one shared article, distinguished only by position."""
    return SearchHit(
        chunk=Chunk(
            id=f"chunk-pos-{position}",
            document_id="document-1",
            version=1,
            text=text,
            content_hash=f"hash-{position}",
            source_name="law.docx",
            mime_type="application/docx",
            status=DocumentStatus.READY,
            position=position,
            coordinates=SourceCoordinates(doc_id="law.md", chapter="Chương I", article="Điều 1"),
        ),
        score=0.9,
    )


def test_evidence_split_across_siblings_is_recovered_only_when_family_is_complete() -> None:
    """Pins the premise of sibling expansion.

    The metric joins a coordinate's retrieved chunks with "".join, so a span
    straddling two chunks is recovered only if both are present -- this is what
    makes returning siblings worth anything.
    """
    case = _case("DL-002", GoldenType.DIRECT_LOOKUP, [_context("Điều 1", "phần đầu và phần cuối")])
    first = _sibling_hit(position=0, text="phần đầu ")
    second = _sibling_hit(position=1, text="và phần cuối")

    assert score_retrieval_case(case, [first])["evidence_recall"] == 0.0
    assert score_retrieval_case(case, [first, second])["evidence_recall"] == 1.0


def test_missing_middle_sibling_glues_text_and_never_matches() -> None:
    """Why expansion must be all-or-nothing: a gap silently fabricates text."""
    case = _case("DL-003", GoldenType.DIRECT_LOOKUP, [_context("Điều 1", "alpha beta gamma")])
    first = _sibling_hit(position=0, text="alpha ")
    middle = _sibling_hit(position=1, text="beta ")
    last = _sibling_hit(position=2, text="gamma")

    assert score_retrieval_case(case, [first, last])["evidence_recall"] == 0.0
    assert score_retrieval_case(case, [first, middle, last])["evidence_recall"] == 1.0
