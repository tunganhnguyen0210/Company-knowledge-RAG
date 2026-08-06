# Test Folder Hierarchy Specification

## 1. Purpose

Restructure the existing test suite so that:

* Test location clearly reflects the production module being tested.
* Coding Agents can find relevant tests without scanning the entire repository.
* Unit, component, and infrastructure integration tests are clearly separated.
* Shared test doubles and builders are reusable.
* Golden-set evaluation data remains separate from software tests.
* The structure remains lightweight enough for an MVP.

This task is a structural refactor. Existing application behavior and test expectations must not change unless a test is proven to be invalid.

---

## 2. Scope

### In scope

* Reorganize files under `tests/`.
* Split broad test modules where they cover multiple independent boundaries.
* Create shared test-support modules.
* Add test documentation.
* Update pytest configuration.
* Update CI commands and paths where necessary.
* Preserve all existing test coverage and behavior.

### Out of scope

* Rewriting production architecture.
* Changing application behavior.
* Editing golden-set samples.
* Changing evaluation scoring logic.
* Adding a large test framework.
* Adding test-impact analysis.
* Adding CI sharding.
* Adding live LLM tests.
* Changing provider retry policies.
* Increasing or decreasing coverage thresholds unless explicitly requested.

---

## 3. Target Folder Structure

The final hierarchy must be:

```text
tests/
├── unit/
│   ├── evaluation/
│   │   └── test_scoring.py
│   │
│   ├── generation/
│   │   ├── test_abstention.py
│   │   ├── test_citation_gate.py
│   │   └── test_tracing.py
│   │
│   ├── ingestion/
│   │   ├── test_parser_docx.py
│   │   ├── test_parser_pdf.py
│   │   ├── test_service.py
│   │   └── test_tracing.py
│   │
│   ├── observability/
│   │   └── test_tracing.py
│   │
│   ├── prompts/
│   │   ├── test_prompt.py
│   │   └── test_prompt_loader.py
│   │
│   ├── providers/
│   │   ├── test_gemini_embeddings.py
│   │   ├── test_generic_key_rotation.py
│   │   ├── test_jina.py
│   │   ├── test_jina_key_rotation.py
│   │   ├── test_key_rotation.py
│   │   ├── test_provider_selection.py
│   │   └── test_providers.py
│   │
│   ├── retrieval/
│   │   ├── test_hybrid.py
│   │   ├── test_qdrant_store.py
│   │   └── test_retrieval.py
│   │
│   ├── storage/
│   │   └── test_registry.py
│   │
│   └── test_settings.py
│
├── component/
│   ├── api/
│   │   ├── test_api.py
│   │   ├── test_app_wiring.py
│   │   └── test_cli.py
│   │
│   └── rag/
│       └── test_retrieve_and_answer.py
│
├── integration/
│   └── qdrant/
│       └── test_document_replacement.py
│
├── support/
│   ├── builders.py
│   ├── providers.py
│   └── tracing.py
│
└── README.md
```

Create `__init__.py` files only when required for import stability. Prefer normal pytest test discovery without turning every folder into an application package.

---

## 4. Test Category Definitions

### 4.1 Unit tests

Location:

```text
tests/unit/
```

A unit test must:

* Test one function, class, policy, parser, or isolated module behavior.
* Avoid real external infrastructure.
* Avoid live HTTP requests.
* Avoid live LLM, embedding, reranking, Langfuse, or Qdrant services.
* Use mocks, fakes, stubs, temporary files, or in-memory stores.
* Be deterministic.
* Run quickly.

Examples:

* Parser behavior
* Citation validation
* Abstention logic
* Key rotation logic
* Provider selection
* Retrieval fusion
* Evaluation score calculation
* Settings validation
* Qdrant adapter behavior using a fake client

A test using `QdrantChunkStore` is still a unit test when the Qdrant client is manually constructed, mocked, or replaced with a fake object.

---

### 4.2 Component tests

Location:

```text
tests/component/
```

A component test must:

* Connect multiple real internal modules.
* Keep external services fake or mocked.
* Validate an application-level boundary.
* Be deterministic.
* Not require Docker or external credentials.

Examples:

* FastAPI application creation
* Upload document, then query through the API
* Retrieval followed by grounded generation
* CLI invoking application services
* Dependency wiring between ingestion, chat, storage, and tracing

A component test may use:

* FastAPI `TestClient`
* `MemoryChunkStore`
* Temporary registry files
* Stub generation providers
* Recording tracers

---

### 4.3 Integration tests

Location:

```text
tests/integration/
```

An integration test must:

* Use real external infrastructure.
* Be explicitly marked with `pytest.mark.integration`.
* Be skipped unless its required environment is enabled.
* Clean up all created resources.
* Avoid live paid LLM or embedding APIs unless a future explicit test category is added.

Current integration scope:

```text
Real local Qdrant only
```

The current Qdrant integration test must continue requiring:

```text
RUN_QDRANT_INTEGRATION=1
```

Integration tests must create unique collection names and delete collections in a `finally` block.

---

### 4.4 Evaluation datasets

The following directory must remain outside `tests/`:

```text
evaluation/
├── GOLDEN_SET_SPEC.md
└── golden_set/
```

Golden-set JSON files are evaluation datasets, not pytest test fixtures.

Do not move them into:

```text
tests/fixtures/
tests/data/
tests/evaluation/
```

Software tests for the evaluation runner belong under:

```text
tests/unit/evaluation/
```

Dataset content remains under:

```text
evaluation/golden_set/
```

---

## 5. Existing File Migration Map

Apply the following moves.

```text
tests/test_settings.py
→ tests/unit/test_settings.py
```

```text
tests/test_prompt.py
→ tests/unit/prompts/test_prompt.py

tests/test_prompt_loader.py
→ tests/unit/prompts/test_prompt_loader.py
```

```text
tests/test_gemini_embeddings.py
→ tests/unit/providers/test_gemini_embeddings.py

tests/test_generic_key_rotation.py
→ tests/unit/providers/test_generic_key_rotation.py

tests/test_jina.py
→ tests/unit/providers/test_jina.py

tests/test_jina_key_rotation.py
→ tests/unit/providers/test_jina_key_rotation.py

tests/test_key_rotation.py
→ tests/unit/providers/test_key_rotation.py

tests/test_provider_selection.py
→ tests/unit/providers/test_provider_selection.py

tests/test_providers.py
→ tests/unit/providers/test_providers.py
```

```text
tests/test_hybrid.py
→ tests/unit/retrieval/test_hybrid.py

tests/test_qdrant_store.py
→ tests/unit/retrieval/test_qdrant_store.py

tests/test_retrieval.py
→ tests/unit/retrieval/test_retrieval.py
```

```text
tests/test_evaluation.py
→ tests/unit/evaluation/test_scoring.py
```

```text
tests/test_tracing.py
→ tests/unit/observability/test_tracing.py
```

```text
tests/test_api.py
→ tests/component/api/test_api.py

tests/test_cli.py
→ tests/component/api/test_cli.py
```

```text
tests/integration/test_qdrant_acl.py
→ tests/integration/qdrant/test_document_replacement.py
```

Any existing storage registry tests must be moved to:

```text
tests/unit/storage/test_registry.py
```

If no storage registry test currently exists, do not create empty placeholder tests.

---

## 6. Required Split: `test_ingestion.py`

The existing `tests/test_ingestion.py` contains several independent behaviors and must be split.

### 6.1 `tests/unit/ingestion/test_parser_pdf.py`

Move tests related to:

* Scanned PDF detection
* Corrupt PDF rejection
* PDF parsing behavior
* PDF-specific MIME or parsing rules

Expected tests include behavior equivalent to:

```text
test_scanned_pdf_is_marked_needs_ocr
test_corrupt_pdf_is_rejected
```

Do not move service-level ingestion behavior into this file.

---

### 6.2 `tests/unit/ingestion/test_parser_docx.py`

Move tests related to:

* DOCX heading conversion
* DOCX table extraction
* DOCX content ordering
* Corrupt DOCX rejection
* Legacy `.doc` rejection
* DOCX-specific parsing behavior

Expected tests include behavior equivalent to:

```text
test_docx_headings_become_markdown_sections
test_docx_table_cells_are_extracted
test_docx_preserves_order_of_paragraphs_and_tables
test_corrupt_docx_is_rejected
test_legacy_doc_is_rejected
```

The `_docx_bytes` helper may remain local if it is used only by DOCX parser tests.

---

### 6.3 `tests/unit/ingestion/test_service.py`

Move tests related to:

* Idempotent ingestion
* Version replacement
* Chunk storage
* Enrichment invocation
* Document status transitions
* Section preservation after chunking

Expected tests include behavior equivalent to:

```text
test_reingesting_same_content_is_idempotent
test_new_content_replaces_active_document_version
test_ingestion_trace_includes_enrichment_when_enricher_exists
test_docx_sections_survive_chunking
```

Tracing-specific assertions should not remain here unless tracing is necessary to verify service behavior.

---

### 6.4 `tests/unit/ingestion/test_tracing.py`

Move tests related to:

* Ingestion span lifecycle
* Parse trace metadata
* Chunking trace metadata
* Metadata-only redaction
* Idempotent trace behavior
* Enrichment trace presence

Expected tests include behavior equivalent to:

```text
test_full_ingestion_trace_contains_lifecycle_data
test_idempotent_ingestion_trace_marks_skip_without_child_spans
test_metadata_only_ingestion_trace_redacts_parsed_and_chunk_text
test_ingestion_trace_includes_enrichment_when_enricher_exists
```

If one test overlaps service and tracing behavior, place it according to its main assertion.

---

### 6.5 `tests/component/api/test_app_wiring.py`

Move application wiring behavior such as:

```text
test_create_app_shares_tracer_between_ingestion_and_chat
```

This is a component test because it verifies dependency wiring across multiple internal services.

---

## 7. Required Split: `test_generation.py`

The existing `tests/test_generation.py` must be split by behavior.

### 7.1 `tests/unit/generation/test_citation_gate.py`

Move tests related to:

* Missing citations
* Invalid citations
* Citation index validation
* Citation mapping
* Citation-gated final answers

Expected tests include behavior equivalent to:

```text
test_generation_abstains_when_model_returns_no_valid_citation
test_generation_rejects_zero_citation_index
```

---

### 7.2 `tests/unit/generation/test_abstention.py`

Move tests where the primary concern is:

* Abstention behavior
* Empty or unsupported evidence
* Model output rejected due to grounding requirements
* Final answer fallback behavior

Do not duplicate citation-gate tests unless the behavior is genuinely distinct.

---

### 7.3 `tests/unit/generation/test_tracing.py`

Move tests related to:

* Generation trace metadata
* Retrieval trace metadata
* Privacy redaction
* Span update order
* Token and model metadata
* Prompt version recording

Expected tests include behavior equivalent to:

```text
test_trace_metadata_is_updated_before_span_closes
test_metadata_only_traces_redact_retrieval_text_and_final_answer
```

---

### 7.4 `tests/component/rag/test_retrieve_and_answer.py`

Move tests that validate the complete internal RAG component flow:

```text
Memory store
→ retrieval
→ ranked context
→ generation
→ citation mapping
→ final response
```

Expected tests include behavior equivalent to:

```text
test_traces_ranked_retrieval_hits_and_citation_gated_final_answer
```

The test may still use a fake provider. It is a component test because it connects retrieval, generation, schemas, tracing, and response construction.

---

## 8. Shared Test Support

Shared helpers must be stored under:

```text
tests/support/
```

Do not place test cases in this directory.

---

### 8.1 `tests/support/tracing.py`

Move reusable tracing test doubles here.

Required candidates:

```python
class RecordingObservation:
    ...

class RecordingTracer:
    ...
```

The implementation must:

* Record span names.
* Store initial metadata.
* Record update metadata.
* Detect updates after a span closes.
* Support trace-mode redaction through the real tracer when needed.
* Avoid application-specific assertions inside the helper.

Do not build a generic tracing framework.

---

### 8.2 `tests/support/providers.py`

Move reusable deterministic provider fakes here.

Candidate classes:

```text
CitedProvider
UncitedProvider
ZeroCitationProvider
AnswerProvider
FailingProvider
UnreachableProvider
```

Only move providers that are used by more than one test module.

A provider used in one file should remain local to that file.

Shared fake providers must:

* Never call an external API.
* Return deterministic structured results.
* Expose stable `name` and `model` values where required.
* Make intended behavior clear from the class name.

---

### 8.3 `tests/support/builders.py`

Add small domain-object builders only where object construction is duplicated.

Recommended initial builder:

```python
def make_chunk(
    *,
    chunk_id: str = "chunk-1",
    document_id: str = "doc-1",
    version: int = 1,
    text: str = "Policy content",
    content_hash: str = "hash",
    source_name: str = "policy.md",
    mime_type: str = "text/markdown",
    section: str | None = None,
    position: int = 0,
) -> Chunk:
    ...
```

Builder rules:

* Use explicit keyword arguments.
* Provide safe deterministic defaults.
* Return real domain models.
* Do not hide important test-specific values.
* Do not add builders that have only one caller.
* Do not create a universal factory abstraction.

---

## 9. Import Rules

Tests must import production modules through the existing `src` Python path configuration.

Example:

```python
from generation.service import ChatService
from retrieval.memory_store import MemoryChunkStore
```

Shared test support may be imported as:

```python
from tests.support.builders import make_chunk
from tests.support.providers import CitedProvider
from tests.support.tracing import RecordingTracer
```

If this import style requires `tests/__init__.py`, add only:

```text
tests/__init__.py
```

and, if necessary:

```text
tests/support/__init__.py
```

Do not add unnecessary `__init__.py` files throughout all test directories unless pytest or type checking requires them.

---

## 10. Pytest Configuration

Update `pyproject.toml` to include:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src", "."]
addopts = "-q"
markers = [
  "unit: isolated deterministic test",
  "component: multiple internal components with fake external dependencies",
  "integration: requires external infrastructure",
  "smoke: critical MVP workflow",
]
```

Preserve any other valid existing pytest configuration.

The root path `"."` may be added to `pythonpath` only if required for importing `tests.support`.

Alternative acceptable approach:

* Add `tests/__init__.py`.
* Preserve `pythonpath = ["src"]`.
* Verify that `tests.support` imports work.

Choose the simpler working option.

---

## 11. Marker Rules

### Unit tests

Markers are optional when folder location is sufficient.

Do not add `@pytest.mark.unit` to every test unless needed for selection.

### Component tests

Use either:

```python
pytestmark = pytest.mark.component
```

at module level, or explicit markers on individual tests.

### Integration tests

Every integration test module must contain:

```python
pytestmark = pytest.mark.integration
```

If environment-based skipping is required, combine it with the integration marker:

```python
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_QDRANT_INTEGRATION") != "1",
        reason="Set RUN_QDRANT_INTEGRATION=1 with Qdrant running",
    ),
]
```

### Smoke tests

Use `pytest.mark.smoke` only for a small number of critical MVP workflows.

Initial smoke candidates:

```text
Upload a document, then receive a cited answer
Application health endpoint succeeds
Qdrant document replacement preserves only the active version
```

Do not mark a large portion of the suite as smoke.

---

## 12. Naming Rules

Test filenames must describe the tested capability.

Good:

```text
test_citation_gate.py
test_parser_docx.py
test_document_replacement.py
test_provider_selection.py
```

Avoid vague names:

```text
test_utils.py
test_misc.py
test_more.py
test_all.py
test_new.py
```

Test functions must describe behavior.

Good:

```python
def test_generation_rejects_zero_citation_index():
    ...
```

Avoid:

```python
def test_generation_2():
    ...
```

Use this naming pattern:

```text
test_<subject>_<expected_behavior>
```

Optional condition:

```text
test_<subject>_<expected_behavior>_when_<condition>
```

---

## 13. Test Data Rules

Use:

* `tmp_path` for temporary files.
* In-memory stores for unit and component tests.
* Local deterministic byte strings for document content.
* Small inline test data for one-off cases.
* Builders for repeated domain objects.
* Local helper functions when used by only one module.

Do not:

* Write to real `data/uploads/`.
* Modify `data/registry.json`.
* Depend on test execution order.
* Share mutable global test state.
* Call paid external APIs.
* Use real credentials.
* Read the complete golden set in unrelated tests.
* add large binary fixtures without explicit justification.

---

## 14. Mocking Rules

Mock the system boundary, not internal implementation details.

Preferred:

```text
Mock Gemini SDK client
Mock HTTP call to Jina
Use fake generation provider
Use fake Qdrant client for unit tests
```

Avoid excessive mocking of:

```text
Private helper functions
Pure transformation functions
Domain schema validation
Internal methods that are part of the behavior being tested
```

A unit test may patch:

* External SDK calls
* Network clients
* Clock or sleep behavior
* Environment variables
* Filesystem paths
* External tracing client

A component test should use as many real internal components as practical.

---

## 15. External Service Policy

### Unit tests

Must not require:

```text
Gemini
OpenAI
OpenRouter
Jina
Langfuse
Qdrant
Internet access
```

### Component tests

Must not require external services.

### Integration tests

May require:

```text
Local Qdrant
```

### Live provider tests

Do not add live provider tests during this refactor.

If added later, they must use a separate explicit marker such as:

```text
live_provider
```

and must never run by default.

---

## 16. CI Requirements

Refactor the existing single CI test execution into two logical test jobs or steps.

### 16.1 Fast quality suite

Must run:

```bash
uv run ruff check .
uv run mypy
uv run pytest -m "not integration" --cov=src --cov-report=term-missing
```

This suite includes:

* Unit tests
* Component tests
* Smoke tests that do not require infrastructure

It must not require Qdrant.

---

### 16.2 Qdrant integration suite

Must start the Qdrant service and run:

```bash
uv run pytest tests/integration/qdrant -m integration
```

with:

```text
RUN_QDRANT_INTEGRATION=1
```

The integration job must clearly fail independently from the fast quality suite.

---

### 16.3 Docker checks

Preserve:

```bash
docker compose config --quiet
docker build --tag company-knowledge-rag:ci .
```

These checks may remain in the quality job or a separate build job.

---

## 17. `tests/README.md` Requirements

Create:

```text
tests/README.md
```

The document must be concise and act as the primary test-context entry point for humans and Coding Agents.

It must include the following sections.

### 17.1 Test categories

Explain:

```text
unit
component
integration
evaluation datasets
```

### 17.2 Source-to-test map

Include:

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
Qdrant behavior        → tests/integration/qdrant/**
Golden-set data        → evaluation/golden_set/**
```

### 17.3 Commands

Include:

```bash
# One file
uv run pytest tests/unit/generation/test_citation_gate.py -q

# One module
uv run pytest tests/unit/generation -q

# Component tests
uv run pytest tests/component -q

# Fast suite
uv run pytest -m "not integration" -q

# Qdrant integration
RUN_QDRANT_INTEGRATION=1 uv run pytest tests/integration/qdrant -q

# Full verification
uv run ruff check .
uv run mypy
uv run pytest -q
```

Add a Windows PowerShell equivalent for the environment variable:

```powershell
$env:RUN_QDRANT_INTEGRATION = "1"
uv run pytest tests/integration/qdrant -q
```

### 17.4 Adding a regression test

Document this workflow:

```text
1. Identify the affected production module.
2. Read the nearest existing tests.
3. Add the test to unit, component, or integration.
4. Reproduce the bug with a failing test.
5. Apply the smallest production fix.
6. Run the targeted test.
7. Run the affected module.
8. Run the fast suite.
9. Run integration tests only when the external boundary changed.
```

### 17.5 Test support

Explain:

```text
tests/support/builders.py
tests/support/providers.py
tests/support/tracing.py
```

### 17.6 Golden-set policy

State explicitly:

```text
Do not modify evaluation/golden_set/ unless the task explicitly concerns evaluation data.
```

---

## 18. Coding Agent Context Rules

Add or update root `AGENTS.md` with the following testing rules.

```text
## Testing Context Rules

1. Read tests/README.md before modifying tests.
2. Identify the affected source module before selecting test context.
3. Read the nearest existing tests before creating new tests.
4. Start with the smallest relevant test scope.
5. Classify new tests as unit, component, or integration.
6. Unit and component tests must not call live external services.
7. Real Qdrant may only be used under tests/integration/qdrant/.
8. Do not modify expected values only to make failing tests pass.
9. Do not modify golden-set data unless the task explicitly concerns evaluation.
10. Reuse tests/support only for stable repeated test concepts.
11. Do not create new generic test infrastructure without demonstrated duplication.
12. Report all commands executed.
13. Report tests that were not executed and explain why.
```

If `CLAUDE.md` or another agent-specific file exists, it should reference the canonical root `AGENTS.md` rather than duplicating all testing rules.

---

## 19. Coding Agent Test Selection Protocol

For every code change, the Coding Agent must follow this context sequence.

### Step 1: Read the task contract

Identify:

* Requested behavior
* Acceptance criteria
* Expected failure
* Allowed production scope
* Explicit non-goals

### Step 2: Map production scope to test scope

Examples:

```text
src/generation/service.py
→ tests/unit/generation/
→ tests/component/rag/ when retrieval-generation behavior changes
```

```text
src/providers/gemini.py
→ tests/unit/providers/test_gemini_embeddings.py
→ related key rotation tests when retry behavior changes
```

```text
src/retrieval/qdrant_store.py
→ tests/unit/retrieval/test_qdrant_store.py
→ tests/integration/qdrant/ when real Qdrant behavior changes
```

### Step 3: Read minimum necessary context

Read:

```text
Target production file
Direct interface or schema
Nearest relevant test file
Relevant test support helper
```

Do not load the entire test suite by default.

### Step 4: Run the smallest relevant test

Example:

```bash
uv run pytest tests/unit/generation/test_citation_gate.py -q
```

### Step 5: Expand context only after evidence

Expand to component or integration context only when:

* The behavior crosses module boundaries.
* The targeted test cannot reproduce the failure.
* The real infrastructure differs from the fake.
* A shared interface changed.

---

## 20. Refactor Safety Requirements

The refactor must preserve:

* Test assertions
* Test intent
* Existing production behavior
* Existing provider mocks
* Existing temporary path isolation
* Existing environment-based Qdrant skipping
* Existing cleanup of Qdrant collections
* Existing evaluation datasets
* Existing coverage collection
* Existing lint and type-check commands

The agent must not weaken tests by:

* Removing assertions
* Replacing exact assertions with `is not None`
* Adding unconditional retries
* Marking failing tests as skipped
* Adding broad exception handling
* Increasing timeouts without cause
* Deleting tests merely because they are difficult to migrate

---

## 21. Refactor Execution Order

Implement in this order.

### Phase 1: Create hierarchy

1. Create target folders.
2. Create `tests/support/`.
3. Add `tests/README.md`.
4. Update pytest markers.

### Phase 2: Move simple files

Move tests that do not require splitting:

* Settings
* Prompts
* Providers
* Retrieval
* Evaluation
* Observability
* API
* CLI
* Qdrant integration

Run:

```bash
uv run pytest -m "not integration" -q
```

### Phase 3: Extract shared support

1. Move repeated tracing doubles.
2. Move shared provider fakes.
3. Add builders only for repeated `Chunk` construction.
4. Update imports.

Run affected modules after each extraction.

### Phase 4: Split broad files

1. Split ingestion tests.
2. Split generation tests.
3. Move application wiring tests.
4. Move retrieve-and-answer component tests.

### Phase 5: Update CI

1. Separate fast and integration execution.
2. Preserve Qdrant service setup.
3. Preserve Docker checks.

### Phase 6: Final verification

Run:

```bash
uv run ruff check .
uv run mypy
uv run pytest -m "not integration" --cov=src --cov-report=term-missing
```

Then run with Qdrant:

```bash
RUN_QDRANT_INTEGRATION=1 uv run pytest tests/integration/qdrant -q
```

Finally:

```bash
uv run pytest -q
```

with the required integration environment enabled.

---

## 22. Acceptance Criteria

The task is complete only when all criteria are satisfied.

### Structure

* [ ] No ordinary test modules remain directly under `tests/`.
* [ ] Unit tests are under `tests/unit/`.
* [ ] Component tests are under `tests/component/`.
* [ ] Real Qdrant tests are under `tests/integration/qdrant/`.
* [ ] Shared helpers are under `tests/support/`.
* [ ] Golden-set data remains under `evaluation/golden_set/`.

### Classification

* [ ] Every test file has an obvious category from its path.
* [ ] Real external infrastructure tests use the `integration` marker.
* [ ] Unit and component tests do not call external services.
* [ ] API tests using `TestClient` are classified as component tests.

### Splitting

* [ ] `test_ingestion.py` no longer exists as one broad root file.
* [ ] PDF parser tests are separated.
* [ ] DOCX parser tests are separated.
* [ ] Ingestion service tests are separated.
* [ ] Ingestion tracing tests are separated.
* [ ] Application wiring tests are classified as component tests.
* [ ] `test_generation.py` no longer exists as one broad root file.
* [ ] Citation tests are separated.
* [ ] Abstention tests are separated.
* [ ] Generation tracing tests are separated.
* [ ] Retrieve-and-answer tests are classified as component tests.

### Shared support

* [ ] Repeated tracing doubles are centralized.
* [ ] Reusable provider fakes are centralized only when used by multiple files.
* [ ] Repeated `Chunk` setup is reduced through a small builder.
* [ ] No generic test utility framework is introduced.

### Tooling

* [ ] Pytest discovers all moved tests.
* [ ] Ruff passes.
* [ ] MyPy passes.
* [ ] Fast tests pass without Qdrant.
* [ ] Qdrant integration tests pass with Qdrant enabled.
* [ ] Coverage collection still works.
* [ ] Docker validation and image build still work.

### Documentation

* [ ] `tests/README.md` exists.
* [ ] Source-to-test mapping is documented.
* [ ] Test commands are documented.
* [ ] Golden-set modification policy is documented.
* [ ] Coding Agent test-context rules are documented in `AGENTS.md`.

---

## 23. Definition of Done Report

At completion, the Coding Agent must report:

```text
1. Files moved
2. Files split
3. Shared support created
4. Pytest configuration changes
5. CI changes
6. Commands executed
7. Test results
8. Coverage result
9. Tests not executed
10. Remaining risks or follow-up recommendations
```

The agent must explicitly state whether:

```text# Test Folder Hierarchy Specification

## 1. Purpose

Restructure the existing test suite so that:

* Test location clearly reflects the production module being tested.
* Coding Agents can find relevant tests without scanning the entire repository.
* Unit, component, and infrastructure integration tests are clearly separated.
* Shared test doubles and builders are reusable.
* Golden-set evaluation data remains separate from software tests.
* The structure remains lightweight enough for an MVP.

This task is a structural refactor. Existing application behavior and test expectations must not change unless a test is proven to be invalid.

---

## 2. Scope

### In scope

* Reorganize files under `tests/`.
* Split broad test modules where they cover multiple independent boundaries.
* Create shared test-support modules.
* Add test documentation.
* Update pytest configuration.
* Update CI commands and paths where necessary.
* Preserve all existing test coverage and behavior.

### Out of scope

* Rewriting production architecture.
* Changing application behavior.
* Editing golden-set samples.
* Changing evaluation scoring logic.
* Adding a large test framework.
* Adding test-impact analysis.
* Adding CI sharding.
* Adding live LLM tests.
* Changing provider retry policies.
* Increasing or decreasing coverage thresholds unless explicitly requested.

---

## 3. Target Folder Structure

The final hierarchy must be:

```text
tests/
├── unit/
│   ├── evaluation/
│   │   └── test_scoring.py
│   │
│   ├── generation/
│   │   ├── test_abstention.py
│   │   ├── test_citation_gate.py
│   │   └── test_tracing.py
│   │
│   ├── ingestion/
│   │   ├── test_parser_docx.py
│   │   ├── test_parser_pdf.py
│   │   ├── test_service.py
│   │   └── test_tracing.py
│   │
│   ├── observability/
│   │   └── test_tracing.py
│   │
│   ├── prompts/
│   │   ├── test_prompt.py
│   │   └── test_prompt_loader.py
│   │
│   ├── providers/
│   │   ├── test_gemini_embeddings.py
│   │   ├── test_generic_key_rotation.py
│   │   ├── test_jina.py
│   │   ├── test_jina_key_rotation.py
│   │   ├── test_key_rotation.py
│   │   ├── test_provider_selection.py
│   │   └── test_providers.py
│   │
│   ├── retrieval/
│   │   ├── test_hybrid.py
│   │   ├── test_qdrant_store.py
│   │   └── test_retrieval.py
│   │
│   ├── storage/
│   │   └── test_registry.py
│   │
│   └── test_settings.py
│
├── component/
│   ├── api/
│   │   ├── test_api.py
│   │   ├── test_app_wiring.py
│   │   └── test_cli.py
│   │
│   └── rag/
│       └── test_retrieve_and_answer.py
│
├── integration/
│   └── qdrant/
│       └── test_document_replacement.py
│
├── support/
│   ├── builders.py
│   ├── providers.py
│   └── tracing.py
│
└── README.md
```

Create `__init__.py` files only when required for import stability. Prefer normal pytest test discovery without turning every folder into an application package.

---

## 4. Test Category Definitions

### 4.1 Unit tests

Location:

```text
tests/unit/
```

A unit test must:

* Test one function, class, policy, parser, or isolated module behavior.
* Avoid real external infrastructure.
* Avoid live HTTP requests.
* Avoid live LLM, embedding, reranking, Langfuse, or Qdrant services.
* Use mocks, fakes, stubs, temporary files, or in-memory stores.
* Be deterministic.
* Run quickly.

Examples:

* Parser behavior
* Citation validation
* Abstention logic
* Key rotation logic
* Provider selection
* Retrieval fusion
* Evaluation score calculation
* Settings validation
* Qdrant adapter behavior using a fake client

A test using `QdrantChunkStore` is still a unit test when the Qdrant client is manually constructed, mocked, or replaced with a fake object.

---

### 4.2 Component tests

Location:

```text
tests/component/
```

A component test must:

* Connect multiple real internal modules.
* Keep external services fake or mocked.
* Validate an application-level boundary.
* Be deterministic.
* Not require Docker or external credentials.

Examples:

* FastAPI application creation
* Upload document, then query through the API
* Retrieval followed by grounded generation
* CLI invoking application services
* Dependency wiring between ingestion, chat, storage, and tracing

A component test may use:

* FastAPI `TestClient`
* `MemoryChunkStore`
* Temporary registry files
* Stub generation providers
* Recording tracers

---

### 4.3 Integration tests

Location:

```text
tests/integration/
```

An integration test must:

* Use real external infrastructure.
* Be explicitly marked with `pytest.mark.integration`.
* Be skipped unless its required environment is enabled.
* Clean up all created resources.
* Avoid live paid LLM or embedding APIs unless a future explicit test category is added.

Current integration scope:

```text
Real local Qdrant only
```

The current Qdrant integration test must continue requiring:

```text
RUN_QDRANT_INTEGRATION=1
```

Integration tests must create unique collection names and delete collections in a `finally` block.

---

### 4.4 Evaluation datasets

The following directory must remain outside `tests/`:

```text
evaluation/
├── GOLDEN_SET_SPEC.md
└── golden_set/
```

Golden-set JSON files are evaluation datasets, not pytest test fixtures.

Do not move them into:

```text
tests/fixtures/
tests/data/
tests/evaluation/
```

Software tests for the evaluation runner belong under:

```text
tests/unit/evaluation/
```

Dataset content remains under:

```text
evaluation/golden_set/
```

---

## 5. Existing File Migration Map

Apply the following moves.

```text
tests/test_settings.py
→ tests/unit/test_settings.py
```

```text
tests/test_prompt.py
→ tests/unit/prompts/test_prompt.py

tests/test_prompt_loader.py
→ tests/unit/prompts/test_prompt_loader.py
```

```text
tests/test_gemini_embeddings.py
→ tests/unit/providers/test_gemini_embeddings.py

tests/test_generic_key_rotation.py
→ tests/unit/providers/test_generic_key_rotation.py

tests/test_jina.py
→ tests/unit/providers/test_jina.py

tests/test_jina_key_rotation.py
→ tests/unit/providers/test_jina_key_rotation.py

tests/test_key_rotation.py
→ tests/unit/providers/test_key_rotation.py

tests/test_provider_selection.py
→ tests/unit/providers/test_provider_selection.py

tests/test_providers.py
→ tests/unit/providers/test_providers.py
```

```text
tests/test_hybrid.py
→ tests/unit/retrieval/test_hybrid.py

tests/test_qdrant_store.py
→ tests/unit/retrieval/test_qdrant_store.py

tests/test_retrieval.py
→ tests/unit/retrieval/test_retrieval.py
```

```text
tests/test_evaluation.py
→ tests/unit/evaluation/test_scoring.py
```

```text
tests/test_tracing.py
→ tests/unit/observability/test_tracing.py
```

```text
tests/test_api.py
→ tests/component/api/test_api.py

tests/test_cli.py
→ tests/component/api/test_cli.py
```

```text
tests/integration/test_qdrant_acl.py
→ tests/integration/qdrant/test_document_replacement.py
```

Any existing storage registry tests must be moved to:

```text
tests/unit/storage/test_registry.py
```

If no storage registry test currently exists, do not create empty placeholder tests.

---

## 6. Required Split: `test_ingestion.py`

The existing `tests/test_ingestion.py` contains several independent behaviors and must be split.

### 6.1 `tests/unit/ingestion/test_parser_pdf.py`

Move tests related to:

* Scanned PDF detection
* Corrupt PDF rejection
* PDF parsing behavior
* PDF-specific MIME or parsing rules

Expected tests include behavior equivalent to:

```text
test_scanned_pdf_is_marked_needs_ocr
test_corrupt_pdf_is_rejected
```

Do not move service-level ingestion behavior into this file.

---

### 6.2 `tests/unit/ingestion/test_parser_docx.py`

Move tests related to:

* DOCX heading conversion
* DOCX table extraction
* DOCX content ordering
* Corrupt DOCX rejection
* Legacy `.doc` rejection
* DOCX-specific parsing behavior

Expected tests include behavior equivalent to:

```text
test_docx_headings_become_markdown_sections
test_docx_table_cells_are_extracted
test_docx_preserves_order_of_paragraphs_and_tables
test_corrupt_docx_is_rejected
test_legacy_doc_is_rejected
```

The `_docx_bytes` helper may remain local if it is used only by DOCX parser tests.

---

### 6.3 `tests/unit/ingestion/test_service.py`

Move tests related to:

* Idempotent ingestion
* Version replacement
* Chunk storage
* Enrichment invocation
* Document status transitions
* Section preservation after chunking

Expected tests include behavior equivalent to:

```text
test_reingesting_same_content_is_idempotent
test_new_content_replaces_active_document_version
test_ingestion_trace_includes_enrichment_when_enricher_exists
test_docx_sections_survive_chunking
```

Tracing-specific assertions should not remain here unless tracing is necessary to verify service behavior.

---

### 6.4 `tests/unit/ingestion/test_tracing.py`

Move tests related to:

* Ingestion span lifecycle
* Parse trace metadata
* Chunking trace metadata
* Metadata-only redaction
* Idempotent trace behavior
* Enrichment trace presence

Expected tests include behavior equivalent to:

```text
test_full_ingestion_trace_contains_lifecycle_data
test_idempotent_ingestion_trace_marks_skip_without_child_spans
test_metadata_only_ingestion_trace_redacts_parsed_and_chunk_text
test_ingestion_trace_includes_enrichment_when_enricher_exists
```

If one test overlaps service and tracing behavior, place it according to its main assertion.

---

### 6.5 `tests/component/api/test_app_wiring.py`

Move application wiring behavior such as:

```text
test_create_app_shares_tracer_between_ingestion_and_chat
```

This is a component test because it verifies dependency wiring across multiple internal services.

---

## 7. Required Split: `test_generation.py`

The existing `tests/test_generation.py` must be split by behavior.

### 7.1 `tests/unit/generation/test_citation_gate.py`

Move tests related to:

* Missing citations
* Invalid citations
* Citation index validation
* Citation mapping
* Citation-gated final answers

Expected tests include behavior equivalent to:

```text
test_generation_abstains_when_model_returns_no_valid_citation
test_generation_rejects_zero_citation_index
```

---

### 7.2 `tests/unit/generation/test_abstention.py`

Move tests where the primary concern is:

* Abstention behavior
* Empty or unsupported evidence
* Model output rejected due to grounding requirements
* Final answer fallback behavior

Do not duplicate citation-gate tests unless the behavior is genuinely distinct.

---

### 7.3 `tests/unit/generation/test_tracing.py`

Move tests related to:

* Generation trace metadata
* Retrieval trace metadata
* Privacy redaction
* Span update order
* Token and model metadata
* Prompt version recording

Expected tests include behavior equivalent to:

```text
test_trace_metadata_is_updated_before_span_closes
test_metadata_only_traces_redact_retrieval_text_and_final_answer
```

---

### 7.4 `tests/component/rag/test_retrieve_and_answer.py`

Move tests that validate the complete internal RAG component flow:

```text
Memory store
→ retrieval
→ ranked context
→ generation
→ citation mapping
→ final response
```

Expected tests include behavior equivalent to:

```text
test_traces_ranked_retrieval_hits_and_citation_gated_final_answer
```

The test may still use a fake provider. It is a component test because it connects retrieval, generation, schemas, tracing, and response construction.

---

## 8. Shared Test Support

Shared helpers must be stored under:

```text
tests/support/
```

Do not place test cases in this directory.

---

### 8.1 `tests/support/tracing.py`

Move reusable tracing test doubles here.

Required candidates:

```python
class RecordingObservation:
    ...

class RecordingTracer:
    ...
```

The implementation must:

* Record span names.
* Store initial metadata.
* Record update metadata.
* Detect updates after a span closes.
* Support trace-mode redaction through the real tracer when needed.
* Avoid application-specific assertions inside the helper.

Do not build a generic tracing framework.

---

### 8.2 `tests/support/providers.py`

Move reusable deterministic provider fakes here.

Candidate classes:

```text
CitedProvider
UncitedProvider
ZeroCitationProvider
AnswerProvider
FailingProvider
UnreachableProvider
```

Only move providers that are used by more than one test module.

A provider used in one file should remain local to that file.

Shared fake providers must:

* Never call an external API.
* Return deterministic structured results.
* Expose stable `name` and `model` values where required.
* Make intended behavior clear from the class name.

---

### 8.3 `tests/support/builders.py`

Add small domain-object builders only where object construction is duplicated.

Recommended initial builder:

```python
def make_chunk(
    *,
    chunk_id: str = "chunk-1",
    document_id: str = "doc-1",
    version: int = 1,
    text: str = "Policy content",
    content_hash: str = "hash",
    source_name: str = "policy.md",
    mime_type: str = "text/markdown",
    section: str | None = None,
    position: int = 0,
) -> Chunk:
    ...
```

Builder rules:

* Use explicit keyword arguments.
* Provide safe deterministic defaults.
* Return real domain models.
* Do not hide important test-specific values.
* Do not add builders that have only one caller.
* Do not create a universal factory abstraction.

---

## 9. Import Rules

Tests must import production modules through the existing `src` Python path configuration.

Example:

```python
from generation.service import ChatService
from retrieval.memory_store import MemoryChunkStore
```

Shared test support may be imported as:

```python
from tests.support.builders import make_chunk
from tests.support.providers import CitedProvider
from tests.support.tracing import RecordingTracer
```

If this import style requires `tests/__init__.py`, add only:

```text
tests/__init__.py
```

and, if necessary:

```text
tests/support/__init__.py
```

Do not add unnecessary `__init__.py` files throughout all test directories unless pytest or type checking requires them.

---

## 10. Pytest Configuration

Update `pyproject.toml` to include:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src", "."]
addopts = "-q"
markers = [
  "unit: isolated deterministic test",
  "component: multiple internal components with fake external dependencies",
  "integration: requires external infrastructure",
  "smoke: critical MVP workflow",
]
```

Preserve any other valid existing pytest configuration.

The root path `"."` may be added to `pythonpath` only if required for importing `tests.support`.

Alternative acceptable approach:

* Add `tests/__init__.py`.
* Preserve `pythonpath = ["src"]`.
* Verify that `tests.support` imports work.

Choose the simpler working option.

---

## 11. Marker Rules

### Unit tests

Markers are optional when folder location is sufficient.

Do not add `@pytest.mark.unit` to every test unless needed for selection.

### Component tests

Use either:

```python
pytestmark = pytest.mark.component
```

at module level, or explicit markers on individual tests.

### Integration tests

Every integration test module must contain:

```python
pytestmark = pytest.mark.integration
```

If environment-based skipping is required, combine it with the integration marker:

```python
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_QDRANT_INTEGRATION") != "1",
        reason="Set RUN_QDRANT_INTEGRATION=1 with Qdrant running",
    ),
]
```

### Smoke tests

Use `pytest.mark.smoke` only for a small number of critical MVP workflows.

Initial smoke candidates:

```text
Upload a document, then receive a cited answer
Application health endpoint succeeds
Qdrant document replacement preserves only the active version
```

Do not mark a large portion of the suite as smoke.

---

## 12. Naming Rules

Test filenames must describe the tested capability.

Good:

```text
test_citation_gate.py
test_parser_docx.py
test_document_replacement.py
test_provider_selection.py
```

Avoid vague names:

```text
test_utils.py
test_misc.py
test_more.py
test_all.py
test_new.py
```

Test functions must describe behavior.

Good:

```python
def test_generation_rejects_zero_citation_index():
    ...
```

Avoid:

```python
def test_generation_2():
    ...
```

Use this naming pattern:

```text
test_<subject>_<expected_behavior>
```

Optional condition:

```text
test_<subject>_<expected_behavior>_when_<condition>
```

---

## 13. Test Data Rules

Use:

* `tmp_path` for temporary files.
* In-memory stores for unit and component tests.
* Local deterministic byte strings for document content.
* Small inline test data for one-off cases.
* Builders for repeated domain objects.
* Local helper functions when used by only one module.

Do not:

* Write to real `data/uploads/`.
* Modify `data/registry.json`.
* Depend on test execution order.
* Share mutable global test state.
* Call paid external APIs.
* Use real credentials.
* Read the complete golden set in unrelated tests.
* add large binary fixtures without explicit justification.

---

## 14. Mocking Rules

Mock the system boundary, not internal implementation details.

Preferred:

```text
Mock Gemini SDK client
Mock HTTP call to Jina
Use fake generation provider
Use fake Qdrant client for unit tests
```

Avoid excessive mocking of:

```text
Private helper functions
Pure transformation functions
Domain schema validation
Internal methods that are part of the behavior being tested
```

A unit test may patch:

* External SDK calls
* Network clients
* Clock or sleep behavior
* Environment variables
* Filesystem paths
* External tracing client

A component test should use as many real internal components as practical.

---

## 15. External Service Policy

### Unit tests

Must not require:

```text
Gemini
OpenAI
OpenRouter
Jina
Langfuse
Qdrant
Internet access
```

### Component tests

Must not require external services.

### Integration tests

May require:

```text
Local Qdrant
```

### Live provider tests

Do not add live provider tests during this refactor.

If added later, they must use a separate explicit marker such as:

```text
live_provider
```

and must never run by default.

---

## 16. CI Requirements

Refactor the existing single CI test execution into two logical test jobs or steps.

### 16.1 Fast quality suite

Must run:

```bash
uv run ruff check .
uv run mypy
uv run pytest -m "not integration" --cov=src --cov-report=term-missing
```

This suite includes:

* Unit tests
* Component tests
* Smoke tests that do not require infrastructure

It must not require Qdrant.

---

### 16.2 Qdrant integration suite

Must start the Qdrant service and run:

```bash
uv run pytest tests/integration/qdrant -m integration
```

with:

```text
RUN_QDRANT_INTEGRATION=1
```

The integration job must clearly fail independently from the fast quality suite.

---

### 16.3 Docker checks

Preserve:

```bash
docker compose config --quiet
docker build --tag company-knowledge-rag:ci .
```

These checks may remain in the quality job or a separate build job.

---

## 17. `tests/README.md` Requirements

Create:

```text
tests/README.md
```

The document must be concise and act as the primary test-context entry point for humans and Coding Agents.

It must include the following sections.

### 17.1 Test categories

Explain:

```text
unit
component
integration
evaluation datasets
```

### 17.2 Source-to-test map

Include:

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
Qdrant behavior        → tests/integration/qdrant/**
Golden-set data        → evaluation/golden_set/**
```

### 17.3 Commands

Include:

```bash
# One file
uv run pytest tests/unit/generation/test_citation_gate.py -q

# One module
uv run pytest tests/unit/generation -q

# Component tests
uv run pytest tests/component -q

# Fast suite
uv run pytest -m "not integration" -q

# Qdrant integration
RUN_QDRANT_INTEGRATION=1 uv run pytest tests/integration/qdrant -q

# Full verification
uv run ruff check .
uv run mypy
uv run pytest -q
```

Add a Windows PowerShell equivalent for the environment variable:

```powershell
$env:RUN_QDRANT_INTEGRATION = "1"
uv run pytest tests/integration/qdrant -q
```

### 17.4 Adding a regression test

Document this workflow:

```text
1. Identify the affected production module.
2. Read the nearest existing tests.
3. Add the test to unit, component, or integration.
4. Reproduce the bug with a failing test.
5. Apply the smallest production fix.
6. Run the targeted test.
7. Run the affected module.
8. Run the fast suite.
9. Run integration tests only when the external boundary changed.
```

### 17.5 Test support

Explain:

```text
tests/support/builders.py
tests/support/providers.py
tests/support/tracing.py
```

### 17.6 Golden-set policy

State explicitly:

```text
Do not modify evaluation/golden_set/ unless the task explicitly concerns evaluation data.
```

---

## 18. Coding Agent Context Rules

Add or update root `AGENTS.md` with the following testing rules.

```text
## Testing Context Rules

1. Read tests/README.md before modifying tests.
2. Identify the affected source module before selecting test context.
3. Read the nearest existing tests before creating new tests.
4. Start with the smallest relevant test scope.
5. Classify new tests as unit, component, or integration.
6. Unit and component tests must not call live external services.
7. Real Qdrant may only be used under tests/integration/qdrant/.
8. Do not modify expected values only to make failing tests pass.
9. Do not modify golden-set data unless the task explicitly concerns evaluation.
10. Reuse tests/support only for stable repeated test concepts.
11. Do not create new generic test infrastructure without demonstrated duplication.
12. Report all commands executed.
13. Report tests that were not executed and explain why.
```

If `CLAUDE.md` or another agent-specific file exists, it should reference the canonical root `AGENTS.md` rather than duplicating all testing rules.

---

## 19. Coding Agent Test Selection Protocol

For every code change, the Coding Agent must follow this context sequence.

### Step 1: Read the task contract

Identify:

* Requested behavior
* Acceptance criteria
* Expected failure
* Allowed production scope
* Explicit non-goals

### Step 2: Map production scope to test scope

Examples:

```text
src/generation/service.py
→ tests/unit/generation/
→ tests/component/rag/ when retrieval-generation behavior changes
```

```text
src/providers/gemini.py
→ tests/unit/providers/test_gemini_embeddings.py
→ related key rotation tests when retry behavior changes
```

```text
src/retrieval/qdrant_store.py
→ tests/unit/retrieval/test_qdrant_store.py
→ tests/integration/qdrant/ when real Qdrant behavior changes
```

### Step 3: Read minimum necessary context

Read:

```text
Target production file
Direct interface or schema
Nearest relevant test file
Relevant test support helper
```

Do not load the entire test suite by default.

### Step 4: Run the smallest relevant test

Example:

```bash
uv run pytest tests/unit/generation/test_citation_gate.py -q
```

### Step 5: Expand context only after evidence

Expand to component or integration context only when:

* The behavior crosses module boundaries.
* The targeted test cannot reproduce the failure.
* The real infrastructure differs from the fake.
* A shared interface changed.

---

## 20. Refactor Safety Requirements

The refactor must preserve:

* Test assertions
* Test intent
* Existing production behavior
* Existing provider mocks
* Existing temporary path isolation
* Existing environment-based Qdrant skipping
* Existing cleanup of Qdrant collections
* Existing evaluation datasets
* Existing coverage collection
* Existing lint and type-check commands

The agent must not weaken tests by:

* Removing assertions
* Replacing exact assertions with `is not None`
* Adding unconditional retries
* Marking failing tests as skipped
* Adding broad exception handling
* Increasing timeouts without cause
* Deleting tests merely because they are difficult to migrate

---

## 21. Refactor Execution Order

Implement in this order.

### Phase 1: Create hierarchy

1. Create target folders.
2. Create `tests/support/`.
3. Add `tests/README.md`.
4. Update pytest markers.

### Phase 2: Move simple files

Move tests that do not require splitting:

* Settings
* Prompts
* Providers
* Retrieval
* Evaluation
* Observability
* API
* CLI
* Qdrant integration

Run:

```bash
uv run pytest -m "not integration" -q
```

### Phase 3: Extract shared support

1. Move repeated tracing doubles.
2. Move shared provider fakes.
3. Add builders only for repeated `Chunk` construction.
4. Update imports.

Run affected modules after each extraction.

### Phase 4: Split broad files

1. Split ingestion tests.
2. Split generation tests.
3. Move application wiring tests.
4. Move retrieve-and-answer component tests.

### Phase 5: Update CI

1. Separate fast and integration execution.
2. Preserve Qdrant service setup.
3. Preserve Docker checks.

### Phase 6: Final verification

Run:

```bash
uv run ruff check .
uv run mypy
uv run pytest -m "not integration" --cov=src --cov-report=term-missing
```

Then run with Qdrant:

```bash
RUN_QDRANT_INTEGRATION=1 uv run pytest tests/integration/qdrant -q
```

Finally:

```bash
uv run pytest -q
```

with the required integration environment enabled.

---

## 22. Acceptance Criteria

The task is complete only when all criteria are satisfied.

### Structure

* [ ] No ordinary test modules remain directly under `tests/`.
* [ ] Unit tests are under `tests/unit/`.
* [ ] Component tests are under `tests/component/`.
* [ ] Real Qdrant tests are under `tests/integration/qdrant/`.
* [ ] Shared helpers are under `tests/support/`.
* [ ] Golden-set data remains under `evaluation/golden_set/`.

### Classification

* [ ] Every test file has an obvious category from its path.
* [ ] Real external infrastructure tests use the `integration` marker.
* [ ] Unit and component tests do not call external services.
* [ ] API tests using `TestClient` are classified as component tests.

### Splitting

* [ ] `test_ingestion.py` no longer exists as one broad root file.
* [ ] PDF parser tests are separated.
* [ ] DOCX parser tests are separated.
* [ ] Ingestion service tests are separated.
* [ ] Ingestion tracing tests are separated.
* [ ] Application wiring tests are classified as component tests.
* [ ] `test_generation.py` no longer exists as one broad root file.
* [ ] Citation tests are separated.
* [ ] Abstention tests are separated.
* [ ] Generation tracing tests are separated.
* [ ] Retrieve-and-answer tests are classified as component tests.

### Shared support

* [ ] Repeated tracing doubles are centralized.
* [ ] Reusable provider fakes are centralized only when used by multiple files.
* [ ] Repeated `Chunk` setup is reduced through a small builder.
* [ ] No generic test utility framework is introduced.

### Tooling

* [ ] Pytest discovers all moved tests.
* [ ] Ruff passes.
* [ ] MyPy passes.
* [ ] Fast tests pass without Qdrant.
* [ ] Qdrant integration tests pass with Qdrant enabled.
* [ ] Coverage collection still works.
* [ ] Docker validation and image build still work.

### Documentation

* [ ] `tests/README.md` exists.
* [ ] Source-to-test mapping is documented.
* [ ] Test commands are documented.
* [ ] Golden-set modification policy is documented.
* [ ] Coding Agent test-context rules are documented in `AGENTS.md`.

---

## 23. Definition of Done Report

At completion, the Coding Agent must report:

```text
1. Files moved
2. Files split
3. Shared support created
4. Pytest configuration changes
5. CI changes
6. Commands executed
7. Test results
8. Coverage result  
9. Tests not executed
10. Remaining risks or follow-up recommendations
```

The agent must explicitly state whether:

```text
All non-integration tests passed
Qdrant integration tests passed
Ruff passed
MyPy passed
Docker checks passed
```

---

## 24. Guiding Principle

Use the smallest structure that makes test ownership, execution cost, and relevant context obvious.

The hierarchy should optimize for:

```text
Production change
→ obvious test location
→ small context package
→ targeted execution
→ reliable verification
```

Do not optimize for hypothetical enterprise scale during this MVP refactor.

All non-integration tests passed
Qdrant integration tests passed
Ruff passed
MyPy passed
Docker checks passed
```

---

## 24. Guiding Principle

Use the smallest structure that makes test ownership, execution cost, and relevant context obvious.

The hierarchy should optimize for:

```text
Production change
→ obvious test location
→ small context package
→ targeted execution
→ reliable verification
```

Do not optimize for hypothetical enterprise scale during this MVP refactor.
