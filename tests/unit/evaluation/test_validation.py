import json
from pathlib import Path

import pytest

from evaluation.golden import (
    Difficulty,
    GoldenCase,
    GoldenContext,
    GoldenDataset,
    GoldenMetadata,
    GoldenType,
    load_golden_dataset,
    validate_golden_dataset,
)


def _single_case_dataset(*, context: str, chapter: str, article: str) -> GoldenDataset:
    return GoldenDataset(
        cases=[
            GoldenCase(
                id="DL-001",
                type=GoldenType.DIRECT_LOOKUP,
                question="Question",
                expected_answer="Answer",
                golden_truth_contexts=[
                    GoldenContext(
                        golden_truth_context=context,
                        golden_metadata=GoldenMetadata(
                            doc_id="law.md",
                            chapter=chapter,
                            article=article,
                        ),
                    )
                ],
                difficulty=Difficulty.EASY,
            )
        ],
        source_files=["test.json"],
        scope="partial",
    )


def test_finalized_dataset_is_exactly_grounded() -> None:
    dataset = load_golden_dataset(Path("evaluation/golden_set"))
    report = validate_golden_dataset(
        dataset,
        canonical_path=Path("data/extracted/01_2021_ND-CP_283247.md"),
        chunks=None,
        audit_root=Path("evaluation"),
    )

    assert report.errors == []
    assert report.warnings == []
    assert report.full_conformance is True


def test_context_in_wrong_article_is_rejected(tmp_path: Path) -> None:
    canonical = tmp_path / "law.md"
    canonical.write_text("# Chương I\n\n### Điều 1. A\n\nBằng chứng", encoding="utf-8")
    dataset = _single_case_dataset(
        context="Bằng chứng",
        chapter="Chương I",
        article="Điều 2",
    )

    report = validate_golden_dataset(dataset, canonical, chunks=None, audit_root=tmp_path)

    assert [issue.code for issue in report.errors] == ["context_coordinate_mismatch"]


def _copy_audits(tmp_path: Path) -> None:
    for filename in ("id_migration_map.json", "golden_set_grounding_review.json"):
        (tmp_path / filename).write_bytes((Path("evaluation") / filename).read_bytes())


@pytest.mark.parametrize(
    ("filename", "warning_code", "path", "value", "remove"),
    [
        (
            "id_migration_map.json",
            "invalid_id_migration_map",
            ("migration_commit",),
            "wrong",
            False,
        ),
        (
            "id_migration_map.json",
            "invalid_id_migration_map",
            ("old_to_new", "61"),
            "DL-999",
            False,
        ),
        (
            "id_migration_map.json",
            "invalid_id_migration_map",
            ("old_to_new", "61"),
            None,
            True,
        ),
        (
            "id_migration_map.json",
            "invalid_id_migration_map",
            ("retired", 0, "status"),
            "active",
            False,
        ),
        (
            "golden_set_grounding_review.json",
            "invalid_grounding_review",
            ("cases", 0, "case_id"),
            "DL-999",
            False,
        ),
        (
            "golden_set_grounding_review.json",
            "invalid_grounding_review",
            ("cases", 0, "status"),
            "failed",
            False,
        ),
        (
            "golden_set_grounding_review.json",
            "invalid_grounding_review",
            ("cases", 0, "contexts", 0, "context_index"),
            99,
            False,
        ),
        (
            "golden_set_grounding_review.json",
            "invalid_grounding_review",
            ("canonical_sha256",),
            "0" * 64,
            False,
        ),
        (
            "golden_set_grounding_review.json",
            "invalid_grounding_review",
            ("dataset_sha256",),
            "0" * 64,
            False,
        ),
        (
            "golden_set_grounding_review.json",
            "invalid_grounding_review",
            ("cases", 0, "contexts", 0, "context_sha256"),
            "0" * 64,
            False,
        ),
    ],
    ids=[
        "migration-commit",
        "migration-mapping",
        "migration-completeness",
        "retired-record",
        "grounding-case-id",
        "grounding-case-status",
        "grounding-context-index",
        "grounding-canonical-hash",
        "grounding-dataset-hash",
        "grounding-context-hash",
    ],
)
def test_each_audit_evidence_field_is_validated_independently(
    tmp_path: Path,
    filename: str,
    warning_code: str,
    path: tuple[str | int, ...],
    value: object,
    remove: bool,
) -> None:
    _copy_audits(tmp_path)
    artifact_path = tmp_path / filename
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    target = artifact
    for segment in path[:-1]:
        target = target[segment]
    if remove:
        del target[path[-1]]
    else:
        target[path[-1]] = value
    artifact_path.write_text(json.dumps(artifact, ensure_ascii=False), encoding="utf-8")

    report = validate_golden_dataset(
        load_golden_dataset(Path("evaluation/golden_set")),
        Path("data/extracted/01_2021_ND-CP_283247.md"),
        chunks=None,
        audit_root=tmp_path,
    )

    assert warning_code in {warning.code for warning in report.warnings}
    assert report.full_conformance is False
