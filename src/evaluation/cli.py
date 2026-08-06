from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from api.app import create_app
from evaluation.artifacts import EvaluationMode, EvaluationReport, EvaluationRequest
from evaluation.golden import GoldenType
from evaluation.repository import LocalRunRepository, RunRepository
from evaluation.runner import EvaluationRunner
from settings import Settings


def _add_selection(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--golden-dir", type=Path, default=Path("evaluation/golden_set"))
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--type", action="append", choices=[item.value for item in GoldenType], default=[]
    )
    group.add_argument("--golden-file", action="append", type=Path, default=[])
    parser.add_argument("--case-id", action="append", default=[])
    parser.add_argument("--limit", type=int)
    parser.add_argument(
        "--canonical-source",
        type=Path,
        default=Path("data/extracted/01_2021_ND-CP_283247.md"),
    )


def _add_validation_scope(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--golden-dir", type=Path, default=Path("evaluation/golden_set"))
    parser.add_argument("--golden-file", action="append", type=Path, default=[])
    parser.add_argument(
        "--canonical-source",
        type=Path,
        default=Path("data/extracted/01_2021_ND-CP_283247.md"),
    )


def _add_output(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--output-root", type=Path, default=Path("reports/rag_evaluation"))


def _add_ragas(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--ragas",
        action="store_true",
        help="Run report-only Ragas metrics using captured evidence",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rag-eval", description="Run staged offline RAG evaluation"
    )
    subparsers = parser.add_subparsers(dest="mode", required=True)

    validate = subparsers.add_parser("validate")
    _add_validation_scope(validate)
    _add_output(validate)

    retrieval = subparsers.add_parser("retrieval")
    _add_selection(retrieval)
    _add_ragas(retrieval)
    _add_output(retrieval)

    ingest = subparsers.add_parser("ingest")
    ingest.add_argument("--source", required=True, type=Path)
    ingest.add_argument(
        "--canonical-source",
        type=Path,
        default=Path("data/extracted/01_2021_ND-CP_283247.md"),
    )
    ingest.add_argument("--force-reingest", action="store_true")
    _add_output(ingest)

    generation = subparsers.add_parser("generation")
    generation.add_argument("--from-run", required=True)
    _add_ragas(generation)
    _add_output(generation)

    e2e = subparsers.add_parser("e2e")
    _add_selection(e2e)
    e2e.add_argument("--ingest", type=Path)
    e2e.add_argument("--force-reingest", action="store_true")
    _add_ragas(e2e)
    _add_output(e2e)
    return parser


def parse_request(argv: Sequence[str]) -> EvaluationRequest:
    parser = build_parser()
    values = vars(parser.parse_args(list(argv)))
    mode = EvaluationMode(values.pop("mode"))
    source = values.pop("source", None)
    e2e_ingest = values.pop("ingest", None)
    question_types = {GoldenType(value) for value in values.pop("type", [])}
    golden_files = values.pop("golden_file", [])
    case_ids = set(values.pop("case_id", []))
    request_values = {
        "mode": mode,
        "ingestion_source": source or e2e_ingest,
        "run_ragas": values.pop("ragas", False),
        **values,
    }
    if mode is not EvaluationMode.GENERATION:
        request_values.update(
            golden_files=golden_files,
            question_types=question_types,
            case_ids=case_ids,
        )
    try:
        return EvaluationRequest(**request_values)
    except ValidationError as exc:
        parser.error(str(exc))
        raise AssertionError("argparse.error always exits") from exc


@dataclass(frozen=True)
class CliRuntime:
    runner: EvaluationRunner
    flush: Callable[[], None] | None


RunnerFactory = Callable[[EvaluationRequest, Settings, RunRepository], CliRuntime]


def _runtime_configuration(settings: Settings) -> dict[str, object]:
    return {
        "qdrant_collection": settings.qdrant_collection,
        "embedding_model": settings.embedding_model,
        "reranker_model": settings.reranker_model,
        "retrieval_limit": settings.retrieval_limit,
        "lexical_candidate_limit": settings.lexical_candidate_limit,
        "min_dense_score": settings.min_dense_score,
        "enable_enrichment": settings.enable_enrichment,
        "generation_provider": settings.main_provider.value,
    }


def _build_runtime(
    request: EvaluationRequest,
    settings: Settings,
    repository: RunRepository,
) -> CliRuntime:
    if request.mode is EvaluationMode.VALIDATE:
        return CliRuntime(
            runner=EvaluationRunner(
                ingestion=None,
                registry=None,
                store=None,
                chat=None,
                repository=repository,
                runtime_configuration=_runtime_configuration(settings),
                semantic_judge=None,
            ),
            flush=None,
        )

    app = create_app(settings)
    judge = None
    if request.run_ragas:
        from evaluation.ragas_adapter import RagasJudge

        judge = RagasJudge.from_settings(settings)
    return CliRuntime(
        runner=EvaluationRunner(
            ingestion=app.state.ingestion,
            registry=app.state.registry,
            store=app.state.store,
            chat=app.state.chat,
            repository=repository,
            runtime_configuration=_runtime_configuration(settings),
            semantic_judge=judge,
        ),
        flush=app.state.tracer.flush,
    )


def run_cli(
    argv: Sequence[str] | None = None,
    *,
    runner_factory: RunnerFactory | None = None,
) -> int:
    request = parse_request(list(argv) if argv is not None else sys.argv[1:])
    settings = Settings()
    repository = LocalRunRepository(request.output_root)
    factory = runner_factory or _build_runtime
    runtime: CliRuntime | None = None
    report: EvaluationReport | None = None
    failure: Exception | None = None
    try:
        runtime = factory(request, settings, repository)
        report = runtime.runner.run(request)
    except Exception as exc:
        failure = exc
    finally:
        if runtime is not None and runtime.flush is not None:
            try:
                runtime.flush()
            except Exception as flush_exc:
                if failure is None:
                    failure = flush_exc
    if failure is not None:
        print(f"rag-eval failed: {type(failure).__name__}: {failure}", file=sys.stderr)
        return 1
    assert report is not None
    print(f"report: {report.report_path}")
    print(json.dumps(report.aggregates, ensure_ascii=False, sort_keys=True))
    return 0 if report.status == "complete" else 1


def main() -> None:
    raise SystemExit(run_cli())
