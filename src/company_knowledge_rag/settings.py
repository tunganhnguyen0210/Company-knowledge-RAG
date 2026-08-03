from __future__ import annotations

import json
from enum import StrEnum
from hashlib import sha256
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from company_knowledge_rag.domain.schemas import Principal


class TraceMode(StrEnum):
    OFF = "off"
    METADATA_ONLY = "metadata-only"
    FULL = "full"


def _parse_api_key_mapping(raw: str) -> dict[str, list[str]]:
    try:
        mapping = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("api_keys must be a valid JSON object") from exc
    if not isinstance(mapping, dict) or not mapping:
        raise ValueError("api_keys must be a non-empty JSON object")
    if any(
        not isinstance(key, str)
        or not key
        or not isinstance(roles, list)
        or not roles
        or not all(isinstance(role, str) and role for role in roles)
        for key, roles in mapping.items()
    ):
        raise ValueError("api_keys must map non-empty keys to non-empty role lists")
    return mapping


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="RAG_", extra="ignore")

    environment: str = "development"
    api_keys: str = '{"change-me": ["employee"]}'
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.6-flash"
    embedding_model: str = "gemini-embedding-001"
    openrouter_api_key: str = ""
    openrouter_model: str = "google/gemini-3.6-flash"
    openrouter_allowed_models: set[str] = Field(
        default_factory=lambda: {"google/gemini-3.6-flash"}
    )
    provider_timeout_seconds: float = 30.0
    provider_max_attempts: int = 2
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""
    qdrant_collection: str = "company_knowledge"
    vector_size: int = 3072
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
        _parse_api_key_mapping(self.api_keys)
        if self.trace_mode is TraceMode.FULL and not self.allow_sensitive_tracing:
            raise ValueError("full tracing requires allow_sensitive_tracing=true")
        if self.environment == "production" and "change-me" in self.api_keys:
            raise ValueError("production requires explicit API keys")
        if self.openrouter_model not in self.openrouter_allowed_models:
            raise ValueError("openrouter_model must be included in openrouter_allowed_models")
        return self

    def principal_for_key(self, api_key: str) -> Principal:
        try:
            mapping = _parse_api_key_mapping(self.api_keys)
            roles = mapping[api_key]
        except KeyError as exc:
            raise KeyError("invalid API key") from exc
        key_fingerprint = sha256(api_key.encode("utf-8")).hexdigest()[:12]
        return Principal(subject=f"api-key:{key_fingerprint}", roles=set(roles))
