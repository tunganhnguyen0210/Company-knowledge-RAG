# Staged Offline RAG Evaluation Plan Review Handoff

## Reviewer goal

Review the implementation plan for correctness, completeness, internal consistency, and executability before any production code is changed. Review the plan only; do not implement it and do not reopen already approved product scope unless you find a contradiction with an authoritative source.

The plan under review is:

- `docs/superpowers/plans/2026-08-05-staged-offline-rag-evaluation.md`

## Authority order

Use these sources in this order when judging the plan:

1. `evaluation/GOLDEN_SET_SPEC.md` — authoritative golden dataset and grounding contract.
2. `docs/evaluation/RAG_Evaluation_Guide.md` — evaluation lifecycle and quality dimensions.
3. `docs/superpowers/specs/2026-08-05-staged-offline-rag-evaluation-design.md` — approved design decisions and scope.
4. The live production interfaces under `src/` — feasibility and integration constraints.
5. The implementation plan — proposed execution sequence.

If sources conflict, report the conflict explicitly instead of silently choosing a lower-authority source.

## Approved scope that must remain fixed

- Offline evaluation only.
- First raw ingestion target: `data/raw/01_2021_ND-CP_283247.docx`.
- Canonical grounding target: `data/extracted/01_2021_ND-CP_283247.md`.
- Five finalized golden files, 20 cases each, 100 cases total.
- Staged commands: `validate`, `ingest`, `retrieval`, `generation --from-run`, and `e2e` under the `rag-eval` entrypoint.
- E2e ingestion is opt-in; unchanged content is not re-ingested unless explicitly forced.
- Selection uses repeatable `--type`, `--golden-file`, and `--case-id`, plus deterministic round-robin `--limit`.
- Full Ragas is opt-in through `--ragas`; scores are report-only until a baseline and judge calibration exist.
- Blocking deterministic invariants fail a run immediately or make it incomplete. A score below `0.85` alone never blocks.
- Public `ChatResponse` remains unchanged.
- Missing or non-machine-validatable audit artifacts prevent full conformance and baseline eligibility.
- Online monitoring, judge calibration, and production release automation are out of scope.

## Exact review areas

### 1. Golden contract and prerequisite handling

Review Tasks 1 and 4.

Confirm that:

- every standard file must contain exactly IDs `001..020` in its own namespace;
- direct-lookup migration is enforced through `DL-001..DL-020` rather than legacy integer IDs;
- answerable and unanswerable context rules match `GOLDEN_SET_SPEC.md`;
- exact evidence is checked inside the declared canonical article and chapter;
- `id_migration_map.json` and `golden_set_grounding_review.json` are never treated as valid merely because a filename exists;
- standard validation still covers all 100 cases before expensive-phase filtering.

### 2. Lossless ingestion metadata and chunking

Review Tasks 2 and 3, especially:

- `SourceCoordinates` ownership;
- `extract_legal_sections` chapter ancestry;
- the lossless `_split` invariant;
- Qdrant flat payload fields plus nested `Chunk` reconstruction;
- `list_document_chunks` pagination and version filtering;
- protection against LLM enrichment overwriting deterministic coordinates.

Verify that ordered chunks can reconstruct an exact golden excerpt even when the excerpt crosses a chunk boundary.

### 3. Replay integrity and artifact lineage

Review Tasks 5, 6, and 8, especially:

- `ChatService.retrieve`, `generate_from_hits`, and the unchanged public projection;
- volatile-field exclusion in `artifact_fingerprint`;
- immutable `IndexSnapshot`, `RetrievalRun`, and `GenerationRun` models;
- non-overwriting run directories and JSONL reconstruction;
- dataset source files and scope recorded in `RetrievalRun`;
- generation replay refusing invalid dataset or artifact fingerprints;
- semantic scores living in `EvaluationReport`, not changing phase fingerprints;
- `GenerationRun` consuming the exact saved ranked hits without calling `store.search`;
- e2e composition recomputing only the phases required by the approved staged lifecycle.

### 4. Failure and gate semantics

Review Task 8.

Confirm that:

- dataset/canonical failures occur before ingestion, Qdrant, or model access;
- an incompatible index reports the exact recovery command;
- per-case runtime errors are retained while remaining cases continue;
- blocking citation, metadata, chunk recoverability, and execution invariants affect status;
- requested Ragas failures or missing scores make the run incomplete;
- low deterministic quality or Ragas scores are reported against `0.85` without changing status;
- only a complete, unfiltered, fully conformant 100-case e2e run can be baseline eligible.

Pay particular attention to exception paths that occur before a manifest or report is written.

### 5. Ragas v0.4 adapter correctness

Review Task 9 against current Ragas v0.4 documentation.

Confirm the exact imports and calls for:

- `ContextPrecision`;
- `ContextRecall`;
- `Faithfulness`;
- `AnswerRelevancy`;
- `llm_factory`;
- `embedding_factory`;
- `ascore(**kwargs)` and `.value` extraction.

Check that Answer Relevancy receives both an LLM and embeddings, concurrency is bounded, no application phase is rerun by the adapter, and exception reporting cannot expose API keys.

### 6. CLI contract and lazy loading

Review Task 10.

Confirm that:

- the old `company-rag-evaluate` entrypoint is removed and only `rag-eval` is added;
- `--output-root` is consistently a post-subcommand option;
- `validate` rejects type/case/limit filters but permits explicit partial files;
- `retrieval` and `e2e` support approved selection flags;
- `generation` inherits dataset scope and selection from `RetrievalRun` and rejects new filters;
- `--force-reingest` requires an explicit source;
- `--ragas` is the only path that imports and constructs the optional Ragas adapter;
- `validate` never creates FastAPI, Qdrant, generation-provider, or Ragas runtime state;
- CLI exit codes distinguish complete from failed/incomplete runs.

### 7. TDD plan executability and migration safety

Review all 11 tasks.

Confirm that every task has:

- exact file paths;
- a failing test before implementation;
- an expected failure reason;
- concrete implementation content rather than placeholders;
- focused verification commands;
- an explicit, narrow commit;
- interfaces consistent with earlier and later tasks.

Check that `tests/test_evaluation.py` is deleted only after replacement coverage exists, and that the user-owned deleted scripts remain untouched and unstaged.

## Known facts to verify, not "fix" by assumption

- `evaluation/id_migration_map.json` is currently absent.
- `evaluation/golden_set_grounding_review.json` is currently absent.
- `GOLDEN_SET_SPEC.md` names both artifacts but does not define a machine-validatable JSON schema for either.
- The plan deliberately blocks full conformance rather than trusting opaque file presence.
- The first baseline does not yet exist, and the judge is not calibrated.
- Ragas remains report-only even when `--ragas` is requested.

If you believe one of these facts is wrong, cite current repository evidence.

## Required reviewer output

Return findings ordered by severity:

- **P0** — violates an authoritative contract, can corrupt or misattribute evaluation evidence, changes production behavior unexpectedly, or can falsely claim conformance/baseline eligibility.
- **P1** — prevents a task from being implemented or tested as written, creates an interface/type mismatch, or misses a required lifecycle behavior.
- **P2** — maintainability, clarity, or verification weakness that does not invalidate the design.

For every finding include:

1. severity;
2. exact plan task/step and symbol or command;
3. violated authority or invariant;
4. concrete recommended correction;
5. whether the correction changes approved scope.

End with one of these verdicts:

- `APPROVE` — no P0/P1 findings;
- `APPROVE WITH P2` — only non-blocking P2 findings;
- `REVISE` — at least one P0/P1 finding.

If there are no findings, say so explicitly; do not invent stylistic findings to fill the report.

## Suggested read-only review commands

```powershell
rtk read evaluation/GOLDEN_SET_SPEC.md
rtk read docs/evaluation/RAG_Evaluation_Guide.md
rtk read docs/superpowers/specs/2026-08-05-staged-offline-rag-evaluation-design.md
rtk read docs/superpowers/plans/2026-08-05-staged-offline-rag-evaluation.md
rtk git status --short --branch
rtk git diff --check
```

Do not stage, commit, modify, ingest, call a paid judge, or contact external systems during the plan review.
