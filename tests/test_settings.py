import pytest
from pydantic import ValidationError

from company_knowledge_rag.settings import Settings, TraceMode


def test_settings_parse_api_keys_and_roles() -> None:
    settings = Settings(
        api_keys='{"demo-secret": ["employee", "hr"]}',
        gemini_api_key="key",
    )

    assert settings.principal_for_key("demo-secret").roles == {"employee", "hr"}
    assert settings.trace_mode is TraceMode.METADATA_ONLY


def test_settings_reject_full_tracing_without_explicit_consent() -> None:
    with pytest.raises(ValidationError, match="allow_sensitive_tracing"):
        Settings(trace_mode="full", allow_sensitive_tracing=False)


def test_production_rejects_default_api_key() -> None:
    with pytest.raises(ValidationError, match="production requires explicit API keys"):
        Settings(environment="production")
