# Full Ingestion, Retrieval, and Answer Tracing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Record the complete ingestion and RAG answer lifecycle in Langfuse when full tracing is explicitly enabled, while preserving safe metadata-only and off modes.

**Architecture:** Keep Langfuse isolated behind `Tracer`. Add serialization and redaction helpers there, then inject one tracer into `IngestionService`. Chat updates its existing retrieval and generation spans with structured Top-K and final-answer metadata before each span closes.

**Tech Stack:** Python 3.11, FastAPI, Pydantic v2, Langfuse SDK v3, pytest, Docker Compose.

## Global Constraints

- `TRACE_MODE=off` creates no Langfuse observations.
- `TRACE_MODE=metadata-only` must never emit question, parsed text, chunk text, prompt text, context text, model output, or final answer.
- `TRACE_MODE=full` requires `ALLOW_SENSITIVE_TRACING=true` and includes the complete sensitive payloads below.
- Upload API and CLI ingestion use the same service-level tracing path.
- Preserve idempotent ingestion, existing API contracts, and no-Langfuse operation.
- Do not alter or commit unrelated worktree changes.

---

## File Structure

- Modify: `src/observability/tracing.py` — privacy-aware payload generation and safe observation updates.
- Create: `tests/test_tracing.py` — unit tests for trace payload mode behavior.
- Modify: `src/generation/service.py` and `tests/test_generation.py` — ranked Top-K plus generation prompt, response, citations, and final answer.
- Modify: `src/ingestion/service.py`, `src/api/app.py`, and `tests/test_ingestion.py` — service-level ingest traces used by both API and CLI.
- Modify: `docker-compose.langfuse.yml`, `README.md`, `docs/architectures/05-observability-evaluation-and-operations.md`, and `tests/test_settings.py` — deployment contract and documentation.

### Task 1: Make Tracer payloads safe and testable

**Files:**
- Modify: `src/observability/tracing.py`
- Create: `tests/test_tracing.py`

**Interfaces:**
- Produces: `Tracer.safe_payload(payload: dict[str, Any]) -> dict[str, Any]`, recursively redacting sensitive keys except in full mode.
- Produces: `Tracer.update(observation: Any, metadata: dict[str, Any]) -> None`, applying `safe_payload` before it calls the active observation.

- [ ] **Step 1: Write failing privacy-mode tests**

```python
def test_metadata_only_removes_sensitive_values_recursively() -> None:
    tracer = Tracer(Settings(trace_mode="metadata-only"))
    payload = tracer.safe_payload({
        "question": "secret question",
        "top_k": [{"chunk_id": "c1", "text": "secret chunk"}],
        "answer": "secret answer",
        "result_count": 1,
    })
    assert payload == {"top_k": [{"chunk_id": "c1"}], "result_count": 1}


def test_full_mode_preserves_sensitive_payload() -> None:
    tracer = Tracer(Settings(trace_mode="full", allow_sensitive_tracing=True))
    payload = {"question": "q", "context": ["c"], "answer": "a"}
    assert tracer.safe_payload(payload) == payload
```

- [ ] **Step 2: Run focused tests to verify they fail**

Run: `uv run pytest tests/test_tracing.py -v`

Expected: FAIL because recursive redaction is absent and the test file is new.

- [ ] **Step 3: Implement recursive redaction and safe updates**

```python
SENSITIVE_TRACE_KEYS = frozenset({
    "answer", "context", "parsed_text", "prompt", "question", "response",
    "system_instruction", "text", "user_prompt",
})

def safe_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
    return payload if self.mode is TraceMode.FULL else cast(dict[str, Any], self._redact(payload))

def _redact(self, value: Any) -> Any:
    if isinstance(value, dict):
        return {key: self._redact(item) for key, item in value.items()
                if key not in SENSITIVE_TRACE_KEYS}
    if isinstance(value, list):
        return [self._redact(item) for item in value]
    return value

def update(self, observation: Any, metadata: dict[str, Any]) -> None:
    if observation is not None and hasattr(observation, "update"):
        observation.update(metadata=self.safe_payload(metadata))
```

Apply `safe_payload` inside `span()` too.

- [ ] **Step 4: Add update coverage and run tests**

```python
def test_update_redacts_before_calling_observation() -> None:
    observation = RecordingObservation()
    Tracer(Settings(trace_mode="metadata-only")).update(
        observation, {"answer": "private", "result_count": 1}
    )
    assert observation.metadata == {"result_count": 1}
```

Run: `uv run pytest tests/test_tracing.py tests/test_settings.py -v`

Expected: PASS.

- [ ] **Step 5: Commit the tracer change**

```powershell
git add src/observability/tracing.py tests/test_tracing.py
git commit -m "feat: add privacy-aware tracing payloads"
```

### Task 2: Capture ranked Top-K retrieval and final answer

**Files:**
- Modify: `src/generation/service.py`
- Modify: `tests/test_generation.py`

**Interfaces:**
- Consumes: safe `Tracer.update` from Task 1.
- Produces: `top_k: list[dict[str, Any]]`, ordered exactly as `store.search()` returns.
- Produces: generation metadata fields `system_instruction`, `user_prompt`, `response`, `citations`, and `answer`.

- [ ] **Step 1: Write the failing recording-tracer test**

```python
def test_full_trace_records_ranked_top_k_and_final_answer() -> None:
    tracer = RecordingTracer()
    service = ChatService(store_with_two_chunks(), CitedProvider(), tracer, retrieval_limit=2)

    response = service.answer("Nghi phep?", Principal(roles={"employee"}))

    retrieval = tracer.updated("retrieval")
    assert [item["rank"] for item in retrieval["top_k"]] == [1, 2]
    assert retrieval["top_k"][0]["chunk_id"] == "doc:v1:0"
    assert retrieval["top_k"][0]["text"] == "Nhan vien duoc nghi 15 ngay."
    generation = tracer.updated("generation")
    assert generation["answer"] == response.answer
    assert generation["citations"] == ["C1"]
```

`RecordingTracer` implements `span`, `safe_payload`, and `update`; its span captures updates while active.

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `uv run pytest tests/test_generation.py::test_full_trace_records_ranked_top_k_and_final_answer -v`

Expected: FAIL because retrieval has no `top_k` and generation has no final result.

- [ ] **Step 3: Add serializers and update active spans**

```python
def _trace_hit(rank: int, hit: SearchHit) -> dict[str, Any]:
    chunk = hit.chunk
    return {
        "rank": rank, "score": hit.score, "chunk_id": chunk.id,
        "document_id": chunk.document_id, "version": chunk.version,
        "source_name": chunk.source_name, "section": chunk.section,
        "position": chunk.position, "content_hash": chunk.content_hash,
        "text": chunk.text,
    }
```

Update retrieval with `result_count`, `latency_ms`, and ordered `top_k`. Start generation with rendered `system_instruction`, `user_prompt`, question, context, and prompt version. Construct citations and citation-gated final answer before the generation context exits, then update it with provider/model/usage, `response=result.value.model_dump()`, citation IDs, and final answer.

- [ ] **Step 4: Add metadata-only and no-hit regression tests**

```python
def test_metadata_only_trace_omits_top_k_text_and_answer() -> None:
    response = service.answer("Nghi phep?", Principal(roles={"employee"}))
    assert "text" not in tracer.updated("retrieval")["top_k"][0]
    assert "answer" not in tracer.updated("generation")
    assert response.citations
```

Run: `uv run pytest tests/test_generation.py -v`

Expected: PASS, including the existing active-span assertion.

- [ ] **Step 5: Commit chat telemetry**

```powershell
git add src/generation/service.py tests/test_generation.py
git commit -m "feat: trace retrieval top-k and final answers"
```

### Task 3: Trace service-level ingestion for API and CLI

**Files:**
- Modify: `src/ingestion/service.py`
- Modify: `src/api/app.py`
- Modify: `tests/test_ingestion.py`

**Interfaces:**
- Consumes: `tracer: Tracer | None = None` in `IngestionService.__init__`.
- Produces: `ingestion` with child spans `parse`, `chunking`, optional `enrichment`, `indexing`, and `registry`.

- [ ] **Step 1: Write failing ingestion span tests**

```python
def test_full_ingestion_trace_contains_parsed_text_and_chunks(tmp_path: Path) -> None:
    tracer = RecordingTracer()
    service = IngestionService(
        DocumentRegistry(tmp_path / "registry.json"), MemoryChunkStore(), tracer=tracer
    )
    document = service.ingest_bytes("policy.md", b"# Leave\n\nNhan vien duoc nghi 15 ngay.")

    assert tracer.names == ["ingestion", "parse", "chunking", "indexing", "registry"]
    assert tracer.updated("parse")["parsed_text"] == "# Leave\n\nNhan vien duoc nghi 15 ngay."
    chunking = tracer.updated("chunking")
    assert chunking["chunk_count"] == 1
    assert chunking["chunks"][0]["text"] == "Nhan vien duoc nghi 15 ngay."
    assert chunking["document_id"] == document.id
```

Add the idempotent-path test:

```python
def test_idempotent_ingestion_trace_marks_skip_without_child_spans(tmp_path: Path) -> None:
    tracer = RecordingTracer()
    service = IngestionService(
        DocumentRegistry(tmp_path / "registry.json"), MemoryChunkStore(), tracer=tracer
    )
    content = b"Same policy"
    service.ingest_bytes("policy.md", content)
    tracer.clear()

    service.ingest_bytes("policy.md", content)

    assert tracer.names == ["ingestion"]
    assert tracer.updated("ingestion")["outcome"] == "idempotent_skip"
```

- [ ] **Step 2: Run ingestion tests to verify they fail**

Run: `uv run pytest tests/test_ingestion.py -v`

Expected: FAIL because `IngestionService` has no tracer or spans.

- [ ] **Step 3: Inject tracer and instrument service boundaries**

```python
def __init__(
    self,
    registry: DocumentRegistry,
    store: ChunkStore,
    upload_dir: Path | None = None,
    enricher: ChunkEnricher | None = None,
    tracer: Tracer | None = None,
) -> None:
    self.tracer = tracer or Tracer(Settings(trace_mode="off"))

with self.tracer.span("ingestion", {"source_name": filename, "file_bytes": len(content)}) as ingestion:
    # On an idempotent return, update ingestion with document ID, version,
    # content hash, and outcome="idempotent_skip" before returning.
    with self.tracer.span("parse", {"source_name": filename, "file_bytes": len(content)}) as parse:
        text, mime_type = parse_document(filename, content)
    self.tracer.update(parse, {
        "mime_type": mime_type,
        "parsed_characters": len(text),
        "parsed_text": text,
    })
```

Use separate contexts for chunking, optional enrichment, indexing, and registry. Chunking update includes `max_chars=1200`, `chunk_count`, and ordered chunk records with ID, document ID, version, position, section, hash, source, MIME type, and text. Record latency for each phase. Do not create `indexing` for non-ready documents; preserve write-before-publish and exception propagation.

In `create_app`, create one `Tracer(settings)` and inject it into both `IngestionService` and `ChatService`. The CLI already uses `create_app`, so it needs no independent telemetry code.

- [ ] **Step 4: Add metadata-only and enrichment tests**

```python
def test_metadata_only_ingestion_trace_redacts_parsed_and_chunk_text(tmp_path: Path) -> None:
    tracer = RecordingTracer(mode="metadata-only")
    service = IngestionService(
        DocumentRegistry(tmp_path / "registry.json"), MemoryChunkStore(), tracer=tracer
    )
    service.ingest_bytes("policy.md", b"Confidential content")

    assert "parsed_text" not in tracer.updated("parse")
    assert "text" not in tracer.updated("chunking")["chunks"][0]
```

Run: `uv run pytest tests/test_ingestion.py tests/test_api.py tests/test_generation.py -v`

Expected: PASS.

- [ ] **Step 5: Commit ingestion telemetry**

```powershell
git add src/ingestion/service.py src/api/app.py tests/test_ingestion.py
git commit -m "feat: trace ingestion and chunking lifecycle"
```

### Task 4: Correct deployment config, document the trace contract, and verify

**Files:**
- Modify: `docker-compose.langfuse.yml`
- Modify: `README.md`
- Modify: `docs/architectures/05-observability-evaluation-and-operations.md`
- Modify: `tests/test_settings.py`

**Interfaces:**
- Consumes: `LANGFUSE_HOST`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `TRACE_MODE`, `ALLOW_SENSITIVE_TRACING`.
- Produces: a Compose overlay whose environment names match `Settings`.

- [ ] **Step 1: Write the environment contract test**

```python
def test_settings_reads_langfuse_environment(monkeypatch) -> None:
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    monkeypatch.setenv("LANGFUSE_HOST", "http://langfuse:3000")

    settings = Settings(_env_file=None)

    assert settings.langfuse_public_key == "pk-test"
    assert settings.langfuse_host == "http://langfuse:3000"
```

- [ ] **Step 2: Run the settings test**

Run: `uv run pytest tests/test_settings.py::test_settings_reads_langfuse_environment -v`

Expected: PASS. It establishes the exact variable names Compose must pass.

- [ ] **Step 3: Correct Compose and documentation**

```yaml
environment:
  LANGFUSE_HOST: ${LANGFUSE_HOST:-http://host.docker.internal:3000}
  LANGFUSE_PUBLIC_KEY: ${LANGFUSE_PUBLIC_KEY}
  LANGFUSE_SECRET_KEY: ${LANGFUSE_SECRET_KEY}
  TRACE_MODE: ${TRACE_MODE:-metadata-only}
  ALLOW_SENSITIVE_TRACING: ${ALLOW_SENSITIVE_TRACING:-false}
```

Update README and architecture documentation with the approved hierarchy and fields. State explicitly that full mode includes parsed document text, chunks, Top-K, prompts, structured response, citations, and answer; metadata-only redacts all sensitive text.

- [ ] **Step 4: Run complete verification**

Run: `uv run pytest -v`

Expected: PASS.

Run: `uv run ruff check .`

Expected: PASS with no lint diagnostics.

Run: `uv run mypy`

Expected: PASS with no type errors.

Run: `docker compose -f docker-compose.yml -f docker-compose.langfuse.yml config`

Expected: API service environment includes all five exact Langfuse variable names.

- [ ] **Step 5: Commit configuration, documentation, and tests**

```powershell
git add docker-compose.langfuse.yml README.md docs/architectures/05-observability-evaluation-and-operations.md tests/test_settings.py
git commit -m "docs: document full RAG tracing"
```
