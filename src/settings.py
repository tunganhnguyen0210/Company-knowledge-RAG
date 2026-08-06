from __future__ import annotations

import os
from enum import StrEnum
from pathlib import Path

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

from providers.gemini_key_pool import GeminiKeyPool
from providers.key_pool import ApiKeyPool
from providers.structured import STRUCTURED_MAX_RETRIES


class TraceMode(StrEnum):
    OFF = "off"
    METADATA_ONLY = "metadata-only"
    FULL = "full"


class MainProvider(StrEnum):
    GEMINI = "gemini"
    OPENROUTER = "openrouter"
    OPENAI = "openai"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (init_settings, dotenv_settings, env_settings, file_secret_settings)

    environment: str = "development"
    main_provider: MainProvider = MainProvider.GEMINI
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash-lite"
    jina_api_key: str = ""
    embedding_model: str = "jina-embeddings-v5-omni-small"
    reranker_model: str = ""
    openrouter_api_key: str = ""
    openrouter_model: str = "deepseek/deepseek-v4-flash-0731"
    openrouter_allowed_models: set[str] = Field(
        default_factory=lambda: {"google/gemini-3.6-flash"}
    )
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"
    ragas_api_key: str = ""
    ragas_base_url: str = "https://api.openai.com/v1"
    ragas_model: str = "gpt-4.1-mini"
    ragas_embedding_model: str = "text-embedding-3-small"
    ragas_max_concurrency: int = Field(default=2, ge=1, le=16)
    provider_timeout_seconds: float = 30.0
    provider_max_attempts: int = 2
    structured_max_retries: int = STRUCTURED_MAX_RETRIES
    key_cooldown_seconds: float = Field(
        default=30.0,
        validation_alias=AliasChoices("key_cooldown_seconds", "gemini_key_cooldown_seconds"),
    )
    gemini_key_cooldown_seconds: float = 30.0
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""
    qdrant_collection: str = "company_knowledge"
    vector_size: int = Field(
        default=1024,
        validation_alias=AliasChoices("vector_size", "embedding_dimensions"),
    )
    upload_dir: Path = Path("data/uploads")
    registry_path: Path = Path("data/registry.json")
    max_upload_bytes: int = 20 * 1024 * 1024
    retrieval_limit: int = 5
    lexical_candidate_limit: int = 500
    min_dense_score: float = 0.35
    enable_enrichment: bool = False
    trace_mode: TraceMode = TraceMode.FULL
    allow_sensitive_tracing: bool = True
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = Field(
        default="https://cloud.langfuse.com",
        validation_alias=AliasChoices("langfuse_host", "langfuse_base_url", "rag_langfuse_host"),
    )

    @model_validator(mode="after")
    def validate_sensitive_tracing(self) -> Settings:
        if self.trace_mode is TraceMode.FULL and not self.allow_sensitive_tracing:
            raise ValueError("full tracing requires allow_sensitive_tracing=true")
        return self

    def build_key_pool(
        self, prefix: str, environment: dict[str, str] | None = None
    ) -> ApiKeyPool:
        """Build a generic ApiKeyPool for any provider prefix (GEMINI, JINA, OPENAI, etc.)."""
        env = dict(os.environ if environment is None else environment)
        prefix_upper = prefix.upper()
        single_key_attr = f"{prefix.lower()}_api_key"
        single_key_val = getattr(self, single_key_attr, "")
        primary_env_var = f"{prefix_upper}_API_KEY"

        if single_key_val and primary_env_var not in env:
            env[primary_env_var] = single_key_val

        cooldown = self.key_cooldown_seconds
        return ApiKeyPool.from_environment(
            prefix_upper, env, cooldown_seconds=cooldown
        )

    def build_gemini_key_pool(self, environment: dict[str, str] | None = None) -> GeminiKeyPool:
        pool = self.build_key_pool("GEMINI", environment=environment)
        return GeminiKeyPool(pool._keys, clock=pool._clock, cooldown_seconds=pool.cooldown_seconds)

    def build_jina_key_pool(self, environment: dict[str, str] | None = None) -> ApiKeyPool:
        return self.build_key_pool("JINA", environment=environment)
