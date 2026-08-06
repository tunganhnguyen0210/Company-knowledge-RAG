from datetime import UTC, datetime
from pathlib import Path

from domain.schemas import Chunk, DocumentStatus, SearchHit, SourceCoordinates
from evaluation.artifacts import (
    GenerationCaseArtifact,
    GenerationRun,
    RetrievalCaseArtifact,
    RetrievalRun,
    artifact_fingerprint,
    fingerprint,
)
from evaluation.golden import GoldenType, load_golden_dataset
from generation.execution import GenerationExecution, RankedHit, RetrievalExecution


def make_chunk(
    *,
    chunk_id: str = "chunk-1",
    text: str = "retrieved original text",
    position: int = 0,
    coordinates: SourceCoordinates | None = None,
) -> Chunk:
    return Chunk(
        id=chunk_id,
        document_id="document-1",
        version=1,
        text=text,
        content_hash="chunk-hash",
        source_name="01_2021_ND-CP_283247.docx",
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        status=DocumentStatus.READY,
        position=position,
        coordinates=coordinates
        or SourceCoordinates(
            doc_id="01_2021_ND-CP_283247.md", chapter="Chương I", article="Điều 1"
        ),
    )


def make_retrieval_run(
    *,
    run_id: str = "retrieval-1",
    dataset_scope: str = "partial",
    golden_dir: Path = Path("evaluation/golden_set"),
    canonical_source: Path = Path("data/extracted/01_2021_ND-CP_283247.md"),
) -> RetrievalRun:
    source_file = golden_dir / "golden_set_direct_lookup.json"
    dataset = load_golden_dataset(
        golden_dir,
        files=None if dataset_scope == "full" else [source_file],
    )
    hit = SearchHit(chunk=make_chunk(), score=0.9)
    case = RetrievalCaseArtifact(
        case_id="DL-001",
        type=GoldenType.DIRECT_LOOKUP,
        difficulty="easy",
        expected_answer="golden reference",
        golden_contexts=["retrieved original text"],
        retrieval=RetrievalExecution(
            question="golden question",
            request_id="request-1",
            hits=[RankedHit(rank=1, hit=hit)],
            latency_ms=1.0,
        ),
    )
    draft = RetrievalRun(
        run_id=run_id,
        created_at=datetime(2026, 8, 5, tzinfo=UTC),
        dataset_fingerprint=fingerprint(
            [case.model_dump(mode="json") for case in dataset.cases]
        ),
        golden_dir=golden_dir,
        dataset_source_files=dataset.source_files,
        dataset_scope=dataset.scope,
        canonical_source=canonical_source,
        index_snapshot_fingerprint="snapshot-fingerprint",
        configuration={"top_k": 5},
        cases=[case],
        run_fingerprint="",
    )
    return draft.model_copy(update={"run_fingerprint": artifact_fingerprint(draft)})


def make_generation_run(*, retrieval: RetrievalRun | None = None) -> GenerationRun:
    source = retrieval or make_retrieval_run()
    case = GenerationCaseArtifact(
        case_id="DL-001",
        generation=GenerationExecution(
            answer="generated answer [C1].",
            citations=[],
            structured_response={"answer": "generated answer [C1].", "citations": [1]},
            provider="fake",
            model="fake-model",
            prompt_version="v1",
            usage={},
            latency_ms=2.0,
        ),
    )
    draft = GenerationRun(
        run_id=source.run_id,
        created_at=datetime(2026, 8, 5, tzinfo=UTC),
        retrieval_run_fingerprint=source.run_fingerprint,
        configuration={"prompt_version": "v1", "model": "fake-model"},
        cases=[case],
        run_fingerprint="",
    )
    return draft.model_copy(update={"run_fingerprint": artifact_fingerprint(draft)})
