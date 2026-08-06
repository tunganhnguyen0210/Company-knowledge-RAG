import pytest
from pydantic import ValidationError

from settings import Settings, TraceMode


def test_settings_default_trace_mode(monkeypatch) -> None:
    monkeypatch.delenv("TRACE_MODE", raising=False)
    settings = Settings(gemini_api_key="key", _env_file=None)
    assert settings.trace_mode is TraceMode.FULL


def test_settings_reads_unprefixed_main_provider(monkeypatch) -> None:
    monkeypatch.setenv("MAIN_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "key")
    monkeypatch.setenv("OPENROUTER_MODEL", "openai/gpt-4.1-mini")
    monkeypatch.setenv("OPENROUTER_ALLOWED_MODELS", '["openai/gpt-4.1-mini"]')

    settings = Settings(_env_file=None)

    assert settings.main_provider == "openrouter"



def test_settings_reject_full_tracing_without_explicit_consent() -> None:
    with pytest.raises(ValidationError, match="allow_sensitive_tracing"):
        Settings(trace_mode="full", allow_sensitive_tracing=False, _env_file=None)


def test_ragas_settings_are_explicit_and_bounded() -> None:
    settings = Settings(
        ragas_api_key="judge-key",
        ragas_base_url="https://judge.example/v1",
        ragas_model="judge-model",
        ragas_embedding_model="judge-embedding",
        ragas_max_concurrency=3,
        _env_file=None,
    )

    assert settings.ragas_model == "judge-model"
    assert settings.ragas_embedding_model == "judge-embedding"
    assert settings.ragas_max_concurrency == 3


@pytest.mark.parametrize("value", [0, 17])
def test_ragas_max_concurrency_is_bounded(value: int) -> None:
    with pytest.raises(ValidationError):
        Settings(ragas_max_concurrency=value, _env_file=None)
