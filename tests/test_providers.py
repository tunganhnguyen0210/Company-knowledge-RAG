import httpx
import pytest

from company_knowledge_rag.providers.base import GenerationRequest, GenerationResult, ProviderError
from company_knowledge_rag.providers.gemini import is_transient_provider_error, normalize_embedding
from company_knowledge_rag.providers.openrouter import is_transient_openrouter_error
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
    assert result.usage["primary_attempts"] == 1
    assert result.usage["fallback_used"] == 1


def test_router_does_not_fallback_for_permanent_errors() -> None:
    primary = StubProvider("gemini", [ProviderError("bad request", transient=False)])
    fallback = StubProvider("openrouter", [GenerationResult("unused", "openrouter", "model")])

    with pytest.raises(ProviderError, match="bad request"):
        ProviderRouter(primary, fallback, max_attempts=1).generate(
            GenerationRequest("system", "question")
        )

    assert fallback.calls == 0


@pytest.mark.parametrize("code", [408, 429, 500, 502, 503, 504])
def test_gemini_api_error_codes_are_classified_as_transient(code: int) -> None:
    class GeminiAPIError(Exception):
        def __init__(self, error_code: int) -> None:
            self.code = error_code

    assert is_transient_provider_error(GeminiAPIError(code))


@pytest.mark.parametrize(
    "error",
    [httpx.TimeoutException("timeout"), httpx.ConnectError("connection failed")],
)
def test_gemini_transport_errors_are_transient(error: Exception) -> None:
    assert is_transient_provider_error(error)


@pytest.mark.parametrize("class_name", ["APIConnectionError", "APITimeoutError"])
def test_openrouter_transport_errors_are_transient(class_name: str) -> None:
    error_type = type(class_name, (Exception,), {})

    assert is_transient_openrouter_error(error_type("transport failed"))


def test_reduced_gemini_embedding_is_normalized_for_cosine_search() -> None:
    vector = normalize_embedding([3.0, 4.0])

    assert vector == pytest.approx([0.6, 0.8])
