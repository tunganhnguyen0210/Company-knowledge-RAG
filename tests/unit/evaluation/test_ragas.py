from types import SimpleNamespace
from typing import Any

import pytest

try:
    from evaluation.ragas_adapter import RagasJudge
    RAGAS_AVAILABLE = True
except ImportError:
    RAGAS_AVAILABLE = False
    RagasJudge = Any

pytestmark = pytest.mark.skipif(not RAGAS_AVAILABLE, reason="Ragas or its dependencies are not fully installed")
from tests.support.evaluation_fakes import make_generation_run, make_retrieval_run


class FakeMetric:
    def __init__(self, value: float, error: Exception | None = None) -> None:
        self.value = value
        self.error = error
        self.calls: list[dict[str, object]] = []

    async def ascore(self, **kwargs: object) -> SimpleNamespace:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return SimpleNamespace(value=self.value)


def _judge(**overrides: FakeMetric) -> RagasJudge:
    metrics = {
        "context_precision": FakeMetric(0.91),
        "context_recall": FakeMetric(0.82),
        "faithfulness": FakeMetric(0.73),
        "answer_relevancy": FakeMetric(0.64),
    }
    metrics.update(overrides)
    return RagasJudge.from_metrics(max_concurrency=2, **metrics)


def test_retrieval_scores_only_context_metrics() -> None:
    judge = _judge()

    batch = judge.score_retrieval(make_retrieval_run())

    assert batch.scores["DL-001"] == {
        "context_precision": 0.91,
        "context_recall": 0.82,
    }
    assert batch.errors == {}


def test_retrieval_routes_captured_question_reference_and_contexts() -> None:
    precision = FakeMetric(0.9)
    recall = FakeMetric(0.8)
    judge = _judge(context_precision=precision, context_recall=recall)

    judge.score_retrieval(make_retrieval_run())

    expected = {
        "user_input": "golden question",
        "reference": "golden reference",
        "retrieved_contexts": ["retrieved original text"],
    }
    assert precision.calls == [expected]
    assert recall.calls == [expected]


def test_generation_uses_saved_contexts_answer_and_reference() -> None:
    faithfulness = FakeMetric(0.9)
    relevancy = FakeMetric(0.8)
    judge = _judge(faithfulness=faithfulness, answer_relevancy=relevancy)
    retrieval = make_retrieval_run()

    batch = judge.score_generation(retrieval, make_generation_run(retrieval=retrieval))

    assert batch.scores["DL-001"] == {
        "faithfulness": 0.9,
        "answer_relevancy": 0.8,
    }
    assert faithfulness.calls == [
        {
            "user_input": "golden question",
            "response": "generated answer [C1].",
            "retrieved_contexts": ["retrieved original text"],
        }
    ]
    assert relevancy.calls == [
        {
            "user_input": "golden question",
            "response": "generated answer [C1].",
        }
    ]


def test_metric_failure_is_recorded_without_erasing_other_score() -> None:
    judge = _judge(context_precision=FakeMetric(0.0, RuntimeError("secret")))

    batch = judge.score_retrieval(make_retrieval_run())

    assert batch.scores["DL-001"] == {
        "context_precision": None,
        "context_recall": 0.82,
    }
    assert batch.errors == {"DL-001": ["context_precision: RuntimeError"]}


def test_missing_retrieval_is_reported_without_metric_calls() -> None:
    precision = FakeMetric(0.9)
    judge = _judge(context_precision=precision)
    run = make_retrieval_run()
    run = run.model_copy(
        update={"cases": [run.cases[0].model_copy(update={"retrieval": None})]}
    )

    batch = judge.score_retrieval(run)

    assert batch.scores["DL-001"] == {
        "context_precision": None,
        "context_recall": None,
    }
    assert batch.errors == {"DL-001": ["retrieval missing"]}
    assert precision.calls == []


def test_from_settings_requires_a_judge_or_openai_key() -> None:
    settings = SimpleNamespace(ragas_api_key="", openai_api_key="")

    with pytest.raises(ValueError, match="RAGAS_API_KEY or OPENAI_API_KEY"):
        RagasJudge.from_settings(settings)
