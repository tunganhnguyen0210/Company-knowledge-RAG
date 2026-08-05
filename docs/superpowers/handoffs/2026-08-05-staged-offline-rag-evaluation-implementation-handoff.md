# Offline RAG Evaluation — Implementation Resume Card

## Start Here

- Worktree: `E:\VIN-INTERNSHIP\Cowork-RAG\.worktree\staged-offline-rag-eval`
- Branch: `codex/staged-offline-rag-eval`
- Planning HEAD before the documentation checkpoint: `36f7f57`
- Task 0 base: the current clean HEAD containing this resume card; record its exact SHA before dispatch
- Base: `6d7732c` (`main`)
- Next task: plan **Task 0 — Approved Golden-Data Reissue and Audit Evidence**
- State: planning is complete; product implementation has not started.

Read only these before dispatching Task 0:

1. `AGENTS.md`
2. `docs/superpowers/plans/2026-08-05-staged-offline-rag-evaluation.md` — Global Constraints and Task 0
3. `docs/superpowers/specs/2026-08-05-staged-offline-rag-evaluation-design.md`
4. `evaluation/GOLDEN_SET_SPEC.md`
5. `tests/README.md`

Do not reread the plan-review report or revision commits unless implementation contradicts the current plan. The revised plan is the executable source.

For implementation behavior, this card, `AGENTS.md`, and `tests/README.md` contain the user's latest workflow decisions. They override repeated test/reviewer boilerplate in the older plan or generic SDD skill; the plan remains authoritative for product and data requirements.

## Approved Data Decision

The user approved P0-3 option (a):

- trim AMB-014 context index 1 before `# Chương IX`;
- trim AMB-019 context index 1 before `# Chương IV`;
- reissue the ambiguous dataset and regenerate/reconcile migration and grounding-review evidence;
- preserve every other finalized golden value.

Stop and ask the user if Task 0 requires any additional golden-data change or weaker article containment.

## Execute Task 0

```powershell
cd E:\VIN-INTERNSHIP\Cowork-RAG\.worktree\staged-offline-rag-eval
rtk git status --short --branch
rtk git log -3 --oneline --decorate
rtk read .superpowers\sdd\progress.md
```

1. Refresh codebase-memory for this exact worktree; the old index points at a removed temporary path.
2. Use `superpowers:subagent-driven-development`; extract only Task 0 with its `task-brief` helper.
3. Dispatch one `gpt-5.6-terra` implementer at `high` reasoning. Do not run parallel implementers.
4. Require TDD and the test-evidence rules in `AGENTS.md` and `tests/README.md`. Run a plan-required test after relevant edits, reuse its fresh passing result while the covered surface is unchanged, and expand only for concrete unproven risk. Keep the single final verification required by Task 11 unless that exact command already passed on the identical final tree. No live services.
5. Record the task base before dispatch, commit explicit paths, generate the review package from that base, and update `.superpowers/sdd/progress.md` only after fresh verification.
6. User-approved SDD review override: a quick supervisor review satisfies the task-review gate for mechanical diffs. Dispatch an independent Terra-High reviewer only for golden authority, replay lineage, immutable artifacts, dependency compatibility, or another cross-task contract. Task 0 changes golden authority, so it requires the independent reviewer.

## Constraints Worth Keeping in Working Memory

- CLI remains `rag-eval`; `ChatResponse` stays unchanged.
- Raw DOCX/PDF uses the production parser; canonical Markdown owns grounding validation.
- Generation replay inherits the retrieval dataset/selection and rejects replacements.
- Artifacts are write-once; duplicate saves preserve original bytes.
- Unit/component tests use `MemoryChunkStore` and deterministic fakes, never Qdrant Cloud or paid/live providers.
- Correctness invariants block; `0.85` comparisons and Ragas scores are report-only.
- Only the authoritative, complete, unfiltered 100-case e2e run can be baseline eligible.
- In Task 9, treat `langchain-community<0.4` only as a probe; lock an exact version only after the prescribed Ragas import passes.

## Verified Starting Point

- Existing full suite passed at base after `uv sync --frozen`.
- Final plan gate: `tasks=12 python_blocks=45 syntax=clean finalization=single-write memory_guards=5 baseline=authoritative prior_markers=clean`.
- No product, golden-data, or dependency implementation has occurred.
- No push or pull request exists.
- The worktree must be clean at handoff; keep this documentation checkpoint out of Task 0's explicit-path data commit.

If branch, worktree, or baseline differs from this card, stop and resolve that drift before dispatching Task 0.
