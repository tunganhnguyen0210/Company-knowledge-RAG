from typing import Any

import httpx
import pytest
from instructor.core.exceptions import FailedAttempt, InstructorRetryException
from pydantic import BaseModel

from providers.base import GenerationRequest, ProviderError, StructuredResult
from providers.embedding import normalize_embedding
from providers.gemini import is_transient_provider_error
from providers.openai import is_transient_openai_error
from providers.openrouter import is_transient_openrouter_error
from providers.router import ProviderRouter
from providers.structured import create_structured, structured_messages


class Sample(BaseModel):
    value: str


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


@pytest.mark.parametrize("class_name", ["APIConnectionError", "APITimeoutError"])
def test_openai_transport_errors_are_transient(class_name: str) -> None:
    error_type = type(class_name, (Exception,), {})

    assert is_transient_openai_error(error_type("transport failed"))


def test_truncated_embedding_is_normalized_for_cosine_search() -> None:
    vector = normalize_embedding([3.0, 4.0])

    assert vector == pytest.approx([0.6, 0.8])


def test_structured_messages_keep_system_instruction_separate_from_untrusted_prompt() -> None:
    messages = structured_messages(GenerationRequest("system rules", "user question"))

    assert messages == [
        {"role": "system", "content": "system rules"},
        {"role": "user", "content": "user question"},
    ]


def _structured_call(client: Any, is_transient: Any = lambda exc: False) -> None:
    create_structured(
        client,
        provider_name="Stub",
        model="stub-model",
        request=GenerationRequest("system", "user"),
        response_model=Sample,
        max_retries=2,
        is_transient=is_transient,
    )


def _exhausted_client(cause: Exception) -> Any:
    class ExhaustedClient:
        def create_with_completion(self, **kwargs: Any) -> None:
            attempt = FailedAttempt(attempt_number=2, exception=cause, completion=None)
            raise InstructorRetryException(
                str(cause), n_attempts=2, total_usage=0, failed_attempts=[attempt]
            )

    return ExhaustedClient()


def test_unsatisfiable_schema_is_a_permanent_provider_error() -> None:
    validation_error = ValueError("citations: field required")

    with pytest.raises(ProviderError) as error:
        # Another provider cannot fix a schema this model never satisfies.
        _structured_call(
            _exhausted_client(validation_error), is_transient=is_transient_provider_error
        )

    assert error.value.transient is False
    assert "Sample" in str(error.value)
    assert "citations: field required" in str(error.value)


def test_api_failure_behind_exhausted_retries_keeps_its_cause_and_transience() -> None:
    class RateLimited(Exception):
        status_code = 429

    with pytest.raises(ProviderError) as error:
        # instructor also retries API errors, so its wrapper must not hide them.
        _structured_call(
            _exhausted_client(RateLimited("slow down")), is_transient=is_transient_openai_error
        )

    assert error.value.transient is True
    assert "slow down" in str(error.value)


def test_structured_transport_failures_stay_transient() -> None:
    class FailingClient:
        def create_with_completion(self, **kwargs: Any) -> None:
            raise httpx.ConnectError("connection failed")

    with pytest.raises(ProviderError) as error:
        _structured_call(FailingClient(), is_transient=is_transient_provider_error)

    assert error.value.transient is True


def test_structured_result_carries_usage_through_the_router() -> None:
    class StructuredProvider:
        name = "stub"

        def generate_structured(
            self, request: GenerationRequest, response_model: type[Sample]
        ) -> StructuredResult[Sample]:
            return StructuredResult(Sample(value="ok"), "stub", "stub-model", {"input_tokens": 7})

    router = ProviderRouter(StructuredProvider(), None)

    result = router.generate_structured(GenerationRequest("system", "user"), Sample)

    assert result.value.value == "ok"
    assert result.usage == {"input_tokens": 7, "primary_attempts": 1, "fallback_used": 0}
