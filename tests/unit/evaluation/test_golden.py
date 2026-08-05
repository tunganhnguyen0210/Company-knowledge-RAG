from pathlib import Path

import pytest
from pydantic import ValidationError

from evaluation.golden import TYPE_PREFIXES, GoldenCase, GoldenType, load_golden_dataset, select_cases


def test_loads_finalized_authoritative_dataset() -> None:
    dataset = load_golden_dataset(Path("evaluation/golden_set"))

    assert len(dataset.cases) == 100
    assert {case.type for case in dataset.cases} == set(GoldenType)
    assert {case.id for case in dataset.cases if case.type is GoldenType.DIRECT_LOOKUP} == {
        f"DL-{index:03d}" for index in range(1, 21)
    }
    for kind, prefix in TYPE_PREFIXES.items():
        assert {case.id for case in dataset.cases if case.type is kind} == {
            f"{prefix}-{index:03d}" for index in range(1, 21)
        }


def test_unanswerable_rejects_non_empty_contexts() -> None:
    with pytest.raises(ValidationError, match="unanswerable contexts must be empty"):
        GoldenCase.model_validate(
            {
                "id": "UA-001",
                "type": "unanswerable",
                "question": "Ngoài phạm vi?",
                "expected_answer": "Không có thông tin.",
                "golden_truth_contexts": [
                    {
                        "golden_truth_context": "evidence",
                        "golden_metadata": {
                            "doc_id": "01_2021_ND-CP_283247.md",
                            "chapter": "Chương I",
                            "article": "Điều 1",
                        },
                    }
                ],
                "difficulty": "easy",
            }
        )


def test_limit_round_robins_across_selected_types() -> None:
    dataset = load_golden_dataset(Path("evaluation/golden_set"))

    selected = select_cases(dataset, question_types=None, case_ids=None, limit=10)

    counts = {kind: sum(case.type is kind for case in selected) for kind in GoldenType}
    assert counts == {kind: 2 for kind in GoldenType}


def test_case_ids_must_exist_inside_type_filter() -> None:
    dataset = load_golden_dataset(Path("evaluation/golden_set"))

    with pytest.raises(ValueError, match="outside selected scope"):
        select_cases(
            dataset,
            question_types={GoldenType.DIRECT_LOOKUP},
            case_ids={"MH-001"},
            limit=None,
        )
