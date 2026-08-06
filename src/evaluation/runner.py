from __future__ import annotations

import platform
import subprocess
from hashlib import sha256
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from domain.schemas import Chunk, Document, DocumentStatus
from evaluation.artifacts import (
    EvaluationMode,
    EvaluationReport,
    EvaluationRequest,
    GenerationCaseArtifact,
    GenerationRun,
    IndexSnapshot,
    RetrievalCaseArtifact,
    RetrievalRun,
    RunManifest,
    SemanticScoreBatch,
    artifact_fingerprint,
    fingerprint,
)
from evaluation.golden import (
    GoldenCase,
    GoldenDataset,
    GoldenValidationReport,
    load_golden_dataset,
    select_cases,
    validate_golden_dataset,
)
from evaluation.metrics import (
    compare_to_target,
    score_generation_case,
    score_retrieval_case,
    segment_aggregates,
)
from evaluation.repository import RunRepository
from generation.service import ChatService
from ingestion.service import IngestionService
from retrieval.base import ChunkStore
from storage.registry import DocumentRegistry

DEFAULT_GOLDEN_DIR = Path("evaluation/golden_set")
DEFAULT_CANONICAL_SOURCE = Path("data/extracted/01_2021_ND-CP_283247.md")


class SemanticJudge(Protocol):
    def score_retrieval(self, run: RetrievalRun) -> SemanticScoreBatch:
        raise NotImplementedError

    def score_generation(
        self,
        retrieval: RetrievalRun,
        generation: GenerationRun,
    ) -> SemanticScoreBatch:
        raise NotImplementedError


class EvaluationRunner:
    def __init__(
        self,
        *,
        ingestion: IngestionService | None,
        registry: DocumentRegistry | None,
        store: ChunkStore | None,
        chat: ChatService | None,
        repository: RunRepository,
        runtime_configuration: dict[str, object],
        semantic_judge: SemanticJudge | None,
    ) -> None:
        self.ingestion = ingestion
        self.registry = registry
        self.store = store
        self.chat = chat
        self.repository = repository
        self.runtime_configuration = runtime_configuration
        self.semantic_judge = semantic_judge

    def run(self, request: EvaluationRequest) -> EvaluationReport:
        run_id = uuid4().hex
        manifest: RunManifest | None = None
        try:
            replay_source = (
                self.repository.load_retrieval(request.from_run)
                if request.mode is EvaluationMode.GENERATION
                and request.from_run is not None
                else None
            )
            effective_request = request
            if replay_source is not None:
                replay_files = [Path(path) for path in replay_source.dataset_source_files]
                effective_request = request.model_copy(
                    update={
                        "golden_dir": replay_source.golden_dir,
                        "golden_files": (
                            replay_files if replay_source.dataset_scope == "partial" else []
                        ),
                        "canonical_source": replay_source.canonical_source,
                    }
                )
                dataset = load_golden_dataset(
                    replay_source.golden_dir,
                    files=(
                        replay_files if replay_source.dataset_scope == "partial" else None
                    ),
                )
                if dataset.source_files != replay_source.dataset_source_files:
                    raise ValueError(
                        "retrieval artifact golden source-file selection is incompatible"
                    )
            else:
                dataset = load_golden_dataset(
                    request.golden_dir,
                    files=request.golden_files or None,
                )
            manifest = self._build_manifest(effective_request, dataset, run_id)
            validation = validate_golden_dataset(
                dataset,
                canonical_path=effective_request.canonical_source,
                chunks=None,
                audit_root=effective_request.golden_dir.parent,
            )
            if validation.errors:
                report = EvaluationReport(
                    run_id=run_id,
                    mode=request.mode,
                    status="failed",
                    dataset_size=len(dataset.cases),
                    evaluated_cases=0,
                    validation=validation.model_dump(mode="json"),
                    aggregates={},
                    errors=[issue.message for issue in validation.errors],
                    artifact_ids={},
                    baseline_eligible=False,
                )
            else:
                selected = (
                    []
                    if request.mode
                    in {
                        EvaluationMode.VALIDATE,
                        EvaluationMode.INGEST,
                        EvaluationMode.GENERATION,
                    }
                    else select_cases(
                        dataset,
                        question_types=request.question_types or None,
                        case_ids=request.case_ids or None,
                        limit=request.limit,
                    )
                )
                try:
                    if effective_request.mode is EvaluationMode.VALIDATE:
                        report = self._run_validate(
                            effective_request, dataset, validation, run_id
                        )
                    elif effective_request.mode is EvaluationMode.INGEST:
                        report = self._run_ingest(
                            effective_request, dataset, validation, run_id
                        )
                    elif effective_request.mode is EvaluationMode.RETRIEVAL:
                        report = self._retrieval_report(
                            effective_request, dataset, selected, validation, run_id
                        )
                    elif effective_request.mode is EvaluationMode.GENERATION:
                        report = self._generation_report(
                            effective_request, dataset, validation, run_id
                        )
                    else:
                        report = self._run_e2e(
                            effective_request, dataset, selected, validation, run_id
                        )
                except Exception as exc:
                    report = EvaluationReport(
                        run_id=run_id,
                        mode=request.mode,
                        status="failed",
                        dataset_size=len(dataset.cases),
                        evaluated_cases=0,
                        validation=validation.model_dump(mode="json"),
                        aggregates={},
                        errors=[f"{type(exc).__name__}: {exc}"],
                        artifact_ids={},
                        baseline_eligible=False,
                    )
            return self._finish_report(report, manifest)
        except Exception as exc:
            failed_report = EvaluationReport(
                run_id=run_id,
                mode=request.mode,
                status="failed",
                dataset_size=0,
                evaluated_cases=0,
                validation=GoldenValidationReport(
                    errors=[],
                    warnings=[],
                    validated_cases=0,
                    full_conformance=False,
                ).model_dump(mode="json"),
                aggregates={},
                errors=[f"{type(exc).__name__}: {exc}"],
                artifact_ids={},
                baseline_eligible=False,
            )
            return self._finish_report(failed_report, manifest)

    def _finish_report(
        self,
        report: EvaluationReport,
        manifest: RunManifest | None,
    ) -> EvaluationReport:
        if manifest is not None:
            final_manifest = manifest.model_copy(
                update={"artifact_lineage": report.artifact_ids}
            )
            self.repository.save_manifest(final_manifest)
        path = self.repository.save_report(report)
        return report.model_copy(update={"report_path": path})

    def _build_manifest(
        self,
        request: EvaluationRequest,
        dataset: GoldenDataset,
        run_id: str,
    ) -> RunManifest:
        raw_path = request.ingestion_source or Path(
            "data/raw/01_2021_ND-CP_283247.docx"
        )
        source_fingerprints = {
            "canonical": sha256(request.canonical_source.read_bytes()).hexdigest()
        }
        if raw_path.exists():
            source_fingerprints["raw"] = sha256(raw_path.read_bytes()).hexdigest()
        try:
            ragas_version = package_version("ragas")
        except PackageNotFoundError:
            ragas_version = "not-installed"
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            check=False,
            text=True,
        )
        return RunManifest(
            run_id=run_id,
            mode=request.mode,
            arguments=request.model_dump(mode="json"),
            git_revision=(
                revision.stdout.strip() if revision.returncode == 0 else None
            ),
            dataset_fingerprint=fingerprint(
                [case.model_dump(mode="json") for case in dataset.cases]
            ),
            source_fingerprints=source_fingerprints,
            configuration_fingerprints={
                "runtime": fingerprint(self.runtime_configuration),
                "selection": fingerprint(
                    {
                        "golden_dir": str(request.golden_dir),
                        "files": [str(path) for path in request.golden_files],
                        "types": sorted(item.value for item in request.question_types),
                        "case_ids": sorted(request.case_ids),
                        "limit": request.limit,
                        "canonical_source": str(request.canonical_source),
                    }
                ),
            },
            dependency_versions={
                "python": platform.python_version(),
                "ragas": ragas_version,
            },
            artifact_lineage={},
        )

    def _run_validate(
        self,
        request: EvaluationRequest,
        dataset: GoldenDataset,
        validation: GoldenValidationReport,
        run_id: str,
    ) -> EvaluationReport:
        return EvaluationReport(
            run_id=run_id,
            mode=request.mode,
            status="complete",
            dataset_size=len(dataset.cases),
            evaluated_cases=0,
            validation=validation.model_dump(mode="json"),
            aggregates={},
            errors=[],
            artifact_ids={},
            baseline_eligible=False,
        )

    def _preflight_index(
        self, request: EvaluationRequest
    ) -> tuple[Document, list[Chunk]]:
        if self.registry is None or self.store is None:
            raise RuntimeError("index runtime is unavailable")
        source_name = (
            request.ingestion_source.name
            if request.ingestion_source is not None
            else "01_2021_ND-CP_283247.docx"
        )
        document = self.registry.find_by_source(source_name)
        chunks = (
            []
            if document is None or document.status is not DocumentStatus.READY
            else self.store.list_document_chunks(document.id, document.version)
        )
        canonical_ids = {chunk.coordinates.doc_id for chunk in chunks}
        coordinates_valid = all(
            chunk.coordinates.article is None
            or chunk.coordinates.chapter is not None
            for chunk in chunks
        )
        payloads_valid = (
            all(
                chunk.text
                and chunk.content_hash
                and chunk.version == document.version
                and chunk.status is DocumentStatus.READY
                for chunk in chunks
            )
            and len({chunk.position for chunk in chunks}) == len(chunks)
        )
        if (
            document is None
            or not chunks
            or canonical_ids != {request.canonical_source.name}
            or not coordinates_valid
            or not payloads_valid
        ):
            raise RuntimeError(
                "Index is missing or incompatible. Run:\n"
                "rag-eval ingest --source data/raw/01_2021_ND-CP_283247.docx"
            )
        return document, chunks

    def _build_snapshot(
        self,
        run_id: str,
        request: EvaluationRequest,
        document: Document,
        chunks: list[Chunk],
        validation: GoldenValidationReport,
    ) -> IndexSnapshot:
        source_hash = document.content_hash
        if request.ingestion_source is not None:
            source_hash = sha256(request.ingestion_source.read_bytes()).hexdigest()
        draft = IndexSnapshot(
            run_id=run_id,
            document_id=document.id,
            document_version=document.version,
            source_name=document.source_name,
            canonical_doc_id=request.canonical_source.name,
            raw_source_hash=source_hash,
            canonical_source_hash=sha256(
                request.canonical_source.read_bytes()
            ).hexdigest(),
            chunk_count=len(chunks),
            collection_name=str(
                self.runtime_configuration.get("qdrant_collection", "memory")
            ),
            configuration=self.runtime_configuration,
            metadata_validation=validation.model_dump(mode="json"),
            chunks=chunks,
            snapshot_fingerprint="",
        )
        return draft.model_copy(
            update={"snapshot_fingerprint": artifact_fingerprint(draft)}
        )

    def _ingest_source(
        self, request: EvaluationRequest
    ) -> tuple[Document, list[Chunk]]:
        if (
            self.ingestion is None
            or self.store is None
            or request.ingestion_source is None
        ):
            raise RuntimeError("ingestion runtime and source are required")
        source_path = request.ingestion_source
        document = self.ingestion.ingest_bytes(
            source_path.name,
            source_path.read_bytes(),
            {"canonical_doc_id": request.canonical_source.name},
            force=request.force_reingest,
        )
        if document.status is not DocumentStatus.READY:
            raise RuntimeError(f"ingestion ended with status {document.status}")
        chunks = self.store.list_document_chunks(document.id, document.version)
        if not chunks:
            raise RuntimeError("ingestion produced no indexed chunks")
        return document, chunks

    def _run_ingest(
        self,
        request: EvaluationRequest,
        dataset: GoldenDataset,
        validation: GoldenValidationReport,
        run_id: str,
    ) -> EvaluationReport:
        try:
            document, chunks = self._ingest_source(request)
            chunk_validation = validate_golden_dataset(
                dataset,
                request.canonical_source,
                chunks=chunks,
                audit_root=request.golden_dir.parent,
            )
            if chunk_validation.errors:
                raise ValueError(
                    "; ".join(issue.message for issue in chunk_validation.errors)
                )
            snapshot = self._build_snapshot(
                run_id, request, document, chunks, chunk_validation
            )
            self.repository.save_snapshot(snapshot)
            return EvaluationReport(
                run_id=run_id,
                mode=request.mode,
                status="complete",
                dataset_size=len(dataset.cases),
                evaluated_cases=0,
                validation=chunk_validation.model_dump(mode="json"),
                aggregates={},
                errors=[],
                artifact_ids={"index_snapshot": snapshot.snapshot_fingerprint},
                baseline_eligible=False,
            )
        except Exception as exc:
            return EvaluationReport(
                run_id=run_id,
                mode=request.mode,
                status="failed",
                dataset_size=len(dataset.cases),
                evaluated_cases=0,
                validation=validation.model_dump(mode="json"),
                aggregates={},
                errors=[f"{type(exc).__name__}: {exc}"],
                artifact_ids={},
                baseline_eligible=False,
            )

    def _retrieval_report(
        self,
        request: EvaluationRequest,
        dataset: GoldenDataset,
        selected: list[GoldenCase],
        validation: GoldenValidationReport,
        run_id: str,
    ) -> EvaluationReport:
        if self.chat is None:
            raise RuntimeError("chat runtime is unavailable")
        document, chunks = self._preflight_index(request)
        validation = validate_golden_dataset(
            dataset,
            request.canonical_source,
            chunks=chunks,
            audit_root=request.golden_dir.parent,
        )
        if validation.errors:
            raise ValueError("; ".join(issue.message for issue in validation.errors))
        snapshot = self._build_snapshot(run_id, request, document, chunks, validation)
        self.repository.save_snapshot(snapshot)
        artifacts: list[RetrievalCaseArtifact] = []
        errors: list[str] = []
        for case in selected:
            try:
                execution = self.chat.retrieve(case.question)
                hits = [item.hit for item in execution.hits]
                artifacts.append(
                    RetrievalCaseArtifact(
                        case_id=case.id,
                        type=case.type,
                        difficulty=case.difficulty.value,
                        expected_answer=case.expected_answer,
                        golden_contexts=[
                            item.golden_truth_context
                            for item in case.golden_truth_contexts
                        ],
                        retrieval=execution,
                        deterministic_scores=score_retrieval_case(case, hits),
                    )
                )
            except Exception as exc:
                message = f"{case.id}: {type(exc).__name__}: {exc}"
                errors.append(message)
                artifacts.append(
                    RetrievalCaseArtifact(
                        case_id=case.id,
                        type=case.type,
                        difficulty=case.difficulty.value,
                        expected_answer=case.expected_answer,
                        golden_contexts=[
                            item.golden_truth_context
                            for item in case.golden_truth_contexts
                        ],
                        retrieval=None,
                        error=message,
                    )
                )
        draft = RetrievalRun(
            run_id=run_id,
            dataset_fingerprint=fingerprint(
                [case.model_dump(mode="json") for case in dataset.cases]
            ),
            golden_dir=request.golden_dir,
            dataset_source_files=dataset.source_files,
            dataset_scope=dataset.scope,
            canonical_source=request.canonical_source,
            index_snapshot_fingerprint=snapshot.snapshot_fingerprint,
            configuration=self.runtime_configuration,
            cases=artifacts,
            run_fingerprint="",
        )
        retrieval = draft.model_copy(
            update={"run_fingerprint": artifact_fingerprint(draft)}
        )
        semantic_scores: dict[str, dict[str, float | None]] = {}
        if request.run_ragas:
            if self.semantic_judge is None:
                errors.append("Ragas requested but semantic judge is unavailable")
            else:
                batch = self.semantic_judge.score_retrieval(retrieval)
                semantic_scores = batch.scores
                errors.extend(
                    f"{case_id}: {message}"
                    for case_id, messages in batch.errors.items()
                    for message in messages
                )
        self.repository.save_retrieval(retrieval)
        status = "complete" if not errors else "incomplete"
        successful_ids = {
            item.case_id for item in retrieval.cases if item.retrieval is not None
        }
        aggregates = segment_aggregates(
            [case for case in selected if case.id in successful_ids],
            [
                item.deterministic_scores | semantic_scores.get(item.case_id, {})
                for item in retrieval.cases
                if item.retrieval is not None
            ],
        )
        case_scores = {
            item.case_id: item.deterministic_scores
            | semantic_scores.get(item.case_id, {})
            for item in retrieval.cases
        }
        return EvaluationReport(
            run_id=run_id,
            mode=request.mode,
            status=status,
            dataset_size=len(dataset.cases),
            evaluated_cases=len(selected),
            validation=validation.model_dump(mode="json"),
            aggregates=aggregates,
            target_comparison=compare_to_target(aggregates),
            case_scores=case_scores,
            errors=errors,
            artifact_ids={
                "index_snapshot": snapshot.snapshot_fingerprint,
                "retrieval_run": retrieval.run_fingerprint,
            },
            baseline_eligible=False,
        )

    def _generation_report(
        self,
        request: EvaluationRequest,
        dataset: GoldenDataset,
        validation: GoldenValidationReport,
        run_id: str,
    ) -> EvaluationReport:
        if self.chat is None or request.from_run is None:
            raise RuntimeError("generation runtime and from_run are required")
        retrieval = self.repository.load_retrieval(request.from_run)
        expected_dataset_fingerprint = fingerprint(
            [case.model_dump(mode="json") for case in dataset.cases]
        )
        if retrieval.dataset_fingerprint != expected_dataset_fingerprint:
            raise ValueError("retrieval artifact dataset fingerprint is incompatible")
        if retrieval.run_fingerprint != artifact_fingerprint(retrieval):
            raise ValueError("retrieval artifact fingerprint is invalid")
        known_ids = {case.id for case in dataset.cases}
        if {case.case_id for case in retrieval.cases} - known_ids:
            raise ValueError("retrieval artifact contains unknown case IDs")
        if retrieval.run_id != run_id:
            self.repository.save_retrieval(retrieval.model_copy(update={"run_id": run_id}))

        golden_by_id = {case.id: case for case in dataset.cases}
        generated_cases: list[GenerationCaseArtifact] = []
        errors: list[str] = []
        for source in retrieval.cases:
            golden = golden_by_id[source.case_id]
            if source.retrieval is None:
                message = f"{source.case_id}: retrieval evidence is unavailable"
                errors.append(message)
                generated_cases.append(
                    GenerationCaseArtifact(
                        case_id=source.case_id,
                        generation=None,
                        error=message,
                    )
                )
                continue
            hits = [item.hit for item in source.retrieval.hits]
            try:
                generated = self.chat.generate_from_hits(
                    source.retrieval.question,
                    hits,
                    source.retrieval.request_id,
                )
                deterministic_scores = score_generation_case(
                    golden,
                    answer=generated.answer,
                    cited_chunk_ids={
                        item.chunk_id for item in generated.citations
                    },
                    retrieved_chunk_ids={hit.chunk.id for hit in hits},
                    retrieval_latency_ms=source.retrieval.latency_ms,
                    generation_latency_ms=generated.latency_ms,
                )
                if deterministic_scores["citation_validity"] != 1.0:
                    errors.append(
                        f"{source.case_id}: blocking invariant failed: citation_validity"
                    )
                generated_cases.append(
                    GenerationCaseArtifact(
                        case_id=source.case_id,
                        generation=generated,
                        deterministic_scores=deterministic_scores,
                    )
                )
            except Exception as exc:
                message = f"{source.case_id}: {type(exc).__name__}: {exc}"
                errors.append(message)
                generated_cases.append(
                    GenerationCaseArtifact(
                        case_id=source.case_id,
                        generation=None,
                        error=message,
                    )
                )

        draft = GenerationRun(
            run_id=run_id,
            retrieval_run_fingerprint=retrieval.run_fingerprint,
            configuration=self.runtime_configuration,
            cases=generated_cases,
            run_fingerprint="",
        )
        generation = draft.model_copy(
            update={"run_fingerprint": artifact_fingerprint(draft)}
        )
        semantic_scores: dict[str, dict[str, float | None]] = {}
        if request.run_ragas:
            if self.semantic_judge is None:
                errors.append("Ragas requested but semantic judge is unavailable")
            else:
                batch = self.semantic_judge.score_generation(retrieval, generation)
                semantic_scores = batch.scores
                errors.extend(
                    f"{case_id}: {message}"
                    for case_id, messages in batch.errors.items()
                    for message in messages
                )
        self.repository.save_generation(generation)
        successful_ids = {
            item.case_id
            for item in generation.cases
            if item.generation is not None
        }
        aggregates = segment_aggregates(
            [case for case in dataset.cases if case.id in successful_ids],
            [
                item.deterministic_scores | semantic_scores.get(item.case_id, {})
                for item in generation.cases
                if item.generation is not None
            ],
        )
        case_scores = {
            item.case_id: item.deterministic_scores
            | semantic_scores.get(item.case_id, {})
            for item in generation.cases
        }
        status = "complete" if not errors else "incomplete"
        return EvaluationReport(
            run_id=run_id,
            mode=request.mode,
            status=status,
            dataset_size=len(dataset.cases),
            evaluated_cases=len(retrieval.cases),
            validation=validation.model_dump(mode="json"),
            aggregates=aggregates,
            target_comparison=compare_to_target(aggregates),
            case_scores=case_scores,
            errors=errors,
            artifact_ids={
                "retrieval_run": retrieval.run_fingerprint,
                "generation_run": generation.run_fingerprint,
            },
            baseline_eligible=False,
        )

    def _run_e2e(
        self,
        request: EvaluationRequest,
        dataset: GoldenDataset,
        selected: list[GoldenCase],
        validation: GoldenValidationReport,
        run_id: str,
    ) -> EvaluationReport:
        if request.ingestion_source is not None:
            _document, chunks = self._ingest_source(request)
            validation = validate_golden_dataset(
                dataset,
                request.canonical_source,
                chunks=chunks,
                audit_root=request.golden_dir.parent,
            )
            if validation.errors:
                raise ValueError(
                    "; ".join(issue.message for issue in validation.errors)
                )
        retrieval_report = self._retrieval_report(
            request,
            dataset,
            selected,
            validation,
            run_id,
        )
        generation_request = request.model_copy(
            update={"mode": EvaluationMode.GENERATION, "from_run": run_id}
        )
        generation_report = self._generation_report(
            generation_request,
            dataset,
            validation,
            run_id,
        )
        errors = retrieval_report.errors + generation_report.errors
        status = "complete" if not errors else "incomplete"
        baseline_eligible = (
            status == "complete"
            and request.baseline_candidate
            and validation.full_conformance
            and request.golden_dir == DEFAULT_GOLDEN_DIR
            and request.golden_files == []
            and request.canonical_source == DEFAULT_CANONICAL_SOURCE
            and len(dataset.cases) == 100
            and len(selected) == 100
        )
        return EvaluationReport(
            run_id=run_id,
            mode=EvaluationMode.E2E,
            status=status,
            dataset_size=len(dataset.cases),
            evaluated_cases=len(selected),
            validation=validation.model_dump(mode="json"),
            aggregates={
                "retrieval": retrieval_report.aggregates,
                "generation": generation_report.aggregates,
            },
            target_comparison={
                "retrieval": retrieval_report.target_comparison,
                "generation": generation_report.target_comparison,
            },
            case_scores={
                case_id: retrieval_report.case_scores.get(case_id, {})
                | generation_report.case_scores.get(case_id, {})
                for case_id in (
                    retrieval_report.case_scores.keys()
                    | generation_report.case_scores.keys()
                )
            },
            errors=errors,
            artifact_ids=(
                retrieval_report.artifact_ids | generation_report.artifact_ids
            ),
            baseline_eligible=baseline_eligible,
        )
