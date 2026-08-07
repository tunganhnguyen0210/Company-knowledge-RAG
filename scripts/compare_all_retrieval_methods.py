from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

# Ensure src/ is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from api.app import create_app
from evaluation.artifacts import EvaluationMode, EvaluationRequest
from evaluation.repository import LocalRunRepository
from evaluation.runner import EvaluationRunner
from settings import Settings


def run_eval_for_config(
    method_name: str,
    settings_overrides: dict[str, Any],
    limit: int | None = None,
) -> dict[str, Any]:
    """Run retrieval/e2e evaluation for a specific settings configuration."""
    print(f"\n[+] Running Evaluation for Method: {method_name}...")
    settings = Settings()
    for key, val in settings_overrides.items():
        setattr(settings, key, val)

    output_dir = Path(f"reports/rag_evaluation/compare_methods/{method_name.lower().replace(' ', '_')}")
    output_dir.mkdir(parents=True, exist_ok=True)
    repository = LocalRunRepository(output_dir)

    request = EvaluationRequest(
        mode=EvaluationMode.E2E,
        limit=limit,
        output_root=output_dir,
    )

    app = create_app(settings)
    runner = EvaluationRunner(
        ingestion=app.state.ingestion,
        registry=app.state.registry,
        store=app.state.store,
        chat=app.state.chat,
        repository=repository,
        runtime_configuration={
            "method_name": method_name,
            "qdrant_collection": settings.qdrant_collection,
            "reranker_model": settings.reranker_model,
            "enable_mmr": getattr(settings, "enable_mmr", False),
            "query_transform_mode": getattr(settings, "query_transform_mode", "none"),
        },
        semantic_judge=None,
    )

    report = runner.run(request)
    if app.state.tracer:
        try:
            app.state.tracer.flush()
        except Exception:
            pass

    return {
        "method_name": method_name,
        "report_path": str(report.report_path),
        "aggregates": report.aggregates,
    }


def compare_all_retrieval_methods(limit: int | None = None) -> None:
    methods_config = [
        ("1. Baseline (Hybrid RRF)", {}),
        ("2. Reranker (jina-v3.5)", {"reranker_model": "jina-reranker-v3.5"}),
        ("3. MMR Diversification", {"enable_mmr": True, "mmr_lambda": 0.7}),
        ("4. Multi-Query Expansion", {"query_transform_mode": "multi_query", "multi_query_n": 3}),
        ("5. HyDE", {"query_transform_mode": "hyde"}),
        (
            "6. Full Combined Pipeline",
            {
                "reranker_model": "jina-reranker-v3.5",
                "enable_mmr": True,
                "query_transform_mode": "multi_query",
            },
        ),
    ]

    results: list[dict[str, Any]] = []
    for name, config in methods_config:
        try:
            res = run_eval_for_config(name, config, limit=limit)
            results.append(res)
        except Exception as exc:
            print(f"[-] Failed method {name}: {exc}")

    print("\n" + "=" * 95)
    print("                      ALL RETRIEVAL METHODS COMPARISON MATRIX")
    print("=" * 95)
    header = f"{'METHOD':<28} | {'RECALL (ALL)':<12} | {'HARD RECALL':<12} | {'AMBIGUOUS REC':<14} | {'CITATION COV':<12} | {'LATENCY P95':<11}"
    print(header)
    print("-" * 95)

    base_recall: float | None = None

    for res in results:
        name = res["method_name"]
        ret_agg = res["aggregates"].get("retrieval", {})
        gen_agg = res["aggregates"].get("generation", {})

        recall_all_raw = ret_agg.get("overall", {}).get("coordinate_recall")
        recall_all = recall_all_raw if recall_all_raw is not None else 0.0

        hard_recall_raw = ret_agg.get("by_difficulty", {}).get("hard", {}).get("coordinate_recall")
        hard_recall = hard_recall_raw if hard_recall_raw is not None else 0.0

        amb_recall_raw = ret_agg.get("by_type", {}).get("ambiguous", {}).get("evidence_recall")
        amb_recall = amb_recall_raw if amb_recall_raw is not None else 0.0

        cit_cov_raw = gen_agg.get("overall", {}).get("citation_coverage")
        cit_cov = cit_cov_raw if cit_cov_raw is not None else 0.0

        lat_p95_raw = gen_agg.get("overall", {}).get("end_to_end_latency_ms_p95")
        lat_p95 = (lat_p95_raw / 1000.0) if lat_p95_raw is not None else 0.0

        if base_recall is None:
            base_recall = recall_all
            delta_str = ""
        else:
            diff = recall_all - base_recall
            delta_str = f"({diff:+.1%})"

        print(
            f"{name:<28} | {recall_all:<6.1%} {delta_str:<5} | {hard_recall:<12.1%} | {amb_recall:<14.1%} | {cit_cov:<12.1%} | {lat_p95:<9.2f}s"
        )

    print("=" * 95)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Compare all Retrieval Methods on Golden Set")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of test cases (default: full 100)")
    args = parser.parse_args()
    compare_all_retrieval_methods(limit=args.limit)
