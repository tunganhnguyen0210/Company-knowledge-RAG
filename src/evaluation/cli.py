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


def _add_name(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--name",
        type=str,
        default=None,
        help="Optional human-readable experiment tag/name for run directory (e.g. baseline, hyde-test)",
    )


def _add_output(parser: argparse.ArgumentParser) -> None:
    _add_name(parser)
    parser.add_argument("--output-root", type=Path, default=Path("reports/rag_evaluation"))


def _add_ragas(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--ragas",
        action="store_true",
        help="Run report-only Ragas metrics using captured evidence",
    )


def _add_strategy_options(parser: argparse.ArgumentParser) -> None:
    group = parser.add_argument_group("strategy options")
    group.add_argument("--reranker-model", type=str, help="Override reranker_model setting")
    group.add_argument("--enable-mmr", action="store_true", default=None, help="Enable MMR diversification")
    group.add_argument("--mmr-lambda", type=float, help="Override mmr_lambda setting")
    group.add_argument(
        "--query-transform-mode",
        type=str,
        choices=["none", "hyde", "multi_query"],
        help="Override query_transform_mode setting",
    )
    group.add_argument("--enable-mrl", action="store_true", default=None, help="Enable MRL search")
    group.add_argument("--enable-enrichment", action="store_true", default=None, help="Enable enrichment")


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
    _add_strategy_options(retrieval)
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
    _add_strategy_options(generation)
    _add_ragas(generation)
    _add_output(generation)

    e2e = subparsers.add_parser("e2e")
    _add_selection(e2e)
    _add_strategy_options(e2e)
    e2e.add_argument("--ingest", type=Path)
    e2e.add_argument("--force-reingest", action="store_true")
    _add_ragas(e2e)
    _add_output(e2e)

    compare = subparsers.add_parser("compare", help="Compare baseline and candidate evaluation reports")
    compare.add_argument("--baseline", required=True, type=Path, help="Path to baseline report.json")
    compare.add_argument("--candidate", required=True, type=Path, help="Path to candidate report.json")

    return parser


def run_compare(baseline_path: Path, candidate_path: Path) -> int:
    if not baseline_path.exists():
        print(f"Error: Baseline report file not found: {baseline_path}", file=sys.stderr)
        return 1
    if not candidate_path.exists():
        print(f"Error: Candidate report file not found: {candidate_path}", file=sys.stderr)
        return 1

    with baseline_path.open("r", encoding="utf-8") as f:
        base_data = json.load(f)
    with candidate_path.open("r", encoding="utf-8") as f:
        cand_data = json.load(f)

    base_agg = base_data.get("aggregates", {})
    cand_agg = cand_data.get("aggregates", {})

    print("=" * 80)
    print("                    BENCHMARK DELTA COMPARISON REPORT")
    print("=" * 80)
    print(f"Baseline:  {baseline_path}")
    print(f"Candidate: {candidate_path}")
    print("-" * 80)
    print(f"{'METRIC':<35} {'BASELINE':<12} {'CANDIDATE':<12} {'DELTA':<12} {'STATUS'}")
    print("-" * 80)

    # Retrieval metrics
    b_ret_overall = base_agg.get("retrieval", {}).get("overall", {})
    c_ret_overall = cand_agg.get("retrieval", {}).get("overall", {})

    for metric_key in ["coordinate_recall", "evidence_recall"]:
        b_val = b_ret_overall.get(metric_key)
        c_val = c_ret_overall.get(metric_key)
        if b_val is not None and c_val is not None:
            delta = c_val - b_val
            delta_str = f"{delta:+.1%}"
            status = "🟢 IMPROVED" if delta >= 0 else "🔴 REGRESSED"
            print(f"{f'{metric_key} (overall)':<35} {b_val:<12.1%} {c_val:<12.1%} {delta_str:<12} {status}")

    # Retrieval by difficulty
    b_by_diff = base_agg.get("retrieval", {}).get("by_difficulty", {})
    c_by_diff = cand_agg.get("retrieval", {}).get("by_difficulty", {})
    for diff in ["hard", "medium", "easy"]:
        if diff in b_by_diff and diff in c_by_diff:
            b_val = b_by_diff[diff].get("coordinate_recall")
            c_val = c_by_diff[diff].get("coordinate_recall")
            if b_val is not None and c_val is not None:
                delta = c_val - b_val
                delta_str = f"{delta:+.1%}"
                status = "🟢 IMPROVED" if delta >= 0 else "🔴 REGRESSED"
                print(f"{f'coordinate_recall ({diff})':<35} {b_val:<12.1%} {c_val:<12.1%} {delta_str:<12} {status}")

    # Retrieval by type
    b_by_type = base_agg.get("retrieval", {}).get("by_type", {})
    c_by_type = cand_agg.get("retrieval", {}).get("by_type", {})
    if "ambiguous" in b_by_type and "ambiguous" in c_by_type:
        b_val = b_by_type["ambiguous"].get("evidence_recall")
        c_val = c_by_type["ambiguous"].get("evidence_recall")
        if b_val is not None and c_val is not None:
            delta = c_val - b_val
            delta_str = f"{delta:+.1%}"
            status = "🟢 IMPROVED" if delta >= 0 else "🔴 REGRESSED"
            print(f"{f'evidence_recall (ambiguous)':<35} {b_val:<12.1%} {c_val:<12.1%} {delta_str:<12} {status}")

    # Generation metrics
    b_gen_overall = base_agg.get("generation", {}).get("overall", {})
    c_gen_overall = cand_agg.get("generation", {}).get("overall", {})
    for metric_key in ["citation_coverage", "citation_validity", "abstention_accuracy"]:
        b_val = b_gen_overall.get(metric_key)
        c_val = c_gen_overall.get(metric_key)
        if b_val is not None and c_val is not None:
            delta = c_val - b_val
            delta_str = f"{delta:+.1%}"
            status = "🟢 IMPROVED" if delta >= 0 else "🔴 REGRESSED"
            print(f"{f'{metric_key} (overall)':<35} {b_val:<12.1%} {c_val:<12.1%} {delta_str:<12} {status}")

    # Latency P95
    b_lat = b_gen_overall.get("end_to_end_latency_ms_p95")
    c_lat = c_gen_overall.get("end_to_end_latency_ms_p95")
    if b_lat is not None and c_lat is not None:
        delta_ms = c_lat - b_lat
        delta_str = f"{delta_ms:+.0f}ms"
        status = "🟢 WITHIN SLA" if delta_ms <= 150 else "🔴 LATENCY SPIKE"
        print(f"{'end_to_end_latency_ms_p95':<35} {b_lat/1000:<12.2f}s {c_lat/1000:<12.2f}s {delta_str:<12} {status}")

    print("-" * 80)
    print("COMPARISON COMPLETE")
    print("=" * 80)
    return 0


def parse_request(argv: Sequence[str]) -> tuple[EvaluationRequest | None, dict[str, Any]]:
    parser = build_parser()
    values = vars(parser.parse_args(list(argv)))
    mode_str = values.pop("mode")

    if mode_str == "compare":
        return None, {"mode": "compare", "baseline": values["baseline"], "candidate": values["candidate"]}

    mode = EvaluationMode(mode_str)
    source = values.pop("source", None)
    e2e_ingest = values.pop("ingest", None)
    question_types = {GoldenType(value) for value in values.pop("type", [])}
    golden_files = values.pop("golden_file", [])
    case_ids = set(values.pop("case_id", []))

    # Collect strategy override flags
    strategy_overrides = {
        "reranker_model": values.pop("reranker_model", None),
        "enable_mmr": values.pop("enable_mmr", None),
        "mmr_lambda": values.pop("mmr_lambda", None),
        "query_transform_mode": values.pop("query_transform_mode", None),
        "enable_mrl": values.pop("enable_mrl", None),
        "enable_enrichment": values.pop("enable_enrichment", None),
    }

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
        req = EvaluationRequest(**request_values)
        return req, strategy_overrides
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
        "rerank_candidate_limit": settings.rerank_candidate_limit,
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
    request, overrides = parse_request(list(argv) if argv is not None else sys.argv[1:])

    if overrides.get("mode") == "compare":
        return run_compare(overrides["baseline"], overrides["candidate"])

    assert request is not None
    settings = Settings()

    # Apply strategy overrides to Settings
    if overrides.get("reranker_model") is not None:
        settings.reranker_model = overrides["reranker_model"]
    if overrides.get("enable_mmr") is True:
        settings.enable_mmr = True
    if overrides.get("mmr_lambda") is not None:
        settings.mmr_lambda = overrides["mmr_lambda"]
    if overrides.get("query_transform_mode") is not None:
        settings.query_transform_mode = overrides["query_transform_mode"]
    if overrides.get("enable_mrl") is True:
        settings.enable_mrl = True
    if overrides.get("enable_enrichment") is True:
        settings.enable_enrichment = True

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

