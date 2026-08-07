# Observability, Quality Evaluation & Operations

## Fresher AI Engineer Key Concepts

> [!NOTE]
> **Why Measure RAG Performance?**  
> RAG applications cannot be evaluated on subjective human inspection alone. We use:
> 1. **Structured Tracing (Langfuse)**: To measure latency, token counts, and step-by-step performance of retrieval and generation pipelines in real-time.
> 2. **Golden-Set Benchmarks**: Automated regression testing on known question-answer pairs to evaluate retrieval recall, groundedness, citation accuracy, and abstention correctness.

## Observability & Tracing Architecture

### Langfuse Integration (`src/observability/tracing.py`)
The system captures structured telemetry across three nested span levels:
1. **`rag-request` Span**: Parent span tracking total request execution, user query, request ID, and final latency.
2. **`retrieval` Span**: Child span recording hybrid retrieval latency, candidate hit count, and min-score filtering stats.
3. **`generation` Span**: Child span logging LLM provider name, model identity, token usage (input/output), and raw model response.

### Trace Modes & Privacy Rules
Configured via `TRACE_MODE` in `settings.py`:
- **`off`**: Disables all tracing telemetry.
- **`metadata-only`**: Sends request IDs, timestamps, latency, token usage, hit counts, chunk identity, and source coordinates to Langfuse, but redacts raw query text, document content, prompts, and answers.
- **`full`**: Captures complete prompt text, context chunks, raw chunk `text`, and raw LLM answers. Requires explicit `ALLOW_SENSITIVE_TRACING=true`.

Retrieval enrichment fields (`retrieval_text`, `summary`, `hypothesis_questions`, and `auto_metadata`) are never copied into retrieval trace payloads in either mode. They improve indexing and ranking, but are not trace evidence.

#### Abstract Payload Comparison (`metadata-only` vs. `full`)

For a user query `"Thủ tục cấp Giấy chứng nhận đăng ký doanh nghiệp thế nào?"`:

**1. `metadata-only` Mode Payload (Enterprise Privacy & GDPR Compliant)**
```json
{
  "name": "generation",
  "metadata": {
    "request_id": "req-8f92a4b1",
    "provider": "gemini",
    "model": "gemini-3.5-flash-lite",
    "input_tokens": 842,
    "output_tokens": 156,
    "latency_ms": 1240,
    "retrieved_chunk_count": 5,
    "cited_chunk_ids": ["ecb49b09-v2:10"],
    "source_coordinates": [
      { "doc_id": "01_2021_ND-CP_283247.md", "chapter": "Chương I", "article": "Điều 6" }
    ]
  }
}
```
*(All sensitive text fields — `question`, `prompt`, `user_prompt`, `system_instruction`, `context`, `text`, `parsed_text`, `response`, `answer` — are stripped before transmission to Langfuse).*

**2. `full` Mode Payload (Staging & Local Debugging)**
```json
{
  "name": "generation",
  "metadata": {
    "request_id": "req-8f92a4b1",
    "provider": "gemini",
    "model": "gemini-3.5-flash-lite",
    "input_tokens": 842,
    "output_tokens": 156,
    "latency_ms": 1240,
    "question": "Thủ tục cấp Giấy chứng nhận đăng ký doanh nghiệp thế nào?",
    "context": [
      {
        "chunk_id": "ecb49b09-v2:10",
        "doc_id": "01_2021_ND-CP_283247.md",
        "article": "Điều 6",
        "text": "### Điều 6. Giấy chứng nhận đăng ký doanh nghiệp..."
      }
    ],
    "user_prompt": "Answer the question using only the retrieved context...",
    "answer": "Giấy chứng nhận đăng ký doanh nghiệp được cấp cho doanh nghiệp khi có đủ hồ sơ hợp lệ... [C1]"
  }
}
```

### Active Traced Pipelines & Payload Schema

The system actively traces two primary workflows: the **Query & Generation Pipeline** (`ChatService`) and the **Document Ingestion Pipeline** (`IngestionService`).

#### 1. Query & Generation Pipeline (`src/generation/service.py`)

| Span Name | Type | Input Payload / Initial Metadata | Output / Execution Updates |
| --- | --- | --- | --- |
| **`rag-request`** | Parent Trace | `request_id`, `question` | Total end-to-end request latency and final `ChatResponse` |
| **`retrieval`** | Child Span | `request_id`, `question` | `result_count`, `latency_ms`, and `top_k` chunk hits (`rank`, `score`, `chunk_id`, `document_id`, `version`, `source_name`, `mime_type`, `status`, `section`, `position`, `content_hash`, `doc_id`, `chapter`, `article`, plus raw `text` only in full mode) |
| **`generation`** | Child Span | `request_id`, `question`, `context` (retrieved chunks), `prompt_version`, `system_instruction`, `user_prompt` | `provider`, `model`, `token_usage` (input/output), `response` (structured model dump), `citation_ids` (`[C1]`, `[C2]`), `answer` |

#### 2. Document Ingestion Pipeline (`src/ingestion/service.py`)

| Span Name | Type | Input Payload / Initial Metadata | Output / Execution Updates |
| --- | --- | --- | --- |
| **`ingestion`** | Parent Trace | `source_name` (filename), `file_bytes` | Pipeline status & completion time |
| **`parse`** | Child Span | `source_name`, `file_bytes` | Extracted text size and document parse latency |
| **`chunking`** | Child Span | `document_id`, `version` | Total chunk count, safe chunk metadata, and `doc_id`/chapter/article coordinates; raw chunk `text` appears only in full mode |
| **`enrichment`** | Child Span | `document_id`, `version` | Optional LLM chunk summary, hypothesis questions, and contextual metadata enrichment latency |
| **`indexing`** | Child Span | `document_id`, `version` | Vector embedding generation & Qdrant insertion latency |
| **`registry`** | Child Span | `document_id`, `version` | Document metadata registration status |

## Automated Quality Evaluation Suite

### Staged offline RAG evaluation

The `rag-eval` CLI is the operator interface for the finalized five-file golden
set. Begin with local validation; it reads the canonical source and audit
evidence without building runtime providers or making network calls.

```powershell
rag-eval validate
rag-eval ingest --source data/raw/01_2021_ND-CP_283247.docx
rag-eval retrieval --type multi_hop --limit 10 --name "hyde-test"
rag-eval generation --from-run <retrieval-run-id>
rag-eval e2e --limit 10 --name "baseline"
rag-eval e2e --limit 10 --ragas
rag-eval e2e --ingest data/raw/01_2021_ND-CP_283247.docx --limit 10
rag-eval compare --baseline reports/rag_evaluation/07Aug_17h20_e2e_base/report.json --candidate reports/rag_evaluation/07Aug_17h45_e2e_cand/report.json
```

`data/raw/01_2021_ND-CP_283247.docx` is the raw ingestion identity. Its
parsed counterpart, `data/extracted/01_2021_ND-CP_283247.md`, is the canonical
identity used for deterministic evidence checks. Every answerable golden
context must be an exact canonical substring inside its declared
`doc_id`/chapter/article coordinates. The validator extracts those legal
sections; only a minimal generic Markdown fallback is used when the document
does not expose a legal article structure. It also content-validates
`evaluation/id_migration_map.json` and
`evaluation/golden_set_grounding_review.json` rather than trusting their
presence.

Ingestion is deliberately opt-in. An unchanged raw source is hash-skipped;
`--force-reingest` requires an explicit `--source` or `--ingest` path. A
retrieval or e2e run without ingestion preflights the existing index for ready,
coordinate-compatible chunks. If legacy Qdrant points fail that preflight,
wipe the local or dev collection and re-index the raw DOCX with
`rag-eval ingest --source data/raw/01_2021_ND-CP_283247.docx --force-reingest`.
Without the force flag, an unchanged source still present in the registry is
hash-skipped and cannot repopulate the empty collection.

For retrieval and e2e, the precedence is: an explicit `--golden-file` or
`--type` first defines the population (they are mutually exclusive), then
`--case-id` narrows that population, then `--limit` chooses a deterministic
round-robin sample across the remaining types. Without a file or type, all five
golden files are selected. Generation accepts only `--from-run`: it inherits
the saved retrieval selection and canonical source, and rejects incompatible
dataset or artifact fingerprints.

Each invocation writes a human-readable, chronologically sortable directory below `reports/rag_evaluation/` using the format `reports/rag_evaluation/<DDMon_HHhMM>_<mode>[_<tag-or-model>]` (e.g. `07Aug_17h20_e2e_baseline`).
It contains a write-once `manifest.json` (arguments, `dataset_fingerprint`, and `environment_hash`) and `report.json`; `ingest` mode runs also write `index_snapshot.json` (skipped on standard retrieval/e2e runs to prevent disk bloat), retrieval writes `retrieval.jsonl`, and generation writes `generation.jsonl`. These ignored artifacts preserve provenance without embedding credentials.

Autonomous AI agents leverage `dataset_fingerprint` and `environment_hash` to execute automated **Analyze → Hypothesize → Fix → Benchmark** loops, inspecting `retrieval.jsonl` and `generation.jsonl` for failing case IDs and verifying improvements via `rag-eval compare`.

`--ragas` is opt-in and report-only: it scores captured retrieval/generation
evidence and does not rerun the application pipeline. A requested Ragas failure
makes the run incomplete. A score below `0.85` is reported, not an implicit
release gate. Baseline eligibility is stricter: only a complete, full,
unfiltered 100-case e2e run against the default golden directory and canonical
source, with content-valid audit evidence, can set `baseline_eligible=true`.
Validation, ingestion, retrieval-only, generation-only, and limited e2e runs
are never baseline eligible.

The evaluator computes deterministic metrics before optional Ragas reporting:

| Evaluation Metric | Description | Success Target |
| --- | --- | --- |
| **`coordinate_recall`** | Ratio of required legal source coordinates (`doc_id`, `chapter`, `article`) present in retrieved chunks. | $\ge 0.85$ |
| **`evidence_recall`** | Ratio of golden context substrings present in retrieved text. | $\ge 0.85$ |
| **`citation_validity`** | Ratio of cases where cited chunk IDs are valid subsets of retrieved chunks. | $1.00$ |
| **`citation_coverage`** | Percentage of generated non-abstained sentences containing valid `[C<n>]` citations. | $\ge 0.90$ |
| **`abstention_accuracy`** | Accuracy of correctly abstaining on unanswerable questions (`GoldenType.UNANSWERABLE`). | $1.00$ |
| **`end_to_end_latency_ms_p95`** | P95 end-to-end response time across evaluation test cases. | $\le 3000\text{ ms}$ |

## Operational Health & Readiness Endpoints

- **Liveness Probe (`GET /health`)**:
  Returns process status and active LLM provider model identity (`{"status": "ok", "active_model": "<model_name>"}`).
- **Readiness Probe (`GET /ready`)**:
  Verifies connectivity to Qdrant vector database and probes active provider readiness (`{"status": "ready", "probed_model": "<model_name>"}`). Returns HTTP 503 if dependencies are unreachable.
