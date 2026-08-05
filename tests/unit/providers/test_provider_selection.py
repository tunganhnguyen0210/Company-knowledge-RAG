from api.app import _build_provider
from settings import Settings


def test_selected_provider_is_primary_with_configured_fallback() -> None:
    settings = Settings(
        main_provider="openrouter",
        openrouter_api_key="selected-provider-key",
        openrouter_model="openai/gpt-4.1-mini",
        openrouter_allowed_models={"openai/gpt-4.1-mini"},
        gemini_api_key="fallback-provider-key",
    )

    provider = _build_provider(settings)

    assert provider.primary.name == "openrouter"
    assert provider.fallback is not None
    assert provider.fallback.name == "gemini"


def test_openai_can_be_selected_as_primary_provider() -> None:
    settings = Settings(
        main_provider="openai",
        openai_api_key="selected-provider-key",
    )

    provider = _build_provider(settings)

    assert provider.primary.name == "openai"
