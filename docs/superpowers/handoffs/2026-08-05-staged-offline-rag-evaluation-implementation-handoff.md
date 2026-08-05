# Staged Offline RAG Evaluation Implementation Handoff

## Resume here

Implement the revised staged offline RAG evaluation plan task by task. Planning and review correction are complete; product implementation has not started.

- Repository: `E:\VIN-INTERNSHIP\Cowork-RAG`
- Worktree: `E:\VIN-INTERNSHIP\Cowork-RAG\.worktree\staged-offline-rag-eval`
- Branch: `codex/staged-offline-rag-eval`
- Handoff HEAD before this file's commit: `e691b0e`
- Base: `6d7732c` (`main`)
- Revised plan: `docs/superpowers/plans/2026-08-05-staged-offline-rag-evaluation.md`
- Original review evidence: `docs/superpowers/handoffs/2026-08-05-staged-offline-rag-evaluation-plan-review-report.md`
- Durable local SDD ledger: `.superpowers/sdd/progress.md` (ignored scratch file)

The worktree was deliberately placed under the project-local `.worktree/` directory so other coding agents can access it. Do not create a replacement under `.codex` or outside the repository.

## Authority order

1. `docs/superpowers/specs/2026-08-05-staged-offline-rag-evaluation-design.md`
2. `evaluation/GOLDEN_SET_SPEC.md`
3. Repository code, `AGENTS.md`, and `tests/README.md`
4. `docs/superpowers/plans/2026-08-05-staged-offline-rag-evaluation.md`

The user explicitly approved P0-3 option (a): trim AMB-014 context index 1 before `# Chương IX` and AMB-019 context index 1 before `# Chương IV`, then reissue the ambiguous dataset and regenerate/reconcile the required migration and grounding-review evidence. This is authorization for the plan's Task 0 data changes only; preserve all other finalized golden content.

## Plan status

The plan now contains 12 implementation tasks, numbered Task 0 through Task 11. Start with the first incomplete task:

> **Task 0: Approved Golden-Data Reissue and Audit Evidence**

Do not repeat the plan-revision work. The following documentation commits are already complete:

- `7ea33d0` — revise the plan for all original P0/P1/P2 findings and track the review evidence.
- `405fe04` — fix the first cross-task review findings.
- `606cd2e` — fix generation replay, retained preflight reports, audit parameterization, and related gates.
- `e992f45` — add authoritative baseline, protocol typing, pytest import, and initial write-once safeguards.
- `e691b0e` — finalize single-write report/manifest orchestration and in-memory duplicate-save guards.

The tracked original review report remained byte-identical during revision. Both the preserved source and committed blob hash are `b5c55de2f8d914547a7829380b3d93aa271f0c0b`.

## Required execution workflow

Use `superpowers:subagent-driven-development` from this same supervision session:

1. Check `.superpowers/sdd/progress.md`; never redispatch a completed task.
2. Extract only the next task with the skill's `scripts/task-brief` helper.
3. Dispatch one fresh implementer using `gpt-5.6-terra` with `high` reasoning.
4. Require TDD, focused tests first, a full relevant gate before commit, self-review, an explicit-path commit, and a report file.
5. Generate a review package from the recorded task base to task head.
6. Choose the cheapest adequate review path before dispatching another agent:
   - use a quick supervisor review for low-risk, mechanically verifiable diffs;
   - use a separate Terra-High reviewer for cross-task contracts, golden-data authority, artifact immutability, replay lineage, dependency compatibility, or other high-risk changes.
7. Fix Critical/Important findings and re-check only the affected surface. Avoid repeated broad review loops when a focused assertion proves the correction.
8. Append the task completion line to the ledger only after fresh verification.

Do not run multiple implementers in parallel. Do not implement product code directly in the supervisor context when the SDD workflow assigns it to a task agent.

## Non-negotiable implementation constraints

- CLI command remains `rag-eval`; do not add a compatibility alias.
- Raw DOCX/PDF ingestion exercises the production parser; canonical Markdown controls grounding validation.
- Evaluation ingestion stays opt-in so saved index snapshots can be reused.
- Generation replay inherits the retrieval run's complete dataset and selection and rejects replacement filters.
- `ChatResponse` remains unchanged.
- Phase artifacts, including manifests and reports, are write-once. Construct the lineage-complete manifest before its single save; duplicate saves must fail without changing original bytes.
- Ragas remains `>=0.4,<0.5`, opt-in, and lazily imported. Answer Relevancy receives both LLM and embeddings.
- Treat `langchain-community<0.4` only as a resolver probe. During Task 9, run the prescribed import check, capture the compatible installed version, lock its exact equality constraint, and rerun the import check.
- Deterministic correctness invariants block. Rates compared with `0.85` and Ragas scores remain report-only.
- Only a complete, unfiltered 100-case e2e run against the authoritative default golden directory and canonical source can be baseline eligible.
- Missing audit artifacts or failed validation must remain truthful; never claim full conformance early.
- Unit/component tests must not call Qdrant Cloud, paid judges, or live providers. Use `MemoryChunkStore` and deterministic fakes.

## Verification already completed

Before plan revision, the isolated worktree was created from `6d7732c`, `uv sync --frozen` completed, and the existing full `uv run pytest -q` suite passed. No product code, golden data, dependency, or lock-file changes were made during plan revision, so product tests were not rerun for the documentation-only commits.

Final supervisor plan gate at `e691b0e`:

```text
tasks=12 python_blocks=45 syntax=clean finalization=single-write memory_guards=5 baseline=authoritative prior_markers=clean
```

Additional checks passed:

- `rtk git diff --check 6d7732c..e691b0e`
- cumulative changed paths were only the revised plan and byte-identical review evidence;
- worktree was clean before this handoff file was created;
- plan Task 6 covers duplicate local and in-memory saves for manifest, snapshot, retrieval, generation, and report;
- runner mode helpers return unsaved reports and finalization writes a lineage-complete manifest once.

## First commands for the next session

```powershell
cd E:\VIN-INTERNSHIP\Cowork-RAG\.worktree\staged-offline-rag-eval
rtk git status --short --branch
rtk git log -6 --oneline --decorate
rtk read .superpowers\sdd\progress.md
```

Refresh the codebase-memory graph for this exact relocated worktree before code discovery; the earlier index referenced the previous temporary worktree path.

Then extract and dispatch plan Task 0. Its task base is the handoff commit that adds this file, not `HEAD~1` after later multi-commit work.

## Known limitations and stop conditions

- No push or pull request was requested or created.
- No live Qdrant, paid judge, or provider call was made.
- Task 9's exact compatible `langchain-community` equality remains intentionally unresolved until its lock-time import proof.
- If Task 0 reveals a data change beyond the two approved trims or requires weakening exact article containment, stop and ask the user; that would exceed the approved option (a).
