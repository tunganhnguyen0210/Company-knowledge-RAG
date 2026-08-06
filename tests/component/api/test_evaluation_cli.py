from __future__ import annotations

from pathlib import Path

import pytest

from evaluation.artifacts import EvaluationMode, EvaluationReport, EvaluationRequest
from evaluation.cli import CliRuntime, parse_request, run_cli
from evaluation.golden import GoldenType


class CompleteValidationRunner:
    def run(self, request: EvaluationRequest) -> EvaluationReport:
        return EvaluationReport(
            run_id="validate-1",
            mode=request.mode,
            status="complete",
            dataset_size=100,
            evaluated_cases=0,
            validation={},
            aggregates={},
            errors=[],
            artifact_ids={},
            baseline_eligible=False,
            report_path=Path("reports/rag_evaluation/validate-1/report.json"),
        )


def _validation_runner_factory():
    return lambda request, settings, repository: CliRuntime(
        runner=CompleteValidationRunner(),
        flush=None,
    )


def test_type_and_limit_map_to_request() -> None:
    request = parse_request(["retrieval", "--type", "multi_hop", "--limit", "10"])
    assert request.mode is EvaluationMode.RETRIEVAL
    assert request.question_types == {GoldenType.MULTI_HOP}
    assert request.limit == 10


def test_type_and_explicit_file_are_mutually_exclusive() -> None:
    with pytest.raises(SystemExit):
        parse_request(
            [
                "retrieval",
                "--type",
                "multi_hop",
                "--golden-file",
                "evaluation/experiment.json",
            ]
        )


def test_force_requires_ingestion_source() -> None:
    with pytest.raises(SystemExit):
        parse_request(["e2e", "--force-reingest"])


def test_ragas_is_explicit_opt_in() -> None:
    without_judge = parse_request(["e2e", "--limit", "5"])
    with_judge = parse_request(["e2e", "--limit", "5", "--ragas"])

    assert without_judge.run_ragas is False
    assert with_judge.run_ragas is True


def test_output_root_is_a_subcommand_option() -> None:
    request = parse_request(["retrieval", "--output-root", "tmp/eval"])
    assert request.output_root == Path("tmp/eval")


def test_generation_rejects_new_selection_flags() -> None:
    with pytest.raises(SystemExit):
        parse_request(["generation", "--from-run", "retrieval-1", "--type", "multi_hop"])


def test_generation_parser_omits_inherited_selection_fields() -> None:
    request = parse_request(["generation", "--from-run", "retrieval-1"])

    assert request.mode is EvaluationMode.GENERATION
    assert request.from_run == "retrieval-1"


def test_validate_rejects_limit_because_standard_validation_is_always_full() -> None:
    with pytest.raises(SystemExit):
        parse_request(["validate", "--limit", "1"])


def test_validate_does_not_create_fastapi_runtime(monkeypatch) -> None:
    monkeypatch.setattr(
        "evaluation.cli.create_app",
        lambda settings: (_ for _ in ()).throw(AssertionError("runtime created")),
    )
    assert run_cli(["validate"], runner_factory=_validation_runner_factory()) == 0
