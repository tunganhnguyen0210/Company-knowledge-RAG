from company_knowledge_rag.evaluation.runner import GoldenCase, score_response


def test_score_response_tracks_retrieval_citations_and_abstention() -> None:
    case = GoldenCase(
        question="Nghỉ phép bao nhiêu ngày?",
        expected_sources={"leave.md"},
        should_abstain=False,
        roles={"employee"},
    )

    scores = score_response(
        case,
        answer="Nhân viên được nghỉ 15 ngày [C1].",
        citation_sources={"leave.md"},
        retrieval_count=2,
        latency_ms=25.0,
    )

    assert scores.retrieval_hit == 1.0
    assert scores.citation_coverage == 1.0
    assert scores.abstention_accuracy == 1.0
    assert scores.latency_ms == 25.0


def test_score_response_rewards_correct_abstention() -> None:
    case = GoldenCase(
        question="Thông tin không tồn tại?",
        expected_sources=set(),
        should_abstain=True,
        roles={"employee"},
    )

    scores = score_response(
        case,
        answer="Không tìm thấy thông tin phù hợp trong tài liệu được phép truy cập.",
        citation_sources=set(),
        retrieval_count=3,
        latency_ms=3.0,
    )

    assert scores.abstention_accuracy == 1.0
    assert scores.groundedness == 1.0
    assert scores.retrieval_hit == 0.0
