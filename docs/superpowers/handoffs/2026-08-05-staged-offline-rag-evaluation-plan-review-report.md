# Staged Offline RAG Evaluation Plan — Review Report

**Reviewed plan:** `docs/superpowers/plans/2026-08-05-staged-offline-rag-evaluation.md`
**Review brief:** `docs/superpowers/handoffs/2026-08-05-staged-offline-rag-evaluation-plan-review.md`
**Delegation:** `docs/superpowers/handoffs/2026-08-05-staged-offline-rag-evaluation-plan-review-delegation.md`
**Date:** 2026-08-05
**Mode:** read-only. No file in the plan's scope was modified, nothing was staged or committed, no data was ingested, no paid judge or external service was called.

**Verdict: `REVISE`**

**Counts: P0 = 3, P1 = 7, P2 = 2.**

Authority order used: design spec `docs/superpowers/specs/2026-08-05-staged-offline-rag-evaluation-design.md` > `GOLDEN_SET_SPEC.md` > repository code and test conventions > the plan.

Findings marked *measured* were reproduced by executing the plan's own code verbatim in a scratchpad against the real repository data. Read-only; no repository file was written.

---

## P0 findings

### P0-1 — The approved raw DOCX yields zero legal coordinates; `extract_legal_sections` degenerates to one section

- **Where:** Task 2 Step 3, `src/ingestion/structure.py`, `HEADING_RE = re.compile(r"(?m)^(#{1,6})\s+(.+)$")` and the `if not matches:` fallback in `extract_legal_sections` (plan lines 468, 480–483). Consumed by Task 2 Step 4 `chunk_document`, Task 3 Step 4 `_chunk_payload`, Task 4 `validate_golden_dataset`.
- **Violated authority:** design spec line 28 (raw DOCX ingestion through the production pipeline) taken together with lines 30–32 (deterministic extraction and persistence of `doc_id`, `chapter`, `article`). The plan's extractor can only satisfy line 32 for input that already carries `#` markers, which the approved raw input does not.
- **Evidence (measured):** `parse_document` emits a `#` prefix only when a paragraph carries a Word `Title`/`Heading N` style (`src/ingestion/parser.py`, `_paragraph_text` / `_heading_level`). Parsing `data/raw/01_2021_ND-CP_283247.docx` through the production parser produced **199,555 chars with 0 markdown headings, 0 articles, 0 chapters**, against `data/extracted/01_2021_ND-CP_283247.md` at **110 headings / 101 articles / 9 chapters**. `extract_legal_sections` therefore takes the no-match branch and returns a single 199 KB section with `chapter=None, article=None`.
- **Consequences:** every chunk from the raw DOCX carries null chapter/article; Task 3 Step 5's assertion `{chunk.coordinates.doc_id for chunk in chunks} == {"01_2021_ND-CP_283247.md"}` still passes vacuously (the fallback sets `doc_id`) and hides the defect; Task 4 Step 4's `test_real_docx_chunks_recover_all_answerable_golden_evidence` fails for all 130 contexts because `chunk_text.get(key, "")` returns `""` for every coordinate key; `rag-eval ingest` and `rag-eval e2e --ingest` cannot produce conformant snapshots; coordinate-aware retrieval scoring can never exceed 0.
- **Correction:** make heading detection markup-agnostic instead of markdown-only, e.g.

  ```python
  LEGAL_HEADING_RE = re.compile(
      r"(?m)^(?:#{1,6}[ \t]+)?((?:Chương[ \t]+[IVXLCDM]+|Điều[ \t]+\d+[A-Za-z]?)\b.*)$"
  )
  ```

  and split sections on `LEGAL_HEADING_RE` (using group 1 as the heading text) rather than on `HEADING_RE`. Measured: this regex finds **110 heading lines / 101 articles / 9 chapters in both** the DOCX-parsed text and the canonical Markdown — identical hierarchy from both sources. Additionally, the chunk-recoverability comparison in Task 4 must normalize markdown markers away on both sides (strip a leading `#{1,6}\s+` in `_normalized`), because canonical-derived golden contexts embed `###` while DOCX-derived chunk text never does; measured effect on the raw-DOCX branch: **34 → 2 mismatches**.
- **Changes approved scope:** No. It keeps raw DOCX ingestion through the production pipeline exactly as approved; it is the change that makes design lines 28 and 32 jointly achievable.

### P0-2 — Task 4 Step 1's `assert report.errors == []` fails on the finalized dataset; root cause is the reconstructed article text

- **Where:** Task 4 Step 1, `tests/unit/evaluation/test_validation.py::test_finalized_dataset_is_exactly_grounded`, `assert report.errors == []` (plan line 860). Root cause: Task 2 Step 3 line 498, `section_text = f"{heading}\n\n{body}".strip() if article else body`, consumed by `validate_golden_dataset`'s `article_text` map (plan lines 925–930) and the `context_coordinate_mismatch` branch (line 941).
- **Violated authority:** the plan's own blocking invariant that finalized-dataset validation produces no errors (Task 4 Step 5 expected outcome, line 1031), and design line 400 (dataset/canonical validation must gate every later stage).
- **Evidence (measured):** running the plan's `extract_legal_sections` and the canonical branch of `validate_golden_dataset` verbatim over the finalized 5 files / 100 cases / 130 contexts with `chunks=None` produced **34 `context_coordinate_mismatch` errors across 22 cases**: ADV-002, ADV-003, ADV-014, ADV-015, AMB-008, AMB-014, AMB-016, AMB-017, AMB-018, AMB-019, AMB-020, DL-010, DL-011, DL-018, DL-020, MH-006, MH-007, MH-008, MH-010, MH-011, MH-013, MH-016. Cause: golden contexts are verbatim canonical slices that **include** the `###` heading markers, while the plan rebuilds the article as marker-stripped `heading + "\n\n" + stripped body`. Whitespace-only `_normalized` does not repair this — the normalized comparison yields the same 34.
- **Correction:** use the raw canonical slice as the article text instead of reconstructing it: `section_text = text[match.start():end].strip()` for article sections. Measured: **34 → 2** mismatches (the two remaining are P0-3).
- **Changes approved scope:** No.

### P0-3 — Two finalized golden contexts cross their article boundary, so `errors == []` remains unreachable and `GOLDEN_SET_SPEC.md §9` is contradicted

- **Where:** Task 4 Step 3, `validate_golden_dataset`, the `elif evidence not in article_text.get(key, ""):` branch (plan line 940), evaluated against `evaluation/golden_set/golden_set_ambiguous.json` cases **AMB-014** and **AMB-019**; asserted by Task 4 Step 1 line 860.
- **Violated authority:** `GOLDEN_SET_SPEC.md §9` states 100/100 samples passed grounding-context and metadata exact-source validation. That claim cannot hold under the plan's per-article containment rule.
- **Evidence (measured), after applying the P0-2 correction:**
  - AMB-014, `golden_metadata` = `Chương VIII` / `Điều 94`: 4,414-char context whose tail is `… không còn hiệu lực.\n\n# Chương IX\n\nĐIỀU KHOẢN THI HÀNH`.
  - AMB-019, `golden_metadata` = `Chương III` / `Điều 20`: 1,005-char context whose tail is `… trước khi tổ chức lại.\n\n# Chương IV\n\nHỒ SƠ, TRÌNH TỰ, THỦ TỤC ĐĂNG KÝ DOANH NGHIỆP, …`.
  Both are exact substrings of the canonical Markdown (`context_not_exact_source` does not fire for any of the 130 contexts), but both extend past the end of the article named by their own metadata.
- **Correction — needs a user decision between:**
  - **(a) Data fix:** trim both contexts at their article boundary and re-issue `golden_set_ambiguous.json`, then reconcile `GOLDEN_SET_SPEC.md §9`.
  - **(b) Rule fix:** change the coordinate check to require that the context *starts* inside the keyed article and that any overflow lands in the immediately following section, recording the boundary crossing as a warning rather than an error; then state that rule in the design and in `GOLDEN_SET_SPEC.md §9`.
  Until one is chosen, Task 4 Step 1's `assert report.errors == []` must not be written as an unconditional expectation.
- **Changes approved scope:** **Yes.** Option (a) changes approved dataset content; option (b) changes the approved validation rule. Both require user approval before implementation.

---

## P1 findings

### P1-1 — Shared test fakes are imported from a module path the plan never creates

- **Where:** plan lines 1388, 2248, 3161 — `from tests.evaluation_fakes import …` — against the file the plan creates and stages at `tests/support/evaluation_fakes.py` (lines 1374, 1782, 1897).
- **Violated invariant:** repository test-layout convention; seven existing test files import via `tests.support.*` (e.g. `tests/component/api/test_api.py:7`, `tests/unit/providers/test_jina_key_rotation.py:8`). `pythonpath = ["src", "."]` makes only `tests.support.evaluation_fakes` importable.
- **Effect:** `ModuleNotFoundError` at collection for `tests/unit/evaluation/test_artifacts.py`, `tests/unit/evaluation/test_runner.py`, and `tests/unit/evaluation/test_ragas.py` — three of the plan's verification gates.
- **Correction:** `from tests.support.evaluation_fakes import …` at all three sites.
- **Changes approved scope:** No.

### P1-2 — `tests/support/evaluation_fakes.py` calls `load_golden_dataset` without importing it

- **Where:** Task 6 Step 4, plan line 1820 (`dataset = load_golden_dataset(Path("evaluation/golden_set"), files=[source_file])`) against the module's import block at lines 1786–1796, which imports only `GoldenType` from `evaluation.golden`.
- **Violated invariant:** the module cannot execute.
- **Effect:** `NameError` in `make_retrieval_run`, i.e. in every test that uses the shared fakes.
- **Correction:** `from evaluation.golden import GoldenType, load_golden_dataset`.
- **Changes approved scope:** No.

### P1-3 — Runner test asserts an attribute `InMemoryRunRepository` does not have

- **Where:** Task 8 Step 1, plan line 2389, `assert runner.repository.saved_retrieval is not None`, against `InMemoryRunRepository` as defined in Task 6 Step 3 (plan lines 1738–1768), which exposes `manifests`, `snapshots`, `retrieval_runs`, `generation_runs`, `reports`.
- **Violated invariant:** the test must fail for the stated reason, not on an `AttributeError`.
- **Correction:** `assert runner.repository.retrieval_runs`.
- **Changes approved scope:** No.

### P1-4 — Making `Chunk.coordinates` required breaks four test files the Task 2 modify list omits

- **Where:** Task 2 Step 3, plan line 455 (`coordinates: SourceCoordinates`, no default), against the Task 2 **Files** list (plan lines 353–364).
- **Violated invariant:** the plan's own rule that each task names every file it must touch, and the requirement that the suite stays green at each commit.
- **Evidence:** these files construct `Chunk(...)` directly and are **not** listed: `tests/support/builders.py:17`, `tests/unit/generation/test_citation_gate.py:14,44`, `tests/unit/generation/test_tracing.py:34,58`, `tests/component/rag/test_retrieve_and_answer.py:19,36`. Conversely the list includes `tests/unit/generation/test_abstention.py`, which contains no `Chunk(` construction (it uses the `builders.py` factory).
- **Correction:** add the four files to Task 2's modify and staging lists; drop `tests/unit/generation/test_abstention.py` or keep it only if it is actually edited.
- **Changes approved scope:** No.

### P1-5 — The Ragas pin is insufficient: `import ragas.metrics.collections` fails, so Task 9's own test cannot run

- **Where:** Task 9 Step 2, `eval = ["ragas>=0.4,<0.5"]` (plan line 3212) and its expected outcome "sync completes" (line 3222); consumed by Task 9 Step 4's top-level imports `from ragas.llms import llm_factory` / `from ragas.metrics.collections import …` (plan lines 3276–3278) and Task 9 Step 5's `pytest tests/unit/evaluation/test_ragas.py`.
- **Violated invariant:** the plan's requirement that offline, judge-free tests pass without any network or paid call.
- **Evidence (measured in this repository's venv, ragas 0.4.3):** `import ragas.metrics.collections` and `import ragas.llms` both raise `ModuleNotFoundError: No module named 'langchain_community.chat_models.vertexai'`, from the unguarded top-level import at `ragas/llms/base.py:12`. Ragas declares `langchain-community` with no upper bound, and the installed `langchain-community` 0.4.2 no longer ships that module. `ragas.embeddings` imports cleanly; `ragas/llms/base.py` is the only file in the package that imports `langchain_community`. Because `src/evaluation/ragas_adapter.py` imports `llm_factory` at module scope, `tests/unit/evaluation/test_ragas.py` fails at **collection** even though it injects fakes and makes no model call.
- **Correction:** add an upper bound for `langchain-community` to the `eval` group alongside the Ragas pin, and make Step 2's expected outcome an executable check rather than "sync completes":

  ```powershell
  rtk proxy uv run --group eval python -c "import ragas.metrics.collections"
  ```

  The working bound is the last `langchain-community` release that still exports `langchain_community.chat_models.vertexai` (the 0.3.x line; `<0.4` is the intended constraint). **Unverified:** I did not install a second version to confirm the exact release, since installing would have modified the environment during a read-only review — resolve the exact bound at lock time using the import check above.
- **Changes approved scope:** No (dependency pin plus one verification command).
- **Verified clean, no finding:** the rest of Task 9 matches ragas 0.4.3 exactly — `ContextPrecision(llm=…)`, `ContextRecall(llm=…)`, `Faithfulness(llm=…)`, `AnswerRelevancy(llm=…, embeddings=…)`; `ascore(user_input, reference, retrieved_contexts)`, `ascore(user_input, retrieved_contexts, reference)`, `ascore(user_input, response, retrieved_contexts)`, `ascore(user_input, response)`; `llm_factory(model, provider="openai", client=…)`; `embedding_factory("openai", model=…, client=…)`; results expose `.value`. The `RAGAS_API_KEY` → `OPENAI_API_KEY` fallback in `from_settings` reads keys without printing either value, as required.

### P1-6 — `artifact_fingerprint` excludes volatile fields only at the top level, so identical replays produce different fingerprints

- **Where:** Task 6 Step 3, plan lines 1456–1466: `VOLATILE_ARTIFACT_FIELDS = {...}` used as `value.model_dump(mode="json", exclude=VOLATILE_ARTIFACT_FIELDS)`.
- **Violated authority:** design spec line 423 ("stable artifact and configuration fingerprints"); the review brief names "volatile-field exclusion in `artifact_fingerprint`" as a hotspot.
- **Effect:** a plain set excludes top-level keys only. Per-case volatiles survive into the hash: `cases[].retrieval.latency_ms`, `cases[].retrieval.request_id`, `cases[].generation.latency_ms`, `cases[].generation.usage`. Two runs over identical inputs therefore yield different `run_fingerprint` values, which defeats fingerprint-based replay comparison and baseline equivalence checks.
- **Correction:** use a nested exclude mapping, or strip volatiles in a dedicated helper before hashing:

  ```python
  VOLATILE_ARTIFACT_FIELDS = {
      "run_id": True,
      "created_at": True,
      "snapshot_fingerprint": True,
      "run_fingerprint": True,
      "cases": {
          "__all__": {
              "retrieval": {"latency_ms", "request_id"},
              "generation": {"latency_ms", "usage"},
          }
      },
  }
  ```
- **Changes approved scope:** No.

### P1-7 — `_run_e2e` writes the report and rewrites the manifest three times for one `run_id`

- **Where:** Task 8 Step 6, `EvaluationRunner._run_e2e` (plan lines 3039–3112). It calls `self._run_retrieval(...)` and `self._run_generation(...)`, each of which returns through `self._finish_report(...)` (e.g. lines 2878, 3019), and then calls `self._finish_report(...)` itself at line 3084. `_finish_report` (2546–2552) performs `save_manifest(... artifact_lineage=...)` followed by `save_report(report)`.
- **Violated authority:** design spec's immutable-artifact requirement (lines 175–196, 423) — an e2e run's `report.json` and manifest lineage are written, overwritten, and overwritten again within one run directory, so intermediate states are observable and the lineage is transiently wrong.
- **Correction:** split the phase bodies into `_retrieval_report(...)` / `_generation_report(...)` that build and return an unsaved `EvaluationReport`, and call `_finish_report` exactly once per invocation from the mode entry point. `retrieval.jsonl` / `generation.jsonl` saving stays where it is.
- **Changes approved scope:** No.

---

## P2 findings

### P2-1 — Task 6's lint command omits the file it creates and stages

- **Where:** Task 6 Step 5, plan line 1889: `rtk ruff check src/evaluation/artifacts.py src/evaluation/repository.py tests/unit/evaluation/test_artifacts.py`, against the staging list at line 1897 which includes `tests/support/evaluation_fakes.py`.
- **Effect:** the file carrying P1-2's undefined name is never linted; `ruff` would have caught it (F821).
- **Correction:** add `tests/support/evaluation_fakes.py` to the ruff invocation.
- **Changes approved scope:** No.

### P2-2 — The DOCX recoverability guard is marked `integration` and is excluded from the final verification gate

- **Where:** Task 4 Step 4, `@pytest.mark.integration` on `test_real_docx_chunks_recover_all_answerable_golden_evidence` (plan line 992), against `pyproject.toml`'s marker definition `integration: requires external infrastructure`, and Task 11's expected outcome "all non-integration tests PASS" (plan line 3877).
- **Effect:** the test needs no external infrastructure — it reads two local files. Task 4 Step 5 does run it (no `-m` filter), but Task 11's full-verification gate never re-runs the single check that would catch a regression of P0-1.
- **Correction:** drop the marker, or add this test path explicitly to Task 11's verification command.
- **Changes approved scope:** No.

---

## Checked and clean (no findings)

- `_split` losslessness (Task 2 Step 4, plan lines 542–559): fuzz-tested with 3,000 random strings at `max_chars ∈ {1, 2, 3, 5, 40, 1200}` — `"".join(_split(t, n)) == t.strip()` held in every case.
- `context_not_exact_source` (Task 4 Step 3, line 938): all 130 finalized contexts are exact substrings of `data/extracted/01_2021_ND-CP_283247.md` when read with `encoding="utf-8"`. The CRLF/LF difference between the raw decree and the golden set does not produce an error here.
- `context_contains_ellipsis` (line 942): zero occurrences across the 130 contexts.
- Article-key uniqueness in `article_text` (lines 926–930): 101 article sections map to 101 distinct `(doc_id, chapter, article)` keys — no silent overwrite.
- Task 3 Step 4 `_chunk_payload` (lines 721–724): the flattened top-level `doc_id`/`chapter`/`article` keys do not break `Chunk.model_validate(record.payload)`; `Chunk` uses pydantic's default `extra="ignore"`.
- Task 10 `_build_runtime`: every `app.state.*` attribute it reads (`settings`, `store`, `provider`, `registry`, `tracer`, `ingestion`, `chat`) exists in `src/api/app.py:61–67`.
- Task 10 CLI: `RagasJudge` is imported lazily inside the judge branch (plan line 3742), so P1-5 does not break `rag-eval` subcommands that omit `--ragas`.
- Ragas API surface for ragas 0.4.3 — see the closing note in P1-5.

## Note on the review brief

The review brief's hotspot list refers to `tests/test_evaluation.py`. That path does not exist; the legacy file is `tests/unit/evaluation/test_scoring.py`, which the plan names correctly at line 3119. This is a stale reference in the brief, not a plan defect, so it is not counted as a finding.

---

## Verdict

**`REVISE`** — P0 = 3, P1 = 7, P2 = 2.

P0-1 and P0-2 are implementation defects with concrete, scope-preserving corrections; they must land before Task 4 can pass. **P0-3 requires a user decision** (trim the two golden contexts, or relax the coordinate rule and update `GOLDEN_SET_SPEC.md §9`) before Task 4 Step 1's expectation can be written truthfully. All seven P1 findings have mechanical corrections that change no approved scope.
