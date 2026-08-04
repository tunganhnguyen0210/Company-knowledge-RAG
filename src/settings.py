from __future__ import annotations

import json
from enum import StrEnum
from hashlib import sha256
from pathlib import Path

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from domain.schemas import Principal


class TraceMode(StrEnum):
    OFF = "off"
    METADATA_ONLY = "metadata-only"
    FULL = "full"


class MainProvider(StrEnum):
    GEMINI = "gemini"
    OPENROUTER = "openrouter"
    OPENAI = "openai"


def _parse_api_key_mapping(raw: str) -> dict[str, list[str]]:
    if not raw or raw == "{}":
        return {"user": ["*"]}
    try:
        mapping = json.loads(raw)
        if isinstance(mapping, dict):
            return {k: v if isinstance(v, list) else [str(v)] for k, v in mapping.items()}
    except json.JSONDecodeError:
        pass
    return {"user": ["*"]}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"
    api_keys: str = '{"change-me": ["*"]}'
    main_provider: MainProvider = MainProvider.GEMINI
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash-lites"
    embedding_model: str = "jina-embeddings-v3"
    jina_api_key: str = ""
    openrouter_api_key: str = ""
    openrouter_model: str = "google/gemini-3.6-flash"
    openrouter_allowed_models: set[str] = Field(
        default_factory=lambda: {"google/gemini-3.6-flash"}
    )
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"
    provider_timeout_seconds: float = 30.0
    provider_max_attempts: int = 2
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
    trace_mode: TraceMode = TraceMode.METADATA_ONLY
    allow_sensitive_tracing: bool = False
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    @model_validator(mode="after")
    def validate_sensitive_tracing(self) -> Settings:
        if self.trace_mode is TraceMode.FULL and not self.allow_sensitive_tracing:
            raise ValueError("full tracing requires allow_sensitive_tracing=true")
        return self

    def build_gemini_key_pool(self, environment: dict[str, str] | None = None) -> GeminiKeyPool:
        import os
        from providers.gemini_key_pool import GeminiKeyPool

        env = dict(os.environ if environment is None else environment)
        if self.gemini_api_key and "GEMINI_API_KEY" not in env:
            env["GEMINI_API_KEY"] = self.gemini_api_key

        return GeminiKeyPool.from_environment(
            env, cooldown_seconds=self.gemini_key_cooldown_seconds
        )

    def principal_for_key(self, api_key: str) -> Principal:
        mapping = _parse_api_key_mapping(self.api_keys)
        roles = mapping.get(api_key, ["*"])
        key_fingerprint = sha256(api_key.encode("utf-8")).hexdigest()[:12]
        return Principal(subject=f"api-key:{key_fingerprint}", roles=set(roles))

    def swagger_default_api_key(self) -> str | None:
        if self.environment != "development":
            return None
        return next(iter(_parse_api_key_mapping(self.api_keys)))

