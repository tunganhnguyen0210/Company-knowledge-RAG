import httpx
import pytest

from providers.gemini import is_transient_provider_error, normalize_embedding
from providers.openai import is_transient_openai_error
from providers.openrouter import is_transient_openrouter_error


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


def test_reduced_gemini_embedding_is_normalized_for_cosine_search() -> None:
    vector = normalize_embedding([3.0, 4.0])

    assert vector == pytest.approx([0.6, 0.8])
