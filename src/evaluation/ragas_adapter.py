from __future__ import annotations

import asyncio
from typing import Any

from openai import AsyncOpenAI
from ragas.embeddings.base import BaseRagasEmbedding, embedding_factory
from ragas.llms import llm_factory
from ragas.metrics.collections import (
    AnswerRelevancy,
    ContextPrecision,
    ContextRecall,
    Faithfulness,
)

from evaluation.artifacts import (
    GenerationCaseArtifact,
    GenerationRun,
    RetrievalCaseArtifact,
    RetrievalRun,
    SemanticScoreBatch,
)

_MetricCall = tuple[str, Any, dict[str, object]]
_CaseScore = tuple[str, dict[str, float | None], list[str]]


def _semantic_score_batch(results: list[_CaseScore]) -> SemanticScoreBatch:
    return SemanticScoreBatch(
        scores={case_id: values for case_id, values, _ in results},
        errors={case_id: errors for case_id, _, errors in results if errors},
    )


class RagasJudge:
    def __init__(
        self,
        context_precision: Any,
        context_recall: Any,
        faithfulness: Any,
        answer_relevancy: Any,
        *,
        max_concurrency: int,
    ) -> None:
        self.context_precision = context_precision
        self.context_recall = context_recall
        self.faithfulness = faithfulness
        self.answer_relevancy = answer_relevancy
        self.max_concurrency = max_concurrency

    @classmethod
    def from_settings(cls, settings: Any) -> RagasJudge:
        api_key = settings.ragas_api_key or settings.openai_api_key
        if not api_key:
            raise ValueError(
                "RAGAS_API_KEY or OPENAI_API_KEY is required for semantic evaluation"
            )
        client = AsyncOpenAI(api_key=api_key, base_url=settings.ragas_base_url)
        llm = llm_factory(settings.ragas_model, client=client)
        embeddings = embedding_factory(
            "openai",
            model=settings.ragas_embedding_model,
            client=client,
        )
        if not isinstance(embeddings, BaseRagasEmbedding):
            raise TypeError("Ragas embedding factory returned a legacy embedding interface")
        return cls(
            ContextPrecision(llm=llm),
            ContextRecall(llm=llm),
            Faithfulness(llm=llm),
            AnswerRelevancy(llm=llm, embeddings=embeddings),
            max_concurrency=settings.ragas_max_concurrency,
        )

    @classmethod
    def from_metrics(
        cls,
        context_precision: Any,
        context_recall: Any,
        faithfulness: Any,
        answer_relevancy: Any,
        *,
        max_concurrency: int,
    ) -> RagasJudge:
        return cls(
            context_precision,
            context_recall,
            faithfulness,
            answer_relevancy,
            max_concurrency=max_concurrency,
        )

    def score_retrieval(self, run: RetrievalRun) -> SemanticScoreBatch:
        return asyncio.run(self._score_retrieval(run))

    def score_generation(
        self,
        retrieval: RetrievalRun,
        generation: GenerationRun,
    ) -> SemanticScoreBatch:
        return asyncio.run(self._score_generation(retrieval, generation))

    async def _metric_value(self, metric: Any, **kwargs: object) -> float:
        result = await metric.ascore(**kwargs)
        return float(result.value)

    async def _score_metric_calls(
        self,
        calls: tuple[_MetricCall, ...],
    ) -> tuple[dict[str, float | None], list[str]]:
        values: dict[str, float | None] = {}
        errors: list[str] = []
        for name, metric, kwargs in calls:
            try:
                values[name] = await self._metric_value(metric, **kwargs)
            except Exception as exc:
                values[name] = None
                errors.append(f"{name}: {type(exc).__name__}")
        return values, errors

    async def _score_retrieval(self, run: RetrievalRun) -> SemanticScoreBatch:
        semaphore = asyncio.Semaphore(self.max_concurrency)

        async def score_case(
            case: RetrievalCaseArtifact,
        ) -> _CaseScore:
            if case.retrieval is None:
                return (
                    case.case_id,
                    {"context_precision": None, "context_recall": None},
                    ["retrieval missing"],
                )
            contexts = [item.hit.chunk.text for item in case.retrieval.hits]
            kwargs: dict[str, object] = {
                "user_input": case.retrieval.question,
                "reference": case.expected_answer,
                "retrieved_contexts": contexts,
            }
            async with semaphore:
                calls: tuple[_MetricCall, ...] = (
                    ("context_precision", self.context_precision, kwargs),
                    ("context_recall", self.context_recall, kwargs),
                )
                values, errors = await self._score_metric_calls(calls)
            return case.case_id, values, errors

        results = await asyncio.gather(*(score_case(case) for case in run.cases))
        return _semantic_score_batch(results)

    async def _score_generation(
        self,
        retrieval: RetrievalRun,
        generation: GenerationRun,
    ) -> SemanticScoreBatch:
        retrieval_by_id = {case.case_id: case for case in retrieval.cases}
        semaphore = asyncio.Semaphore(self.max_concurrency)

        async def score_case(
            case: GenerationCaseArtifact,
        ) -> _CaseScore:
            source = retrieval_by_id[case.case_id]
            if source.retrieval is None:
                return (
                    case.case_id,
                    {"faithfulness": None, "answer_relevancy": None},
                    ["retrieval missing"],
                )
            contexts = [item.hit.chunk.text for item in source.retrieval.hits]
            if case.generation is None:
                return (
                    case.case_id,
                    {"faithfulness": None, "answer_relevancy": None},
                    ["generation missing"],
                )
            async with semaphore:
                calls: tuple[_MetricCall, ...] = (
                    (
                        "faithfulness",
                        self.faithfulness,
                        {
                            "user_input": source.retrieval.question,
                            "response": case.generation.answer,
                            "retrieved_contexts": contexts,
                        },
                    ),
                    (
                        "answer_relevancy",
                        self.answer_relevancy,
                        {
                            "user_input": source.retrieval.question,
                            "response": case.generation.answer,
                        },
                    ),
                )
                values, errors = await self._score_metric_calls(calls)
            return case.case_id, values, errors

        results = await asyncio.gather(
            *(score_case(case) for case in generation.cases)
        )
        return _semantic_score_batch(results)
