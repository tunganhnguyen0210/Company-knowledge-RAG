# Test Suite Documentation

Primary test-context entry point for humans and Coding Agents.

## 1. Test Categories

- **unit** (`tests/unit/`): Tests one function, class, policy, parser, or isolated module. Uses mocks, fakes, or in-memory stores. Must avoid live external services (Gemini, OpenAI, Jina, Qdrant, Langfuse, or network access).
- **component** (`tests/component/`): Connects multiple real internal modules while keeping external services fake/mocked. Validates application-level boundaries (e.g. FastAPI `TestClient`, RAG pipelines).
- **evaluation datasets** (`evaluation/golden_set/`): Golden-set benchmark datasets kept separate from software tests. Software tests for evaluation code live in `tests/unit/evaluation/`.

## 2. Source-to-Test Map

```text
src/api/**             → tests/component/api/**
src/evaluation/**      → tests/unit/evaluation/**
src/generation/**      → tests/unit/generation/**
src/ingestion/**       → tests/unit/ingestion/**
src/observability/**   → tests/unit/observability/**
src/prompts/**         → tests/unit/prompts/**
src/providers/**       → tests/unit/providers/**
src/retrieval/**       → tests/unit/retrieval/**
src/storage/**         → tests/unit/storage/**
Golden-set data        → evaluation/golden_set/**
```

## 3. Commands

### One file
```bash
uv run pytest tests/unit/generation/test_citation_gate.py -q
```

### One module
```bash
uv run pytest tests/unit/generation -q
```

### Component tests
```bash
uv run pytest tests/component -q
```

### Full test suite
```bash
uv run pytest -q
```

### Full verification
```bash
uv run ruff check .
uv run mypy
uv run pytest -q
```

## 4. Efficient Test Execution

1. In TDD, run the smallest test that proves red, then rerun it after the relevant change to prove green.
2. Record each successful command and the source, test, configuration, and dependency surface it covers.
3. Treat that evidence as fresh while its covered surface remains unchanged; do not rerun a passing command merely because one or two minutes elapsed.
4. Expand to another scope only when a failure, relevant edit, or coupled contract leaves a concrete risk unproven. After a later failure is fixed, rerun the failed command and the last passing scope that the break could have invalidated.
5. Run full verification once on the final tree only when the plan or acceptance contract requires it; reuse an identical final-tree result instead of repeating it.

## 5. Adding a Regression Test

1. Identify the affected production module.
2. Read the nearest existing tests.
3. Add the test to unit or component.
4. Reproduce the bug with a failing test.
5. Apply the smallest production fix.
6. Run the targeted test.
7. Apply the efficient-execution rules above; broader scopes require a concrete unproven risk.

## 6. Test Support

Reusable helpers are organized under `tests/support/`:
- `tests/support/builders.py`: Domain object construction helpers (e.g. `make_chunk`).
- `tests/support/providers.py`: Shared deterministic provider fakes (`CitedProvider`, `UncitedProvider`, etc.).
- `tests/support/tracing.py`: Shared tracing test doubles (`RecordingTracer`, `RecordingObservation`).

## 7. Golden-Set Policy

Do not modify `evaluation/golden_set/` unless the task explicitly concerns evaluation data.
