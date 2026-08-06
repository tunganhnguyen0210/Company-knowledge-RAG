from pathlib import Path

import pytest

from evaluation.artifacts import (
    EvaluationMode,
    EvaluationReport,
    EvaluationRequest,
    IndexSnapshot,
    RunManifest,
    artifact_fingerprint,
    fingerprint,
)
from evaluation.repository import InMemoryRunRepository, LocalRunRepository
from tests.support.evaluation_fakes import make_generation_run, make_retrieval_run


def test_fingerprint_is_stable_across_dictionary_order() -> None:
    assert fingerprint({"a": 1, "b": 2}) == fingerprint({"b": 2, "a": 1})


def test_local_repository_round_trips_retrieval_run(tmp_path: Path) -> None:
    repository = LocalRunRepository(tmp_path)
    run = make_retrieval_run(run_id="retrieval-1")

    repository.save_retrieval(run)

    assert repository.load_retrieval("retrieval-1") == run


def test_baseline_candidate_requires_authoritative_dataset_and_canonical_paths() -> None:
    authoritative = EvaluationRequest(mode=EvaluationMode.E2E)
    assert authoritative.baseline_candidate is True
    assert (
        authoritative.model_copy(update={"golden_dir": Path("tmp/golden")}).baseline_candidate
        is False
    )
    assert (
        authoritative.model_copy(
            update={"canonical_source": Path("tmp/canonical.md")}
        ).baseline_candidate
        is False
    )


def _write_once_cases() -> list[tuple[str, object, str]]:
    retrieval = make_retrieval_run(run_id="once")
    return [
        ("manifest.json", RunManifest.model_construct(run_id="once"), "save_manifest"),
        (
            "index_snapshot.json",
            IndexSnapshot.model_construct(run_id="once"),
            "save_snapshot",
        ),
        ("retrieval.jsonl", retrieval, "save_retrieval"),
        (
            "generation.jsonl",
            make_generation_run(retrieval=retrieval).model_copy(update={"run_id": "once"}),
            "save_generation",
        ),
        ("report.json", EvaluationReport.model_construct(run_id="once"), "save_report"),
    ]


@pytest.mark.parametrize(("filename", "artifact", "method"), _write_once_cases())
def test_local_repository_rejects_duplicate_artifact_saves_without_rewrite(
    tmp_path: Path,
    filename: str,
    artifact: object,
    method: str,
) -> None:
    repository = LocalRunRepository(tmp_path)
    save = getattr(repository, method)
    save(artifact)
    destination = tmp_path / "once" / filename
    original = destination.read_bytes()

    with pytest.raises(FileExistsError):
        save(artifact)

    assert destination.read_bytes() == original


@pytest.mark.parametrize(("_filename", "artifact", "method"), _write_once_cases())
def test_memory_repository_rejects_duplicate_artifact_saves(
    _filename: str,
    artifact: object,
    method: str,
) -> None:
    repository = InMemoryRunRepository()
    save = getattr(repository, method)
    save(artifact)

    with pytest.raises(FileExistsError):
        save(artifact)


def test_limited_request_is_not_baseline_eligible() -> None:
    request = EvaluationRequest(mode=EvaluationMode.E2E, limit=10)
    assert request.baseline_candidate is False


def test_artifact_fingerprint_excludes_run_identity_and_timestamp() -> None:
    first = make_retrieval_run(run_id="run-a")
    second = make_retrieval_run(run_id="run-b")

    assert artifact_fingerprint(first) == artifact_fingerprint(second)


def test_artifact_fingerprint_excludes_nested_execution_volatiles() -> None:
    first = make_retrieval_run()
    source_case = first.cases[0]
    assert source_case.retrieval is not None
    changed = source_case.retrieval.model_copy(
        update={"request_id": "different-request", "latency_ms": 999.0}
    )
    second = first.model_copy(
        update={"cases": [source_case.model_copy(update={"retrieval": changed})]}
    )
    assert artifact_fingerprint(first) == artifact_fingerprint(second)


def test_ragas_is_off_by_default() -> None:
    assert EvaluationRequest(mode=EvaluationMode.E2E).run_ragas is False
