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
