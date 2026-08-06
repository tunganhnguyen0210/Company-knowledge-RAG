from __future__ import annotations

import asyncio
from typing import Any

from openai import AsyncOpenAI
from ragas.embeddings.base import embedding_factory
from ragas.llms import llm_factory
from ragas.metrics.collections import (
    AnswerRelevancy,
    ContextPrecision,
    ContextRecall,
    Faithfulness,
)

from evaluation.artifacts import GenerationRun, RetrievalRun, SemanticScoreBatch


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

    async def _score_retrieval(self, run: RetrievalRun) -> SemanticScoreBatch:
        semaphore = asyncio.Semaphore(self.max_concurrency)

        async def score_case(
            case: Any,
        ) -> tuple[str, dict[str, float | None], list[str]]:
            if case.retrieval is None:
                return (
                    case.case_id,
                    {"context_precision": None, "context_recall": None},
                    ["retrieval missing"],
                )
            contexts = [item.hit.chunk.text for item in case.retrieval.hits]
            values: dict[str, float | None] = {}
            errors: list[str] = []
            async with semaphore:
                for name, metric in (
                    ("context_precision", self.context_precision),
                    ("context_recall", self.context_recall),
                ):
                    try:
                        values[name] = await self._metric_value(
                            metric,
                            user_input=case.retrieval.question,
                            reference=case.expected_answer,
                            retrieved_contexts=contexts,
                        )
                    except Exception as exc:
                        values[name] = None
                        errors.append(f"{name}: {type(exc).__name__}")
            return case.case_id, values, errors

        results = await asyncio.gather(*(score_case(case) for case in run.cases))
        return SemanticScoreBatch(
            scores={case_id: values for case_id, values, _ in results},
            errors={case_id: errors for case_id, _, errors in results if errors},
        )

    async def _score_generation(
        self,
        retrieval: RetrievalRun,
        generation: GenerationRun,
    ) -> SemanticScoreBatch:
        retrieval_by_id = {case.case_id: case for case in retrieval.cases}
        semaphore = asyncio.Semaphore(self.max_concurrency)

        async def score_case(
            case: Any,
        ) -> tuple[str, dict[str, float | None], list[str]]:
            source = retrieval_by_id[case.case_id]
            if source.retrieval is None:
                return (
                    case.case_id,
                    {"faithfulness": None, "answer_relevancy": None},
                    ["retrieval missing"],
                )
            contexts = [item.hit.chunk.text for item in source.retrieval.hits]
            values: dict[str, float | None] = {}
            errors: list[str] = []
            if case.generation is None:
                return (
                    case.case_id,
                    {"faithfulness": None, "answer_relevancy": None},
                    ["generation missing"],
                )
            async with semaphore:
                calls = (
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
                for name, metric, kwargs in calls:
                    try:
                        values[name] = await self._metric_value(metric, **kwargs)
                    except Exception as exc:
                        values[name] = None
                        errors.append(f"{name}: {type(exc).__name__}")
            return case.case_id, values, errors

        results = await asyncio.gather(
            *(score_case(case) for case in generation.cases)
        )
        return SemanticScoreBatch(
            scores={case_id: values for case_id, values, _ in results},
            errors={case_id: errors for case_id, _, errors in results if errors},
        )
