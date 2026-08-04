from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pydantic import AliasChoices, BaseModel, Field, field_validator

from generation.service import ABSTENTION, ChatService


class GoldenCase(BaseModel):
    question: str
    expected_sources: set[str] = Field(
        default_factory=set,
        validation_alias=AliasChoices("expected_sources", "source", "sources"),
    )
    expected_answer: str | None = Field(
        default=None,
        validation_alias=AliasChoices("expected_answer", "answer"),
    )
    should_abstain: bool = False
    category: str = "lookup"

    @field_validator("expected_sources", mode="before")
    @classmethod
    def _convert_sources_to_set(cls, v: Any) -> set[str]:
        if isinstance(v, str):
            v_str = v.strip()
            return {v_str} if v_str else set()
        if isinstance(v, (list, tuple, set)):
            return {item.strip() for item in v if isinstance(item, str) and item.strip()}
        return set()


class CaseScores(BaseModel):
    retrieval_hit: float
    groundedness: float
    citation_coverage: float
    abstention_accuracy: float
    latency_ms: float


def score_response(
    case: GoldenCase,
    *,
    answer: str,
    citation_sources: set[str],
    retrieval_count: int,
    latency_ms: float,
) -> CaseScores:
    abstained = answer.strip() == ABSTENTION
    sentences = [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", answer) if sentence.strip()]
    cited_sentences = sum(bool(re.search(r"\[C\d+\]", sentence)) for sentence in sentences)
    coverage = 1.0 if abstained else cited_sentences / max(len(sentences), 1)
    retrieval_hit = (
        1.0
        if (case.should_abstain and retrieval_count == 0)
        or (not case.should_abstain and bool(case.expected_sources & citation_sources))
        else 0.0
    )
    return CaseScores(
        retrieval_hit=retrieval_hit,
        groundedness=1.0 if abstained or bool(citation_sources) else 0.0,
        citation_coverage=coverage,
        abstention_accuracy=1.0 if abstained == case.should_abstain else 0.0,
        latency_ms=latency_ms,
    )


def run_golden_set(chat: ChatService, path: Path) -> dict[str, object]:
    cases = [GoldenCase.model_validate(item) for item in json.loads(path.read_text(encoding="utf-8"))]
    details: list[dict[str, Any]] = []
    for case in cases:
        response = chat.answer(case.question)
        scores = score_response(
            case,
            answer=response.answer,
            citation_sources={citation.source_name for citation in response.citations},
            retrieval_count=response.retrieval.result_count,
            latency_ms=response.retrieval.latency_ms,
        )
        details.append(
            {
                "question": case.question,
                "category": case.category,
                "expected_answer": case.expected_answer,
                "answer": response.answer,
                "scores": scores.model_dump(),
            }
        )
    metric_names = ("retrieval_hit", "groundedness", "citation_coverage", "abstention_accuracy")
    aggregate = {
        metric: sum(float(item["scores"][metric]) for item in details) / max(len(details), 1)
        for metric in metric_names
    }
    aggregate["avg_latency_ms"] = sum(
        float(item["scores"]["latency_ms"]) for item in details
    ) / max(len(details), 1)
    return {"aggregate": aggregate, "cases": details}
