from evaluation.runner import GoldenCase, score_response


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


def test_golden_case_parses_single_source_alias() -> None:
    raw_case = {
        "question": "Văn bản về đăng ký doanh nghiệp này quy định những phạm vi và nội dung gì?",
        "answer": "Nghị định này quy định...",
        "source": "01_2021_ND-CP_283247.md",
    }
    case = GoldenCase.model_validate(raw_case)
    assert case.question == raw_case["question"]
    assert case.expected_sources == {"01_2021_ND-CP_283247.md"}
    assert case.expected_answer == "Nghị định này quy định..."
    assert case.should_abstain is False


def test_golden_case_parses_negative_abstention_case() -> None:
    raw_case = {
        "question": "Chính sách thưởng Tết năm 2026 của công ty được quy định như thế nào?",
        "answer": "Không tìm thấy thông tin phù hợp trong tài liệu được phép truy cập.",
        "source": "",
        "should_abstain": True,
        "category": "negative",
    }
    case = GoldenCase.model_validate(raw_case)
    assert case.should_abstain is True
    assert case.category == "negative"
    assert case.expected_sources == set()
    assert case.expected_answer == "Không tìm thấy thông tin phù hợp trong tài liệu được phép truy cập."


def test_golden_case_uses_type_and_metadata_for_evaluation_defaults() -> None:
    case = GoldenCase.model_validate(
        {
            "question": "Thuế GTGT là bao nhiêu?",
            "type": "unanswerable",
            "expected_answer": "Không có thông tin trong tài liệu.",
            "gold_metadata": {"doc_id": "01_2021_ND-CP_283247.md"},
        }
    )

    assert case.category == "unanswerable"
    assert case.should_abstain is True
    assert case.expected_sources == set()
