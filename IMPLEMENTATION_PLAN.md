# Implementation Plan: Test Folder Hierarchy Reorganization

## Tasks

- [x] Task 1: Phase 1 — Create directory structure, `tests/README.md`, update `pyproject.toml` pytest configuration, and update `AGENTS.md`.
  - **Files/Areas**: `tests/unit/`, `tests/component/`, `tests/integration/`, `tests/support/`, `tests/README.md`, `pyproject.toml`, `AGENTS.md`
  - **Validation Command**: `uv run pytest -m "not integration" -q`
  - **Acceptance Criteria**: Directories exist, `tests/README.md` created, `pyproject.toml` contains pytest testpaths/pythonpath/markers/basetemp, `AGENTS.md` updated with testing rules.
  - **Status**: done

- [x] Task 2: Phase 2 — Move non-split test files to unit, component, and integration subdirectories.
  - **Files/Areas**: `tests/test_settings.py`, `tests/test_prompt*.py`, `tests/test_gemini*.py`, `tests/test_generic_key_rotation.py`, `tests/test_jina*.py`, `tests/test_key_rotation.py`, `tests/test_provider_selection.py`, `tests/test_providers.py`, `tests/test_hybrid.py`, `tests/test_qdrant_store.py`, `tests/test_retrieval.py`, `tests/test_evaluation.py`, `tests/test_tracing.py`, `tests/test_api.py`, `tests/test_cli.py`, `tests/integration/test_qdrant_acl.py`
  - **Validation Command**: `uv run pytest -m "not integration" -q`
  - **Acceptance Criteria**: Simple files moved to `tests/unit/*`, `tests/component/*`, and `tests/integration/qdrant/test_document_replacement.py`. Imports work correctly.
  - **Status**: done

- [x] Task 3: Phase 3 — Extract shared test support modules and update imports & doubles.
  - **Files/Areas**: `tests/support/tracing.py`, `tests/support/providers.py`, `tests/support/builders.py`, `tests/unit/providers/test_jina_key_rotation.py`
  - **Validation Command**: `uv run pytest tests/unit/providers/ -q`
  - **Acceptance Criteria**: Shared `RecordingTracer`, provider fakes, and `make_chunk` builder extracted to `tests/support/`. `test_jina_key_rotation.py` uses `make_chunk` and passes.
  - **Status**: done

- [x] Task 4: Phase 4.1 — Split `tests/test_ingestion.py` into modular unit and component test files.
  - **Files/Areas**: `tests/unit/ingestion/test_parser_pdf.py`, `tests/unit/ingestion/test_parser_docx.py`, `tests/unit/ingestion/test_service.py`, `tests/unit/ingestion/test_tracing.py`, `tests/component/api/test_app_wiring.py`
  - **Validation Command**: `uv run pytest tests/unit/ingestion tests/component/api/test_app_wiring.py -q`
  - **Acceptance Criteria**: `test_ingestion.py` deleted; PDF, DOCX, service, tracing, and app wiring tests split into designated locations; all tests pass.
  - **Status**: done

- [x] Task 5: Phase 4.2 — Split `tests/test_generation.py` into modular unit and component test files.
  - **Files/Areas**: `tests/unit/generation/test_citation_gate.py`, `tests/unit/generation/test_abstention.py`, `tests/unit/generation/test_tracing.py`, `tests/component/rag/test_retrieve_and_answer.py`
  - **Validation Command**: `uv run pytest tests/unit/generation tests/component/rag -q`
  - **Acceptance Criteria**: `test_generation.py` deleted; citation gate, abstention, tracing, and retrieve-and-answer tests split into designated locations; all tests pass.
  - **Status**: done

- [x] Task 6: Phase 5 & 6 — Final verification, linting, type-checking, and full test suite execution.
  - **Files/Areas**: Entire workspace
  - **Validation Command**: `uv run ruff check . && uv run mypy && uv run pytest -m "not integration" -q`
  - **Acceptance Criteria**: Ruff passes, mypy passes, fast pytest suite passes with 0 failures, Qdrant integration tests skip cleanly or pass if enabled.
  - **Status**: done
