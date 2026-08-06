from __future__ import annotations

import json
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from domain.schemas import Chunk
from evaluation.golden import GoldenType
from generation.execution import GenerationExecution, RetrievalExecution


def fingerprint(value: BaseModel | dict[str, Any] | list[Any]) -> str:
    raw = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    encoded = json.dumps(
        raw, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


VOLATILE_ARTIFACT_FIELDS: dict[str, object] = {
    "run_id": True,
    "created_at": True,
    "snapshot_fingerprint": True,
    "run_fingerprint": True,
    "cases": {
        "__all__": {
            "retrieval": {"latency_ms", "request_id"},
            "generation": {"latency_ms", "usage"},
        }
    },
}


def artifact_fingerprint(value: BaseModel) -> str:
    """Hash only phase inputs/evidence; never hash timestamps or storage identity."""
    return fingerprint(value.model_dump(mode="json", exclude=VOLATILE_ARTIFACT_FIELDS))


class EvaluationMode(StrEnum):
    VALIDATE = "validate"
    INGEST = "ingest"
    RETRIEVAL = "retrieval"
    GENERATION = "generation"
    E2E = "e2e"


class ArtifactModel(BaseModel):
    model_config = ConfigDict(frozen=True)


class EvaluationRequest(BaseModel):
    mode: EvaluationMode
    golden_dir: Path = Path("evaluation/golden_set")
    golden_files: list[Path] = Field(default_factory=list)
    question_types: set[GoldenType] = Field(default_factory=set)
    case_ids: set[str] = Field(default_factory=set)
    limit: int | None = Field(default=None, ge=1)
    canonical_source: Path = Path("data/extracted/01_2021_ND-CP_283247.md")
    ingestion_source: Path | None = None
    force_reingest: bool = False
    from_run: str | None = None
    run_ragas: bool = False
    output_root: Path = Path("reports/rag_evaluation")

    @computed_field
    @property
    def baseline_candidate(self) -> bool:
        return (
            self.mode is EvaluationMode.E2E
            and self.golden_dir == Path("evaluation/golden_set")
            and self.canonical_source
            == Path("data/extracted/01_2021_ND-CP_283247.md")
            and not self.golden_files
            and not self.question_types
            and not self.case_ids
            and self.limit is None
        )

    @model_validator(mode="after")
    def validate_mode_contract(self) -> EvaluationRequest:
        if self.golden_files and self.question_types:
            raise ValueError("golden_files and question_types are mutually exclusive")
        if self.force_reingest and self.ingestion_source is None:
            raise ValueError("force_reingest requires an ingestion source")
        if self.mode is EvaluationMode.INGEST and self.ingestion_source is None:
            raise ValueError("ingest mode requires an ingestion source")
        if self.mode is EvaluationMode.GENERATION and self.from_run is None:
            raise ValueError("generation mode requires from_run")
        if self.mode in {EvaluationMode.VALIDATE, EvaluationMode.INGEST} and self.run_ragas:
            raise ValueError(f"{self.mode} does not support Ragas")
        if self.mode is EvaluationMode.VALIDATE and (
            self.question_types or self.case_ids or self.limit is not None
        ):
            raise ValueError(
                "validate checks the complete standard dataset unless golden_files are explicit"
            )
        if self.mode is EvaluationMode.INGEST and (
            self.golden_files
            or self.question_types
            or self.case_ids
            or self.limit is not None
        ):
            raise ValueError("ingest always validates the complete standard dataset")
        replay_replacements = self.model_fields_set & {
            "golden_dir",
            "golden_files",
            "question_types",
            "case_ids",
            "limit",
            "canonical_source",
        }
        if self.mode is EvaluationMode.GENERATION and replay_replacements:
            raise ValueError("generation replay inherits the saved retrieval selection")
        return self


class RunManifest(ArtifactModel):
    run_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    mode: EvaluationMode
    arguments: dict[str, Any]
    git_revision: str | None
    dataset_fingerprint: str
    source_fingerprints: dict[str, str]
    configuration_fingerprints: dict[str, str]
    dependency_versions: dict[str, str]
    artifact_lineage: dict[str, str]


class IndexSnapshot(ArtifactModel):
    run_id: str
    document_id: str
    document_version: int
    source_name: str
    canonical_doc_id: str
    raw_source_hash: str
    canonical_source_hash: str
    chunk_count: int
    collection_name: str
    configuration: dict[str, Any]
    metadata_validation: dict[str, Any]
    chunks: list[Chunk]
    snapshot_fingerprint: str


class RetrievalCaseArtifact(ArtifactModel):
    case_id: str
    type: GoldenType
    difficulty: str
    expected_answer: str
    golden_contexts: list[str]
    retrieval: RetrievalExecution | None
    deterministic_scores: dict[str, float | None] = Field(default_factory=dict)
    error: str | None = None


class RetrievalRun(ArtifactModel):
    run_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    dataset_fingerprint: str
    golden_dir: Path
    dataset_source_files: list[str]
    dataset_scope: str
    canonical_source: Path
    index_snapshot_fingerprint: str
    configuration: dict[str, Any]
    cases: list[RetrievalCaseArtifact]
    run_fingerprint: str


class GenerationCaseArtifact(ArtifactModel):
    case_id: str
    generation: GenerationExecution | None
    deterministic_scores: dict[str, float | None] = Field(default_factory=dict)
    error: str | None = None


class GenerationRun(ArtifactModel):
    run_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    retrieval_run_fingerprint: str
    configuration: dict[str, Any]
    cases: list[GenerationCaseArtifact]
    run_fingerprint: str


class SemanticScoreBatch(ArtifactModel):
    scores: dict[str, dict[str, float | None]]
    errors: dict[str, list[str]] = Field(default_factory=dict)


class EvaluationReport(ArtifactModel):
    run_id: str
    mode: EvaluationMode
    status: str
    dataset_size: int
    evaluated_cases: int
    validation: dict[str, Any]
    aggregates: dict[str, Any]
    target_comparison: dict[str, Any] = Field(default_factory=dict)
    case_scores: dict[str, dict[str, float | None]] = Field(default_factory=dict)
    errors: list[str]
    artifact_ids: dict[str, str]
    baseline_eligible: bool
    report_path: Path | None = None
