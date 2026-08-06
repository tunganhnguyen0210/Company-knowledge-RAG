from __future__ import annotations

import re
from collections import defaultdict
from math import ceil
from statistics import mean
from typing import Any

from domain.schemas import SearchHit
from evaluation.golden import Difficulty, GoldenCase, GoldenType
from generation.service import ABSTENTION


def _normalized(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def score_retrieval_case(case: GoldenCase, hits: list[SearchHit]) -> dict[str, float | None]:
    if not case.golden_truth_contexts:
        return {"coordinate_recall": None, "evidence_recall": None}
    required_coordinates = {
        (item.golden_metadata.doc_id, item.golden_metadata.chapter, item.golden_metadata.article)
        for item in case.golden_truth_contexts
    }
    retrieved_coordinates = {
        (hit.chunk.coordinates.doc_id, hit.chunk.coordinates.chapter, hit.chunk.coordinates.article)
        for hit in hits
    }
    grouped: dict[tuple[str, str | None, str | None], list[tuple[int, str]]] = defaultdict(list)
    for hit in hits:
        key = (
            hit.chunk.coordinates.doc_id,
            hit.chunk.coordinates.chapter,
            hit.chunk.coordinates.article,
        )
        grouped[key].append((hit.chunk.position, hit.chunk.text))
    recovered = 0
    for item in case.golden_truth_contexts:
        metadata = item.golden_metadata
        key = (metadata.doc_id, metadata.chapter, metadata.article)
        text = "".join(value for _, value in sorted(grouped.get(key, [])))
        recovered += _normalized(item.golden_truth_context) in _normalized(text)
    return {
        "coordinate_recall": len(required_coordinates & retrieved_coordinates) / len(required_coordinates),
        "evidence_recall": recovered / len(case.golden_truth_contexts),
    }


def score_generation_case(
    case: GoldenCase,
    *,
    answer: str,
    cited_chunk_ids: set[str],
    retrieved_chunk_ids: set[str],
    retrieval_latency_ms: float,
    generation_latency_ms: float,
) -> dict[str, float | None]:
    abstained = answer.strip() == ABSTENTION
    sentences = [item.strip() for item in re.split(r"(?<=[.!?])\s+", answer) if item.strip()]
    cited_sentences = sum(bool(re.search(r"\[C\d+\]", sentence)) for sentence in sentences)
    return {
        "citation_validity": 1.0 if cited_chunk_ids <= retrieved_chunk_ids else 0.0,
        "citation_coverage": 1.0 if abstained else cited_sentences / max(len(sentences), 1),
        "abstention_accuracy": (
            (1.0 if abstained else 0.0) if case.type is GoldenType.UNANSWERABLE else None
        ),
        "retrieval_latency_ms": retrieval_latency_ms,
        "generation_latency_ms": generation_latency_ms,
        "end_to_end_latency_ms": retrieval_latency_ms + generation_latency_ms,
    }


def aggregate_scores(rows: list[dict[str, float | None]]) -> dict[str, float]:
    keys = sorted({key for row in rows for key in row})
    return {
        key: mean(values)
        for key in keys
        if (values := [float(row[key]) for row in rows if row.get(key) is not None])
    }


def percentile_95(values: list[float]) -> float:
    if not values:
        raise ValueError("percentile requires at least one value")
    ordered = sorted(values)
    return ordered[max(ceil(0.95 * len(ordered)) - 1, 0)]


def _aggregate_segment(rows: list[dict[str, float | None]]) -> dict[str, float]:
    output = aggregate_scores(rows)
    for key in sorted({name for row in rows for name in row if name.endswith("latency_ms")}):
        values = [float(row[key]) for row in rows if row.get(key) is not None]
        if values:
            output[f"{key}_p95"] = percentile_95(values)
    return output


def segment_aggregates(
    cases: list[GoldenCase],
    rows: list[dict[str, float | None]],
) -> dict[str, Any]:
    if len(cases) != len(rows):
        raise ValueError("cases and score rows must have equal length")
    pairs = list(zip(cases, rows, strict=True))
    return {
        "overall": _aggregate_segment(rows),
        "by_type": {
            kind.value: _aggregate_segment([row for case, row in pairs if case.type is kind])
            for kind in GoldenType
            if any(case.type is kind for case, _ in pairs)
        },
        "by_difficulty": {
            difficulty.value: _aggregate_segment(
                [row for case, row in pairs if case.difficulty is difficulty]
            )
            for difficulty in Difficulty
            if any(case.difficulty is difficulty for case, _ in pairs)
        },
    }


RATE_METRICS = {
    "coordinate_recall",
    "evidence_recall",
    "citation_validity",
    "citation_coverage",
    "abstention_accuracy",
    "context_precision",
    "context_recall",
    "faithfulness",
    "answer_relevancy",
}


def compare_to_target(value: dict[str, Any], target: float = 0.85) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, item in value.items():
        if isinstance(item, dict):
            nested = compare_to_target(item, target)
            if nested:
                output[key] = nested
        elif key in RATE_METRICS and isinstance(item, (int, float)):
            output[key] = {"target": target, "meets_target": float(item) >= target}
    return output
