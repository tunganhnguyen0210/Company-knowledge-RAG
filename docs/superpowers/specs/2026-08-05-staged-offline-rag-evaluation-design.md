# Staged offline RAG evaluation lifecycle

## Status

Approved design for the first offline evaluation lifecycle. The console command is
`rag-eval`; it replaces the longer `company-rag-evaluate` entrypoint.

## Goal

Create a clean, expandable offline evaluation system for the premature RAG pipeline.
It must evaluate the real raw-document ingestion path, deterministic legal metadata,
chunking, retrieval, citation-gated generation, and a small Ragas metric set. It must
also let developers change one pipeline phase without unnecessarily recomputing or
confounding the other phases.

The design follows two authorities:

1. [`evaluation/GOLDEN_SET_SPEC.md`](../../../evaluation/GOLDEN_SET_SPEC.md) defines
   the golden dataset and grounding contract.
2. [`docs/evaluation/RAG_Evaluation_Guide.md`](../../evaluation/RAG_Evaluation_Guide.md)
   defines the offline RAG evaluation lifecycle and quality dimensions.

## Scope

The first implementation covers:

- deterministic validation of the finalized five-file, 100-case golden dataset;
- raw DOCX ingestion for `data/raw/01_2021_ND-CP_283247.docx` through the production
  parser, with the design remaining compatible with the existing PDF path;
- canonical-source validation against
  `data/extracted/01_2021_ND-CP_283247.md`;
- deterministic extraction and persistence of `doc_id`, `chapter`, and `article`;
- metadata-preserving chunking and Qdrant indexing;
- retrieval-only, generation-replay, and end-to-end evaluation;
- deterministic retrieval/generation measurements;
- on-demand Ragas context precision, context recall, faithfulness, and answer
  relevancy;
- reproducible, replayable evaluation artifacts and reports.

Online production monitoring, automated judge calibration, and semantic release
gates are outside this first implementation.

## Golden dataset prerequisites

The authoritative specification requires five files with exactly 20 cases each and
prefixed IDs (`DL`, `MH`, `UA`, `AMB`, and `ADV`). The migration of
`golden_set_direct_lookup.json` to `DL-001..DL-020` is prerequisite zero and is now
present in the repository.

The specification also names `id_migration_map.json` and
`golden_set_grounding_review.json` as audit artifacts. They are not currently present
under `evaluation/`. The implementation must either generate and validate those
artifacts or the specification must be explicitly revised before the validator can
claim full conformance. The evaluator must not silently claim they exist.

## Current gaps

The current implementation cannot evaluate the finalized dataset correctly:

- `GoldenCase` consumes legacy `expected_sources`, `should_abstain`, and `category`
  fields, so finalized IDs, types, difficulties, contexts, and legal metadata are
  discarded.
- The CLI defaults to the removed monolithic `evaluation/golden_set.json`.
- Chunk enrichment produces free-form LLM key/value metadata rather than the
  deterministic legal coordinates required by the golden specification.
- The flat `section` field loses chapter ancestry when an article heading becomes the
  current section.
- `ChatResponse` exposes only retrieval count and latency, so the evaluator cannot
  calculate context metrics from the chunks actually retrieved.
- The current runner is a single end-to-end loop and has no replayable index,
  retrieval, or generation artifacts.

## Design principles

1. **The real pipeline is evaluated.** Raw DOCX/PDF parsing, production chunking,
   indexing, retrieval, and generation are not replaced by evaluation-only copies.
2. **Canonical text and raw input have different roles.** Raw files exercise
   ingestion; canonical Markdown validates exact evidence and coordinates.
3. **Structural metadata is deterministic.** LLM enrichment may improve retrieval
   text but cannot create or overwrite authoritative coordinates.
4. **The public response contract stays small.** Evaluation evidence is internal and
   is not added to the public `ChatResponse`.
5. **Phase artifacts are immutable and replayable.** Each phase records the inputs
   and configuration that produced it.
6. **One deep evaluation module owns orchestration.** Callers and tests use one small
   interface while phase complexity remains inside the module.
7. **Quality scores do not become gates before calibration.** Correctness invariants
   block immediately; Ragas and other quality rates are report-only in v1.

## Top-level module and interface

The external seam is one deep module:

```python
EvaluationRunner.run(request: EvaluationRequest) -> EvaluationReport
```

`EvaluationRequest` selects a mode, dataset scope, source/index inputs, and output
location. `EvaluationReport` returns the complete status and artifact references.
CLI subcommands are thin projections onto this interface rather than separate
implementations.

The module has internal seams for owned persistence and true external dependencies:

- a local JSON/JSONL run-repository adapter and an in-memory test adapter;
- the configured generation provider and fake provider adapters already used by tests;
- the real Ragas judge adapter and a deterministic fake judge adapter.

Internal seams are not exposed through the external interface merely for testing.

## Source identities and metadata contract

The system keeps physical and logical identities separate:

| Field | Value for v1 | Purpose |
|---|---|---|
| `source_name` | `01_2021_ND-CP_283247.docx` | Physical uploaded file |
| internal `document_id` | Existing UUID | Registry/version/index identity |
| canonical `doc_id` | `01_2021_ND-CP_283247.md` | Golden and retrieval scoring identity |
| `chapter` | `Chương I..IX` | Legal hierarchy coordinate |
| `article` | `Điều 1..101` | Legal hierarchy coordinate |

The domain owns a typed coordinate value:

```python
class SourceCoordinates(BaseModel):
    doc_id: str
    chapter: str | None
    article: str | None
```

Chunks carry `SourceCoordinates`. The Qdrant adapter persists flat payload keys
`doc_id`, `chapter`, and `article` so filters and deterministic metrics remain simple.
The existing UUID `document_id`, version, source name, section, position, and content
hash remain available.

## Deterministic structure extraction and chunking

The ingestion flow becomes:

```text
raw DOCX/PDF
  -> existing parser emits normalized Markdown-like text
  -> legal structure extractor tracks heading ancestry
  -> structured article sections carry doc/chapter/article
  -> chunker splits section bodies without dropping coordinates
  -> optional LLM enrichment adds retrieval text only
  -> embeddings and Qdrant payloads
```

The structure extractor maintains a heading stack. A `Chương` heading updates the
current chapter. An `Điều` heading starts an article section and inherits the current
chapter. Every split chunk inherits the same coordinates as its parent article.
Non-article preamble text may have null chapter/article values but must not be used to
satisfy answerable golden evidence.

`auto_metadata`, summaries, contextual prefixes, and hypothetical questions remain
optional retrieval enrichment. They are stored separately and cannot modify
`SourceCoordinates`. Embeddings may use enriched `retrieval_text`; grounding,
citations, and evaluation always use original chunk text.

## Phase artifacts

The evaluation lifecycle produces four immutable artifact types.

### IndexSnapshot

Records:

- raw and canonical source hashes;
- canonical `doc_id` and internal document/version identity;
- parser, structure extractor, chunker, enrichment, embedding, and index settings;
- chunk count and metadata validation summary;
- Qdrant collection/index identity;
- an overall snapshot fingerprint.

### RetrievalRun

Records, for every selected golden case:

- case ID, type, difficulty, and question;
- index snapshot fingerprint;
- query and retrieval configuration;
- ranked original chunks with scores, coordinates, IDs, positions, and hashes;
- retrieval latency and deterministic retrieval metrics;
- a retrieval-run fingerprint.

### GenerationRun

Records:

- source retrieval-run fingerprint;
- prompt version, provider, model, and generation settings;
- generated answer, structured model response, validated citations, usage, and
  latency for each case;
- a generation-run fingerprint.

### EvaluationReport

Records:

- deterministic validation and metric results;
- Ragas results;
- overall, type, and difficulty aggregates;
- errors and completeness;
- artifact lineage and baseline eligibility.

Fingerprints are content/configuration hashes, not timestamps. Replay validates
fingerprint compatibility before any model call.

## Evaluation modes

### validate

Validates the authoritative golden dataset and canonical Markdown without Qdrant or
model calls. It always checks the complete standard dataset unless explicit
`--golden-file` partial mode is used.

### ingest

Exercises raw parsing, metadata extraction, chunking, optional enrichment, embedding,
and indexing, then produces an `IndexSnapshot`. Normal ingestion remains idempotent by
content hash. Forced ingestion replaces the active indexed version only after the new
version is ready.

### retrieval

Runs selected questions against an existing compatible index and produces a
`RetrievalRun`. It does not invoke answer generation. This isolates query,
hybrid-search, RRF, score filtering, top-k, and reranker changes.

### generation

Loads a compatible `RetrievalRun` and regenerates answers from exactly those saved
contexts. This isolates prompt, provider/model, temperature, and structured-output
changes from retrieval variance. It calculates generation and Ragas generation
metrics but does not claim end-to-end success.

### e2e

Runs retrieval, generation, deterministic metrics, and Ragas metrics together.
Ingestion is opt-in. A complete, unfiltered 100-case e2e run is the only mode eligible
to establish a future baseline.

## Development workflows

| Changed phase | Reused artifact | Recomputed phases | Required final confirmation |
|---|---|---|---|
| Ingestion, metadata, chunking, embeddings | Golden dataset | Index, retrieval, generation | Full e2e |
| Query, hybrid retrieval, RRF, filtering, reranking | Compatible IndexSnapshot | Retrieval, then generation | E2e smoke/full run |
| Prompt, model, or generation settings | Exact RetrievalRun | Generation only | E2e smoke run |

This gives developers phase attribution without removing the final integrated check.

## CLI contract

The console entrypoint is `rag-eval`. The old `company-rag-evaluate` script is
replaced, and repository documentation must use the short name.

Examples:

```powershell
# Validate all 100 authoritative cases.
rag-eval validate

# Build or update the index through the real raw DOCX path.
rag-eval ingest --source data/raw/01_2021_ND-CP_283247.docx

# Explicitly rebuild the indexed document.
rag-eval ingest `
  --source data/raw/01_2021_ND-CP_283247.docx `
  --force-reingest

# Evaluate retrieval changes for ten multi-hop cases.
rag-eval retrieval --type multi_hop --limit 10

# Replay a prompt/model change against fixed retrieval evidence.
rag-eval generation --from-run <retrieval-run-id>

# Reuse the existing index for a ten-case integrated run.
rag-eval e2e --limit 10

# Opt into ingestion before an integrated run.
rag-eval e2e `
  --ingest data/raw/01_2021_ND-CP_283247.docx `
  --limit 10
```

`--force-reingest` is invalid unless the command also supplies an ingestion source.
Without ingestion, index-dependent modes perform a preflight and fail with the exact
recovery command when the expected index is missing or incompatible.

### Dataset selection

The selection interface is:

- `--golden-dir PATH`, defaulting to `evaluation/golden_set`;
- repeatable `--type TYPE` for the five standard types;
- repeatable `--golden-file PATH` for explicit partial/experimental files;
- repeatable `--case-id ID` for targeted regressions;
- `--limit N` applied after other filters.

`--golden-file` and `--type` are mutually exclusive. Standard directory/type runs
validate all 100 authoritative cases before filtering expensive phases. Explicit-file
runs validate only supplied files and report `scope=partial`. Unknown IDs, empty
selections, and incompatible flags fail before ingestion or model calls.

`--limit` uses a stable round-robin selection across selected types. It does not alter
full-dataset validation. Reports record both `dataset_size` and `evaluated_cases`.
Limited, filtered, case-specific, retrieval-only, generation-only, and partial-file
runs are never baseline eligible.

## Deterministic checks and metrics

### Blocking correctness invariants

| Area | Required invariant |
|---|---|
| Golden dataset | Five standard files, 20 cases each, valid prefixed IDs/types, no duplicates |
| Grounding | Every answerable excerpt is exact canonical text in its declared chapter/article |
| Raw ingestion | Parser succeeds and produces a `READY` document |
| Metadata | Answerable chunks contain correct canonical doc/chapter/article coordinates |
| Chunking | Every golden excerpt is recoverable from ordered chunks in its article |
| Index payload | Original text, coordinates, position, version, and hash survive persistence |
| Citations | Every emitted citation maps to a chunk retrieved for that question |
| Execution | Requested phases finish without infrastructure or case-execution errors |

### Report-only deterministic quality

- coordinate recall@k, requiring all unique coordinates for multi-hop cases;
- exact evidence recall@k from ordered retrieved chunks;
- citation validity and sentence citation coverage;
- abstention accuracy for `unanswerable` cases;
- mean and p95 retrieval and end-to-end latency.

Metrics are aggregated overall, by type, and by difficulty. The report compares rates
to the documented `0.85` target but does not use those rates as release gates in v1.

## Ragas adapter

Ragas consumes evidence already captured by retrieval and generation. It never
re-ingests documents or reruns retrieval/generation for each metric.

The adapter mapping is:

| Ragas field | Evaluation evidence |
|---|---|
| `user_input` | Golden `question` |
| `retrieved_contexts` | Original texts of ranked retrieved chunks |
| `response` | Generated answer |
| `reference` | Golden `expected_answer` |

The initial metrics are:

- context precision;
- context recall;
- faithfulness;
- answer relevancy.

Retrieval mode can calculate the context metrics. Generation and e2e modes calculate
faithfulness and answer relevancy when answers are available. Scores are stored per
case and aggregated overall/by type/by difficulty.

The implementation should pin one supported Ragas minor series rather than allowing
unreviewed API drift across `>=0.3,<1`; the current design targets the v0.4 dataset and
metric interfaces and should record the exact installed version in every report.

Ragas judge calls are on-demand, may use external model credentials, and can cost
tokens. Scores below `0.85` remain report-only until a human-labeled calibration set
and a stable full-run baseline exist.

Golden Question Quality remains part of the dataset reviewer workflow because it
judges the reference dataset rather than a pipeline execution. A separately calibrated
custom judge may be added later without changing the four core Ragas fields.

## Run repository and report layout

Each run gets a non-overwriting directory:

```text
reports/rag_evaluation/<run-id>/
  manifest.json
  index_snapshot.json          # when created or referenced
  retrieval.jsonl              # when retrieval ran or was replayed
  generation.jsonl             # when generation ran
  report.json
```

`manifest.json` records command arguments, selection, timestamps, Git revision,
dataset/source/configuration fingerprints, dependency/metric versions, and artifact
lineage. `report.json` records status, checks, aggregates, errors, and
`baseline_eligible`.

Raw evaluation evidence is local offline data and must follow repository ignore and
privacy rules. The evaluator does not require Langfuse full tracing and does not make
trace payloads its contract.

## Failure handling

- Dataset or canonical-source validation fails before ingestion, Qdrant, or model
  access.
- Ingestion failures do not delete the previously ready indexed version.
- Missing/incompatible indexes fail preflight with a recovery command.
- Per-case RAG failures are recorded while remaining cases continue; the run is
  incomplete and exits unsuccessfully.
- Ragas scores below threshold do not fail. Missing/crashed requested Ragas
  evaluations make the run incomplete because the requested phase did not finish.
- Reports are retained for failed/incomplete runs so successful evidence is not lost.
- Generation replay refuses artifacts with incompatible dataset, case selection,
  coordinate schema, or retrieval evidence fingerprints.

## Test strategy

Tests use the same `EvaluationRunner.run` interface as CLI callers.

### Unit and contract tests

- finalized golden v1 schema, ID/file counts, exact grounding, and coordinates;
- direct-lookup migration and missing audit-artifact diagnostics;
- DOCX-derived heading hierarchy and chapter propagation;
- long-article chunk splitting without evidence or coordinate loss;
- Qdrant payload serialization/validation of source coordinates;
- stable artifact and configuration fingerprints;
- type/file/case/limit selection and incompatible flags;
- public `ChatResponse` projection from internal execution evidence;
- Ragas field mapping and metric routing with a fake judge;
- compatibility rejection for invalid replay artifacts;
- idempotent, skipped, and forced ingestion paths.

### Integration tests

- raw DOCX -> parser -> metadata -> chunks -> in-memory/test store;
- Qdrant payload round trip when the integration dependency is available;
- retrieval-only run with controlled ranked hits;
- generation replay with fixed contexts and fake provider;
- end-to-end runner with fake external adapters and a real report directory;
- full deterministic validation against the finalized 100-case dataset.

### Optional external smoke test

An explicitly invoked smoke test uses the raw DOCX, Qdrant, configured generation
provider, Ragas judge, and a small `--limit`. Paid/network calls are never required by
the default unit suite.

## Acceptance criteria

The design is implemented when:

1. `rag-eval validate` enforces the finalized specification and reports missing audit
   artifacts honestly.
2. Raw DOCX ingestion produces metadata-bearing chunks whose golden evidence is fully
   recoverable.
3. Ingestion is opt-in for e2e runs and unchanged documents are not reprocessed.
4. Retrieval, generation replay, and e2e modes produce typed, fingerprinted artifacts.
5. Type/file/case/limit selection follows the approved precedence and baseline rules.
6. Ragas evaluates captured evidence once with the four approved metrics and remains
   report-only.
7. Public chat responses and citation gating remain unchanged.
8. Reports provide phase attribution and enough provenance to reproduce comparisons.
9. Focused tests pass without network or paid model calls.

## Explicit non-goals

- online production evaluation or monitoring;
- automatic modification or deletion of golden cases;
- automatic deployment/release blocking from uncalibrated Ragas scores;
- a generic plugin framework for hypothetical future phases;
- evaluating multiple source documents in the first quick-eval implementation;
- using Langfuse full traces as the evaluator's source of truth.
