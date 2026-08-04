# Ingestion Langfuse Latency Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reliably flush existing ingestion latency observations to Langfuse when the batch-ingestion CLI exits, including after a document-processing failure.

**Architecture:** `IngestionService` already opens an `ingestion` observation containing `parse`, `chunking`, `indexing`, and `registry` child spans with `latency_ms` metadata. Keep this pipeline unchanged. Add process-scope cleanup in `src.cli.ingest` so its shared application tracer flushes after the path loop exits normally or raises.

**Tech Stack:** Python 3.12, argparse CLI, pytest, Langfuse Python SDK.

## Global Constraints

- Do not add console latency output, a second telemetry backend, or new configuration.
- Do not change the Jina retry policy, Qdrant behavior, registry behavior, or document output format.
- Preserve the original ingestion exception and non-zero process exit after cleanup.
- Flush exactly once for each invocation of `src.cli.ingest` after `create_app` succeeds.

---

## File Structure

- `src/cli.py` owns command-line ingestion orchestration and will own process-scope tracer cleanup.
- `tests/test_cli.py` will isolate CLI behavior by substituting a fake FastAPI-like application with a recording tracer and ingestion service.

### Task 1: Flush the shared tracer when the ingest CLI exits

**Files:**
- Create: `tests/test_cli.py`
- Modify: `src/cli.py:29-40`

**Interfaces:**
- Consumes: `src.api.app.create_app(settings) -> FastAPI`, whose `app.state` has `ingestion` and `tracer`.
- Produces: `src.cli.ingest() -> None`, which calls `app.state.tracer.flush() exactly once after either a completed or failed ingestion loop.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_cli.py` with a fake application and two behavioral tests:

```python
from __future__ import annotations

from types import SimpleNamespace

import pytest

import cli


class RecordingTracer:
    def __init__(self) -> None:
        self.flush_calls = 0

    def flush(self) -> None:
        self.flush_calls += 1


class RecordingIngestion:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error

    def ingest_bytes(self, filename: str, content: bytes) -> SimpleNamespace:
        if self.error is not None:
            raise self.error
        return SimpleNamespace(source_name=filename, status="ready", version=1, id="doc-1")


def _app(ingestion: RecordingIngestion, tracer: RecordingTracer) -> SimpleNamespace:
    return SimpleNamespace(state=SimpleNamespace(ingestion=ingestion, tracer=tracer))


def test_ingest_flushes_tracer_after_success(tmp_path, monkeypatch) -> None:
    seed = tmp_path / "policy.md"
    seed.write_text("Policy text", encoding="utf-8")
    tracer = RecordingTracer()
    monkeypatch.setattr(cli, "Settings", lambda: object())
    monkeypatch.setattr(cli, "create_app", lambda settings: _app(RecordingIngestion(), tracer))
    monkeypatch.setattr("sys.argv", ["company-rag-ingest", str(seed)])

    cli.ingest()

    assert tracer.flush_calls == 1


def test_ingest_flushes_tracer_before_reraising_ingestion_error(tmp_path, monkeypatch) -> None:
    seed = tmp_path / "policy.md"
    seed.write_text("Policy text", encoding="utf-8")
    tracer = RecordingTracer()
    error = RuntimeError("embedding rate limited")
    monkeypatch.setattr(cli, "Settings", lambda: object())
    monkeypatch.setattr(cli, "create_app", lambda settings: _app(RecordingIngestion(error), tracer))
    monkeypatch.setattr("sys.argv", ["company-rag-ingest", str(seed)])

    with pytest.raises(RuntimeError, match="embedding rate limited"):
        cli.ingest()

    assert tracer.flush_calls == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `rtk proxy uv run pytest -p no:cacheprovider tests/test_cli.py -q`

Expected: the success test fails with `assert 0 == 1`, and the failure-path test also reports that no tracer flush occurred. The `RuntimeError` assertion itself passes, proving the test exercises the intended path.

- [ ] **Step 3: Write the minimal implementation**

Replace the loop in `src/cli.py` with the following cleanup boundary; do not catch or translate exceptions:

```python
    try:
        for path in paths:
            if path.suffix.lower() not in {".md", ".txt", ".pdf", ".docx"}:
                continue
            document = app.state.ingestion.ingest_bytes(path.name, path.read_bytes())
            print(f"{document.source_name}: {document.status} v{document.version} ({document.id})")
    finally:
        app.state.tracer.flush()
```

- [ ] **Step 4: Run the focused tests to verify they pass**

Run: `rtk proxy uv run pytest -p no:cacheprovider tests/test_cli.py -q`

Expected: `2 passed` and exit code 0.

- [ ] **Step 5: Run tracing regression coverage**

Run: `rtk proxy uv run pytest -p no:cacheprovider tests/test_cli.py tests/test_ingestion.py tests/test_tracing.py -q`

Expected: all selected tests pass, including `test_full_ingestion_trace_contains_lifecycle_data`.

- [ ] **Step 6: Commit the implementation**

```powershell
rtk git add src/cli.py tests/test_cli.py
rtk git commit -m "fix: flush ingestion spans on CLI exit"
```

Expected: a commit containing only the CLI cleanup and its focused tests.

### Task 2: Validate live export during the resumed seed batch

**Files:**
- Modify: none
- Verify: `data/registry.json`, Qdrant Cloud collection `company_knowledge`, Langfuse observations

**Interfaces:**
- Consumes: the committed Task 1 CLI behavior and `TRACE_MODE=full` Langfuse configuration.
- Produces: Langfuse observations named `ingestion`, `parse`, `chunking`, `indexing`, and `registry`, with step latency available through calculated duration and `latency_ms` metadata.

- [ ] **Step 1: Wait for Jina token capacity, then resume idempotently**

Run: `rtk proxy uv run company-rag-ingest .\\data\\seed`

Expected: already-ready documents are skipped; remaining supported seed documents are ingested until completion or a provider error. If Jina returns a 429, stop the command and resume after the provider's rolling one-minute token window clears; do not alter retry settings.

- [ ] **Step 2: Query Langfuse observations from this run**

Run a read-only `langfuse-cli api observations list` query scoped to the run time and `development` environment, selecting `basic,time,metadata,metrics,trace_context` fields.

Expected: each completed seed document has an `ingestion` parent and `parse`, `chunking`, `indexing`, and `registry` child observations. Child duration is available as Langfuse `latency`; metadata includes `latency_ms`, document identity, and chunk count where applicable.

- [ ] **Step 3: Verify ingestion state and retrieval**

Run the existing evaluation command: `rtk proxy uv run company-rag-evaluate`

Expected: report its exit status and output. Separately count registry entries by status and Qdrant points, then run representative security-policy, remote-work, and employee-handbook searches through `QdrantChunkStore.search()`. Report ranks and scores without claiming a quality threshold that was not specified.
