import pytest

from company_knowledge_rag.providers.base import GenerationRequest, GenerationResult, ProviderError
from company_knowledge_rag.providers.router import ProviderRouter


class StubProvider:
    def __init__(self, name: str, outcomes: list[object]) -> None:
        self.name = name
        self.outcomes = outcomes
        self.calls = 0

    def generate(self, request: GenerationRequest) -> GenerationResult:
        outcome = self.outcomes[self.calls]
        self.calls += 1
        if isinstance(outcome, Exception):
            raise outcome
        return outcome  # type: ignore[return-value]


def test_router_falls_back_only_for_transient_provider_errors() -> None:
    primary = StubProvider("gemini", [ProviderError("timeout", transient=True)])
    fallback = StubProvider("openrouter", [GenerationResult("ok", "openrouter", "model")])

    result = ProviderRouter(primary, fallback, max_attempts=1).generate(
        GenerationRequest("system", "question")
    )

    assert result.text == "ok"
    assert primary.calls == fallback.calls == 1


def test_router_does_not_fallback_for_permanent_errors() -> None:
    primary = StubProvider("gemini", [ProviderError("bad request", transient=False)])
    fallback = StubProvider("openrouter", [GenerationResult("unused", "openrouter", "model")])

    with pytest.raises(ProviderError, match="bad request"):
        ProviderRouter(primary, fallback, max_attempts=1).generate(
            GenerationRequest("system", "question")
        )

    assert fallback.calls == 0

