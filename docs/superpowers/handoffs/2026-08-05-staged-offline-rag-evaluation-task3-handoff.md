# Staged Offline RAG Evaluation — Task 3 Resume Card

You are the supervisor (controller) resuming this plan. Tasks 0, 1, and 2 are complete. Your next task is plan Task 3.

## Start Here

- Worktree: `E:\VIN-INTERNSHIP\Cowork-RAG\.worktree\staged-offline-rag-eval`
- Branch: `codex/staged-offline-rag-eval`; base `6d7732c` (`main`). HEAD is `8120639`, worktree clean.
- Commit chain: `c546f15` (Task 0) → `f793589` (Task 1) → `0ea1961` + `8120639` (Task 2).
- Ledger: `.superpowers/sdd/progress.md`. **Read it first.** This flat path is mandated by the user — do not create a per-plan ledger elsewhere. It carries the full commit chain, both review verdicts per task, every deferred minor, and the open questions below.
- Artifact workspace (briefs, implementer reports, review packages, reviews): `.superpowers/sdd/2026-08-05-staged-offline-rag-evaluation/`
- Plan — the executable source of truth for product and data requirements: `docs/superpowers/plans/2026-08-05-staged-offline-rag-evaluation.md`. Task 3 begins at line 767.

Read only these before dispatching Task 3:

1. `AGENTS.md`
2. The plan's Global Constraints section + Task 3 only
3. `docs/superpowers/specs/2026-08-05-staged-offline-rag-evaluation-design.md`
4. `evaluation/GOLDEN_SET_SPEC.md`
5. `tests/README.md`
6. The prior resume card `docs/superpowers/handoffs/2026-08-05-staged-offline-rag-evaluation-implementation-handoff.md` — specifically its "Constraints Worth Keeping in Working Memory" section, verbatim.

Do not reread the plan-review report or the plan-revision commits unless implementation contradicts the current plan. The revised plan is the executable source.

For workflow behavior, this card, `AGENTS.md`, and `tests/README.md` carry the user's latest decisions and override any repeated test/reviewer boilerplate in the older plan text. The plan remains authoritative for product and data requirements.

## Execution Workflow (user-approved, non-negotiable)

The process is: one implementer per task → task review (spec compliance + code quality, **both verdicts required**) → fix loop if needed → ledger update → next task. After the last task, one broad whole-branch review.

1. **Extract the task text to its own brief file** before dispatching, so the implementer reads requirements from a file rather than from a pasted prompt. Existing briefs are in the artifact workspace as `task-N-brief.md`; follow that naming. The brief is the single source of exact values (numbers, strings, signatures, test cases).
2. **Record the task base** (`git rev-parse HEAD`) before dispatch. You need it for the review diff.
3. **Dispatch one fresh implementer per task. Never run implementers in parallel** — they conflict.
4. Give the implementer: one line on where the task fits, the brief path, interfaces/decisions from earlier tasks the brief cannot know, your resolution of any ambiguity you spotted in the brief, and a report file path (`task-N-report.md`). Do not paste accumulated session history into a dispatch.
5. **Generate the review diff from the recorded base, never `HEAD~1`** — a task can span multiple commits and `HEAD~1` silently truncates it. Hand the reviewer a file, e.g.:
   ```
   git log --oneline BASE..HEAD > review.diff
   git diff --stat BASE..HEAD >> review.diff
   git diff -U10 BASE..HEAD >> review.diff
   ```
   Existing packages in the workspace are named `review-<base>..<head>.diff`.
6. **Reviewer inputs are three file paths** — brief, implementer report, review diff — plus the plan's Global Constraints copied verbatim. Never pre-judge findings for a reviewer; do not tell it what not to flag.
7. **Review gate:** a quick supervisor review satisfies the task-review gate for mechanical diffs. Dispatch an **independent** reviewer only for golden authority, replay lineage, immutable artifacts, dependency compatibility, or another cross-task contract. **Task 3 changes the persisted Qdrant payload contract, so it requires an independent reviewer.**
8. **Fix loop:** max 5 rounds per task. Rounds 1–3 go back to the implementer that did the work if your harness can resume it, otherwise a fresh implementer carrying the brief, report, and findings verbatim. Rounds 4–5 use a fresh implementer on a stronger model. Minor findings never enter the loop — record them in the ledger as `Task <N>: minor (deferred): <one-liner>` for the final review to triage. A finding that conflicts with what the plan mandates is the **user's** decision: present the finding beside the plan text and ask which governs.
9. **Update the ledger only after fresh verification.** The ledger is your recovery map if you lose context — trust it and `git log` over recollection.
10. **Commit explicit paths only. Never run `git add -A` or `git add .`** — the repo carries unrelated user changes that must be preserved.
11. Worktree must be clean at handoff.

**Verify subagent claims yourself.** Do not take a self-reported PASS at face value. In Task 2 the implementer's scoped test run was green while the full suite had two real failures, and it separately misattributed an environment fault to the diff.

## Model Delegation

Use the least capable model that can do the job; always specify it explicitly rather than inheriting a default.

- Task text contains complete code → transcription plus testing → cheapest tier.
- Multi-file integration or judgment → mid tier.
- Architecture, or the final whole-branch review → strongest tier.
- Reviewers → scale to diff risk; mid tier is the floor.
- Fix rounds 4–5 → at least one tier above the implementer that got stuck.

Turn count dominates cost more than per-token price: the cheapest models often take 2–3× the turns on multi-step work.

## Environment Gotcha

This machine has `SSL_CERT_FILE` pointing at a path that does not exist. It makes the Jina provider tests fail spuriously and makes mypy print a warning. It is unrelated to any diff. Prefix every verification command:

```bash
env -u SSL_CERT_FILE -u REQUESTS_CA_BUNDLE uv run pytest -q
env -u SSL_CERT_FILE -u REQUESTS_CA_BUNDLE uv run ruff check .
env -u SSL_CERT_FILE -u REQUESTS_CA_BUNDLE uv run mypy
```

Verified green baseline on `8120639`: **119 passed**, ruff clean, mypy clean (43 source files).

`pyproject.toml` sets `pythonpath = ["src", "."]`, so imports carry no `src.` prefix: `domain.schemas`, `ingestion.structure`, `evaluation.golden`.

## Task 3 Must Close a Carried-Forward Defect

Task 2 made `Chunk.coordinates` a required field with no default. `src/retrieval/qdrant_store.py:139,151` reconstructs chunks via `Chunk.model_validate(point.payload)`, which now raises `pydantic.ValidationError` on any Qdrant point persisted before this change, since old payloads lack that key.

Task 2's brief deliberately excluded that file from its scope; the plan assigns `src/retrieval/qdrant_store.py` to Task 3. **Task 3 must close this** — reindex or an explicit migration path — before any populated collection is read. Recorded in the ledger as an Important carried finding, not a Task 2 gap.

## Two Open Questions — Ask the User, Do Not Assume

1. **Non-legal documents lost heading-derived `section`.** Task 2 replaced the old `_sections` helper (which matched *any* markdown heading) with `extract_legal_sections` (only `Chương`/`Điều`, with or without a leading `#`). A generic `# Leave` heading or a plain DOCX heading now yields `section=None` and bare `coordinates` with no chapter or article. This follows from the brief but was **never stated as an intended product change**. It is fine if the corpus is only the decree; it is a regression if ingestion must stay general-purpose, in which case `extract_legal_sections` needs a generic-heading fallback. Raised twice with the user, still unanswered.
2. **Live Qdrant exposure.** Whether a populated collection already holds pre-migration points is unknowable offline and is a deployment question for the user.

## Deferred Minors Awaiting the Final Whole-Branch Review

Full detail in the ledger:

- Task 0: `id_migration_map` `61 -> DL-017` is a question rewording, not a verbatim carry-over.
- Task 1: `load_golden_dataset(files=[])` — `files or [...]` truthiness makes an empty list fall through to all five default files while skipping authoritative validation and mislabelling `scope="partial"`; the fix is `files is None`.
- Task 1: duplicate-ID, wrong-count, prefix-mismatch, `multi_hop<2`, `limit<1`, empty-selection and partial-mode branches have no dedicated test.
- Task 2: `tests/support/builders.py` uses `coordinates or SourceCoordinates(...)` truthiness instead of `is None` — the same bug shape as the Task 1 minor.
- Task 2: `_split` infinite-loops if `max_chars <= 0`; unreachable via `CHUNK_MAX_CHARS = 1200`.

## Remaining Scope

Tasks 3–11, in plan order:

3. Coordinate Persistence and Index Snapshot Reads
4. Canonical Grounding and Chunk-Recoverability Validation
5. Internal Retrieval and Generation Evidence
6. Immutable Artifacts, Fingerprints, and Run Repository
7. Deterministic Retrieval and Generation Metrics
8. Staged `EvaluationRunner` Modes and Failure Semantics
9. Ragas v0.4 Report-Only Judge Adapter
10. `rag-eval` CLI and Approved Selection Contract
11. Documentation, Full Verification, and Optional Smoke Command

## Hard Constraints

- **No live services.** Unit and component tests use `MemoryChunkStore` and deterministic fakes — never Qdrant Cloud, never paid or live providers.
- **TDD required:** write the failing test, prove red, implement, prove green.
- Frozen and audited — never edit these to make a test pass: `evaluation/golden_set/**`, `evaluation/id_migration_map.json`, `evaluation/golden_set_grounding_review.json`, `evaluation/GOLDEN_SET_SPEC.md`.
- Do not modify `evaluation/golden_set/` unless the task explicitly concerns evaluation data.
- Do not reuse golden ID `65` or invent a replacement for it.
- Do not weaken the coordinate rule.
- CLI remains `rag-eval`; `ChatResponse` stays unchanged.
- Artifacts are write-once; duplicate saves preserve original bytes.
- Correctness invariants block; `0.85` comparisons and Ragas scores are report-only.
- Only the authoritative, complete, unfiltered 100-case e2e run can be baseline eligible.
- In Task 9, treat `langchain-community<0.4` only as a probe; lock an exact version only after the prescribed Ragas import passes.
- **No push and no pull request exists. Do not create one.**

## First Actions

```bash
cd E:\VIN-INTERNSHIP\Cowork-RAG\.worktree\staged-offline-rag-eval
git status --short --branch
git log -3 --oneline --decorate
cat .superpowers/sdd/progress.md
```

If branch, HEAD, or worktree cleanliness differs from this card, stop and resolve that drift before dispatching Task 3.
