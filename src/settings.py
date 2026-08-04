from __future__ import annotations

import json
import os
from enum import StrEnum
from hashlib import sha256
from pathlib import Path

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

from providers.gemini_key_pool import GeminiKeyPool
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
        return (dotenv_settings, init_settings, env_settings, file_secret_settings)

    environment: str = "development"
    main_provider: MainProvider = MainProvider.GEMINI
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash-lite"
    embedding_model: str = "gemini-embedding-001"
    openrouter_api_key: str = ""
    openrouter_model: str = "deepseek/deepseek-v4-flash-0731"
    openrouter_allowed_models: set[str] = Field(
        default_factory=lambda: {"google/gemini-3.6-flash"}
    )
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"
    provider_timeout_seconds: float = 30.0
    provider_max_attempts: int = 2
    structured_max_retries: int = STRUCTURED_MAX_RETRIES
    gemini_key_cooldown_seconds: float = 60.0
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

    def build_gemini_key_pool(self, environment: dict[str, str] | None = None) -> GeminiKeyPool:
        env = dict(os.environ if environment is None else environment)
        if self.gemini_api_key and "GEMINI_API_KEY" not in env:
            env["GEMINI_API_KEY"] = self.gemini_api_key

        return GeminiKeyPool.from_environment(
            env, cooldown_seconds=self.gemini_key_cooldown_seconds
        )

