# Staged Offline RAG Evaluation — Code Simplifier Review Handoff

## Checkpoint

- Worktree: `E:\VIN-INTERNSHIP\Cowork-RAG\.worktree\staged-offline-rag-eval`
- Branch: `codex/staged-offline-rag-eval`
- Simplification base: `db5bc0c` (`fix: complete staged evaluation verification`)
- Merge base: `6d7732c` (`main` at implementation start)
- Review scope: Tasks 0–11, limited to code changed by the staged offline evaluation implementation.
- Review result: no safe feature or module deletion. Six bounded refactors have worthwhile clarity/duplication payoff.
- Current reusable evidence at `db5bc0c`: 187 tests passed; Ruff clean; mypy clean for 49 source files; `rag-eval validate` passed 100 cases/130 contexts with `full_conformance=true` and `baseline_eligible=false`.

This handoff applies the `code-simplifier` skill as a Python review rubric. Its JavaScript/React-specific rules do not apply. Preserve behavior, prefer explicit Python, and follow `AGENTS.md`, the implementation plan, Ruff, mypy, and repository tests.

## Non-Negotiable Boundaries

- Refactor only. Do not change outputs, error strings, selection precedence, status semantics, artifact bytes, fingerprints, trace privacy, concurrency, or baseline eligibility.
- Never edit `evaluation/golden_set/**`, `evaluation/id_migration_map.json`, `evaluation/golden_set_grounding_review.json`, or `evaluation/GOLDEN_SET_SPEC.md`.
- Never replace the explicit retrieval trace allowlist with `Chunk.model_dump()`. Enrichment fields must remain absent in every trace mode; raw `text` remains FULL-only.
- Preserve write-once artifact behavior and one final manifest/report write.
- Preserve Ragas as report-only and evidence-only. It must not rerun retrieval/generation.
- Preserve general-purpose ingestion as minimal: legal headings authoritative; generic Markdown headings only when no legal structure exists.
- Work one simplifier task at a time. Commit explicit paths only. Do not combine cleanup with new behavior.
- Reuse passing evidence while its covered surface is unchanged. Each agent runs its focused scope; the last agent runs full verification.

## Ranked Simplifier Tasks

### S1 — Task 7 metrics clarity (start here)

**Value/risk:** high clarity payoff, low behavior risk.

**Files:**

- `src/evaluation/metrics.py`
- `tests/unit/evaluation/test_metrics.py`

**Why:** `aggregate_scores()` and `_aggregate_segment()` duplicate dense non-null value extraction with assignment expressions. Retrieval scoring repeats long coordinate tuples and several long comprehensions. Current code is correct but harder to scan than necessary.

**Refine:** introduce one small typed helper for non-null metric values; name repeated coordinate concepts only where it reduces repetition; reformat long comprehensions. Prefer explicit loops over clever compression.

**Do not change:** unique-coordinate denominator, null exclusion, nearest-rank p95, segmentation order, rate-metric target comparison, or returned keys.

**Verify:** `tests/unit/evaluation/test_metrics.py`, scoped Ruff, mypy.

**Suggested agent:** `gpt-5.6-terra`, high effort.

### S2 — Task 5 retrieval trace allowlist extraction

**Value/risk:** high privacy/readability payoff, medium contract risk.

**Files:**

- `src/generation/service.py`
- `tests/unit/generation/test_execution.py`
- `tests/unit/generation/test_tracing.py`
- `tests/component/rag/test_retrieve_and_answer.py`

**Why:** `ChatService.retrieve()` embeds a large explicit trace dictionary inside a list comprehension. The allowlist is security-relevant and should have a named boundary.

**Refine:** extract a small private helper that builds one ranked-hit trace record from explicit fields. Keep the allowlist visible and explicit. Consider citation-index construction only if extraction clearly reduces nesting without hiding the citation gate.

**Do not change:** trace keys, coordinate fields, scores/ranks, FULL raw text, METADATA_ONLY redaction, enrichment exclusion, retrieval execution evidence, `ChatResponse`, or citation gating.

**Verify:** listed files plus `tests/unit/generation/test_citation_gate.py`; scoped Ruff, mypy.

**Suggested agent:** `gpt-5.6-terra`, high effort.

### S3 — Task 4 golden validation decomposition

**Value/risk:** highest single-function clarity payoff, high authority risk.

**Files:**

- `src/evaluation/golden.py`
- `tests/unit/evaluation/test_validation.py`
- `tests/component/evaluation/test_validation.py`
- `tests/unit/evaluation/test_golden.py`

**Why:** `validate_golden_dataset()` is about 192 lines and owns five distinct operations: canonical article indexing, exact-source checks, coordinate checks, chunk recoverability, and two audit-artifact validations. Nested expected-review construction obscures authority rules.

**Refine:** extract private pure helpers for canonical article mapping, context validation, ordered chunk recovery, migration-map validation, and grounding-review construction/comparison. Move the fixed expected migration structure to a clearly named module constant if byte/value equality remains exact. Keep one public orchestration function.

**Do not change:** error-before-warning semantics, error/warning codes and messages, exact substring checks, markup normalization, ordered chunk concatenation, expected migration content, SHA-256 serialization, 100/130 counts, or `full_conformance` logic.

**Verify:** listed tests, `rag-eval validate`, scoped Ruff, mypy. Confirm 100 cases/130 contexts and zero warnings/errors.

**Suggested agent:** `gpt-5.6-sol`, high effort.

### S4 — Task 9 Ragas scoring duplication

**Value/risk:** medium clarity payoff, high third-party/concurrency risk.

**Files:**

- `src/evaluation/ragas_adapter.py`
- `tests/unit/evaluation/test_ragas.py`

**Why:** retrieval and generation paths duplicate metric result/error collection, semaphore handling, and `SemanticScoreBatch` assembly. Both nested `score_case()` functions use broad `Any` despite concrete artifact models.

**Refine:** add small typed metric-call/result helpers and share batch assembly. Improve case parameter types where current artifact models permit. Keep retrieval/generation evidence preparation separate when their inputs differ.

**Do not change:** metric names, Ragas v0.4 kwargs, per-metric exception isolation, exception redaction to type name, max concurrency, current semaphore scope, case order, null scores, or no-network unit-test behavior.

**Verify:** `tests/unit/evaluation/test_ragas.py`, exact installed Ragas import/version probe, scoped Ruff, mypy. No live judge call.

**Suggested agent:** `gpt-5.6-sol`, high effort.

### S5 — Task 6 JSONL repository duplication

**Value/risk:** medium duplication payoff, medium immutable-artifact risk.

**Files:**

- `src/evaluation/repository.py`
- `tests/unit/evaluation/test_artifacts.py`
- `tests/unit/evaluation/test_runner.py`

**Why:** `save_retrieval()` and `save_generation()` duplicate header/case JSONL assembly. This is a narrow shared serialization shape.

**Refine:** extract one private JSONL-body helper that accepts an already-dumped header and ordered case models/records. Keep Local and InMemory repositories explicit; do not build a generic save framework around their dictionaries/counters.

**Do not change:** record order, `record_type`, JSON field values, UTF-8 behavior, final newline, file names, atomic write checks, duplicate-save exceptions, or original bytes after failure.

**Verify:** listed tests; add/retain byte-equality assertions if needed; scoped Ruff, mypy.

**Suggested agent:** `gpt-5.6-terra`, high effort.

### S6 — Task 8 runner orchestration decomposition (last)

**Value/risk:** highest overall payoff, highest lifecycle risk. Run after S1–S5 so dependencies are stable.

**Files:**

- `src/evaluation/runner.py`
- `tests/unit/evaluation/test_runner.py`
- `tests/component/api/test_evaluation_cli.py`

**Why:** `run()` is about 127 lines; retrieval and generation phase methods are about 122 and 137 lines. Failure-report construction, replay dataset resolution, semantic-score merging, and per-mode dispatch repeat or nest multiple responsibilities.

**Refine:** extract narrowly named helpers for replay-aware dataset resolution, failed-report construction, case-score merging, and mode dispatch. Reduce nesting while keeping explicit `if/elif` flow where it is clearer than a dispatch registry. Split phase methods only at stable artifact boundaries.

**Do not change:** validate-before-runtime ordering, replay without search, selection inheritance, per-case continuation, incompatible fingerprint rejection, immutable write counts/order, artifact lineage, correctness blocking, report-only targets, Ragas opt-in behavior, E2E status, or strict 100-case baseline gate.

**Verify:** listed tests, then full `tests` suite, Ruff, mypy, `git diff --check`, and `rag-eval validate`.

**Suggested agent:** `gpt-5.6-sol`, high effort.

## Reviewed, Leave As-Is

- **Task 0:** golden data and audit evidence are authority artifacts, not simplifier scope.
- **Task 1:** schema models, type contract, loader, and selection are compact and explicit. Keep `evaluation.__init__` re-exports; the plan requires that public surface even though internal code imports submodules directly.
- **Tasks 2–3:** legal/generic heading precedence, coordinate persistence, Qdrant legacy rejection, and pagination are sensitive and already reasonably direct. Do not generalize filters or payload conversion. `extract_legal_sections()` may be reformatted locally, but it does not justify a separate agent task.
- **Task 6 artifacts:** keep `VOLATILE_ARTIFACT_FIELDS`, frozen models, and explicit mode validator. These are contract declarations, not accidental complexity.
- **Task 10:** CLI parser duplication is small and explicit; consolidating mode-specific arguments risks hiding approved option boundaries.
- **Task 11:** documentation and targeted typing fixes need no simplification.
- **Test builders:** `coordinates or SourceCoordinates(...)` can become an explicit `is not None` expression when a nearby task already touches those helpers, but it is not worth a standalone agent.

## Removal Decision

No production feature, class, module, CLI mode, public export, artifact field, or regression test should be removed. Ruff reports no unused imports, and the only apparently unused package-level re-exports are plan-mandated public API. Safe removal means removing duplicated local assembly during S1–S6, not deleting behavior.

Already completed removals must stay removed:

- legacy `company-rag-evaluate` CLI path from `src/cli.py`;
- obsolete `tests/unit/evaluation/test_scoring.py` after replacement coverage landed.

## Agent Workflow

1. Start from `db5bc0c`; verify clean worktree and current branch.
2. Execute S1 → S6 sequentially. One fresh coding agent per task; never parallelize shared-file edits.
3. Each agent reads only this handoff, its named source/tests, `AGENTS.md`, and relevant plan task.
4. Each agent uses `code-simplifier`, preserves behavior, runs focused verification, self-reviews, and commits explicit paths.
5. Controller reviews each commit diff before next task. No independent reviewer needed for mechanical S1/S2/S5; use stronger controller scrutiny for S3/S4/S6 authority/lifecycle boundaries.
6. Last agent runs full verification. Do not push, merge, or create a PR without new user instruction.
