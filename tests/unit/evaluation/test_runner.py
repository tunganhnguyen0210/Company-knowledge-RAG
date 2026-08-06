from pathlib import Path

import pytest
from pydantic import ValidationError

from domain.schemas import Document, DocumentStatus, SearchHit, SourceCoordinates
from evaluation.artifacts import EvaluationMode, EvaluationRequest
from evaluation.golden import load_golden_dataset
from evaluation.repository import InMemoryRunRepository
from evaluation.runner import EvaluationRunner
from generation.execution import GenerationExecution, RankedHit, RetrievalExecution
from tests.support.evaluation_fakes import make_chunk, make_retrieval_run


class ExplodingDependency:
    def __getattr__(self, name: str):
        raise AssertionError(f"runtime dependency used during validation: {name}")


class FakeRegistry:
    def __init__(self) -> None:
        self.document = Document(
            id="document-1",
            version=1,
            content_hash="raw-hash",
            source_name="01_2021_ND-CP_283247.docx",
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            status=DocumentStatus.READY,
            metadata={"canonical_doc_id": "01_2021_ND-CP_283247.md"},
        )

    def find_by_source(self, source_name: str) -> Document | None:
        return self.document if source_name == self.document.source_name else None


class FakeStore:
    def __init__(self) -> None:
        dataset = load_golden_dataset(Path("evaluation/golden_set"))
        self.chunks = [
            make_chunk(
                chunk_id=f"{case.id}-{context_index}",
                text=context.golden_truth_context,
                position=position,
                coordinates=SourceCoordinates(
                    doc_id=context.golden_metadata.doc_id,
                    chapter=context.golden_metadata.chapter,
                    article=context.golden_metadata.article,
                ),
            )
            for position, (case, context_index, context) in enumerate(
                (case, context_index, context)
                for case in dataset.cases
                for context_index, context in enumerate(case.golden_truth_contexts)
            )
        ]
        self.chunk = self.chunks[0]
        self.search_calls = 0

    def list_document_chunks(self, document_id: str, version: int | None = None):
        return self.chunks

    def search(self, query: str, limit: int = 5):
        self.search_calls += 1
        return [SearchHit(chunk=self.chunk, score=0.9)]


class FakeChat:
    def __init__(self, store: FakeStore, *, fail_first_retrieval: bool = False) -> None:
        self.store = store
        self.fail_first_retrieval = fail_first_retrieval
        self.retrieval_calls = 0

    def retrieve(self, question: str, request_id: str | None = None) -> RetrievalExecution:
        self.retrieval_calls += 1
        if self.fail_first_retrieval and self.retrieval_calls == 1:
            raise RuntimeError("controlled retrieval failure")
        hit = SearchHit(chunk=self.store.chunk, score=0.9)
        return RetrievalExecution(
            question=question,
            request_id=request_id or f"request-{self.retrieval_calls}",
            hits=[RankedHit(rank=1, hit=hit)],
            latency_ms=1.0,
        )

    def generate_from_hits(
        self,
        question: str,
        hits: list[SearchHit],
        request_id: str | None = None,
    ) -> GenerationExecution:
        return GenerationExecution(
            answer="Answer [C1].",
            citations=[],
            structured_response={"answer": "Answer [C1].", "citations": [1]},
            provider="fake",
            model="fake-model",
            prompt_version="v1",
            usage={},
            latency_ms=2.0,
        )


class FakeIngestion:
    def __init__(self) -> None:
        self.calls = 0

    def ingest_bytes(self, *args: object, **kwargs: object) -> Document:
        self.calls += 1
        return FakeRegistry().document


def _runner(tmp_path: Path, *, fail_if_runtime_used: bool = False) -> EvaluationRunner:
    repository = InMemoryRunRepository()
    if fail_if_runtime_used:
        exploding = ExplodingDependency()
        return EvaluationRunner(
            ingestion=exploding,
            registry=exploding,
            store=exploding,
            chat=exploding,
            repository=repository,
            runtime_configuration={},
            semantic_judge=None,
        )
    store = FakeStore()
    return EvaluationRunner(
        ingestion=None,
        registry=FakeRegistry(),
        store=store,
        chat=FakeChat(store),
        repository=repository,
        runtime_configuration={"qdrant_collection": "test"},
        semantic_judge=None,
    )


def _runner_with_one_retrieval_failure(tmp_path: Path) -> EvaluationRunner:
    runner = _runner(tmp_path)
    runner.chat = FakeChat(runner.store, fail_first_retrieval=True)
    return runner


def _runner_with_saved_retrieval(tmp_path: Path) -> tuple[EvaluationRunner, FakeStore]:
    runner = _runner(tmp_path)
    runner.repository.save_retrieval(make_retrieval_run())
    return runner, runner.store


def _successful_runner(tmp_path: Path) -> EvaluationRunner:
    return _runner(tmp_path)


def test_validate_mode_never_builds_runtime_dependencies(tmp_path) -> None:
    runner = _runner(tmp_path, fail_if_runtime_used=True)

    report = runner.run(EvaluationRequest(mode=EvaluationMode.VALIDATE))

    assert report.mode is EvaluationMode.VALIDATE
    assert report.evaluated_cases == 0
    assert report.status == "complete"


def test_retrieval_mode_continues_after_case_error(tmp_path) -> None:
    runner = _runner_with_one_retrieval_failure(tmp_path)

    report = runner.run(EvaluationRequest(mode=EvaluationMode.RETRIEVAL, limit=2))

    assert report.evaluated_cases == 2
    assert report.status == "incomplete"
    assert len(report.errors) == 1
    assert runner.repository.retrieval_runs


def test_generation_mode_reuses_saved_hits_without_search(tmp_path) -> None:
    runner, store = _runner_with_saved_retrieval(tmp_path)

    report = runner.run(EvaluationRequest(mode=EvaluationMode.GENERATION, from_run="retrieval-1"))

    assert report.status == "complete"
    assert store.search_calls == 0


def test_generation_request_rejects_replacement_selection() -> None:
    with pytest.raises(ValidationError, match="inherits the saved retrieval selection"):
        EvaluationRequest(
            mode=EvaluationMode.GENERATION,
            from_run="retrieval-1",
            canonical_source=Path("replacement.md"),
        )


def test_generation_inherits_full_golden_and_canonical_selection(tmp_path: Path) -> None:
    golden_dir = tmp_path / "golden"
    golden_dir.mkdir()
    for source in Path("evaluation/golden_set").glob("*.json"):
        (golden_dir / source.name).write_bytes(source.read_bytes())
    canonical_source = tmp_path / "01_2021_ND-CP_283247.md"
    canonical_source.write_bytes(
        Path("data/extracted/01_2021_ND-CP_283247.md").read_bytes()
    )
    runner, store = _runner_with_saved_retrieval(tmp_path)
    runner.repository.retrieval_runs.clear()
    runner.repository.save_retrieval(
        make_retrieval_run(
            dataset_scope="full",
            golden_dir=golden_dir,
            canonical_source=canonical_source,
        )
    )

    report = runner.run(
        EvaluationRequest(mode=EvaluationMode.GENERATION, from_run="retrieval-1")
    )

    manifest = runner.repository.manifests[report.run_id]
    assert report.status == "complete"
    assert store.search_calls == 0
    assert manifest.arguments["golden_dir"] == str(golden_dir)
    assert manifest.arguments["canonical_source"] == str(canonical_source)


def test_e2e_reuses_existing_index_unless_ingest_is_explicit(tmp_path) -> None:
    runner = _runner(tmp_path)
    ingestion = FakeIngestion()
    runner.ingestion = ingestion

    report = runner.run(EvaluationRequest(mode=EvaluationMode.E2E, limit=1))

    assert report.status == "complete"
    assert ingestion.calls == 0
    assert runner.repository.report_save_calls == 1


def test_only_full_complete_e2e_is_baseline_eligible(tmp_path) -> None:
    runner = _successful_runner(tmp_path)
    full = runner.run(EvaluationRequest(mode=EvaluationMode.E2E))
    limited = runner.run(EvaluationRequest(mode=EvaluationMode.E2E, limit=5))
    assert full.baseline_eligible is True
    assert limited.baseline_eligible is False


def test_e2e_ingestion_saves_one_immutable_snapshot(tmp_path: Path) -> None:
    source = tmp_path / "01_2021_ND-CP_283247.docx"
    source.write_bytes(b"fake-docx")
    runner = _runner(tmp_path)
    runner.ingestion = FakeIngestion()

    report = runner.run(
        EvaluationRequest(mode=EvaluationMode.E2E, ingestion_source=source, limit=1)
    )

    assert report.status == "complete"
    assert runner.repository.snapshot_save_calls == 1


@pytest.mark.parametrize("mode", [EvaluationMode.VALIDATE, EvaluationMode.GENERATION])
def test_preflight_failures_are_retained_as_reports(
    tmp_path: Path,
    mode: EvaluationMode,
) -> None:
    runner = _runner(tmp_path)
    request = (
        EvaluationRequest(mode=mode, canonical_source=tmp_path / "missing.md")
        if mode is EvaluationMode.VALIDATE
        else EvaluationRequest(mode=mode, from_run="missing-retrieval")
    )

    report = runner.run(request)

    assert report.status == "failed"
    assert report.errors[0].startswith("FileNotFoundError:")
    assert report.report_path is not None
    assert runner.repository.report_save_calls == 1
