# Automated Quality Evaluation Suite & Observability Architecture Reference

## 1. Overview & Core Purpose

The **Automated Quality Evaluation Suite** (`rag-eval` CLI) and **Observability Engine** provide a staged, deterministic, and telemetry-backed framework for testing, benchmarking, and monitoring the Cowork-RAG system.

Rather than relying on manual inspection or non-deterministic LLM-as-a-judge scores alone, the system utilizes a **5-file canonical golden dataset**, **deterministic evidence verification**, **optional Ragas semantic metrics**, and **structured Langfuse tracing**.

---

## 2. Evaluation Dataset & Canonical Grounding Architecture

### Golden Set Composition
The authoritative evaluation dataset consists of **100 test cases** across five JSON files located at `evaluation/golden_set/`:

| Dataset File | Case Type (`GoldenType`) | ID Prefix | Case Count | Specific Invariants / Requirements |
| --- | --- | --- | --- | --- |
| `golden_set_direct_lookup.json` | `direct_lookup` | `DL-001` .. `DL-020` | 20 | Explicit factual query referencing single legal clause. |
| `golden_set_multi_hop.json` | `multi_hop` | `MH-001` .. `MH-020` | 20 | Complex query requiring $\ge 2$ distinct context sections. |
| `golden_set_unanswerable.json` | `unanswerable` | `UA-001` .. `UA-020` | 20 | Out-of-domain / unanswerable query; contexts must be empty (`[]`). |
| `golden_set_ambiguous.json` | `ambiguous` | `AMB-001` .. `AMB-020` | 20 | Vague / multi-interpretation query testing retrieval breadth. |
| `golden_set_adversarial.json` | `adversarial` | `ADV-001` .. `ADV-020` | 20 | Tricky / prompt injection / deceptive questions. |

### Grounding & Preflight Invariants
- **Canonical Source Document**: `data/extracted/01_2021_ND-CP_283247.md` (parsed markdown identity).
- **Raw Document Identity**: `data/raw/01_2021_ND-CP_283247.docx`.
- **Substring Match Requirement**: Every golden context string must be an *exact canonical substring* inside its declared `(doc_id, chapter, article)` coordinates.
- **Audit Verification Files**:
  - `evaluation/id_migration_map.json`: Tracks historical ID namespace mapping.
  - `evaluation/golden_set_grounding_review.json`: Verifies sha256 checksums of the canonical document, raw text, and dataset cases.

---

## 3. Staged Evaluation Modes & Execution Workflows

The `rag-eval` CLI provides 6 operating commands:

```powershell
# 1. Dataset & Audit Verification (No runtime or network calls)
rag-eval validate

# 2. Document Ingestion (Opt-in re-indexing into Qdrant vector database)
rag-eval ingest --source data/raw/01_2021_ND-CP_283247.docx --force-reingest

# 3. Retrieval Evaluation (Preflights index, executes hybrid search, scores retrieval)
rag-eval retrieval --type multi_hop --limit 10

# 4. Generation Replay (Inherits retrieval run selection and source)
rag-eval generation --from-run <retrieval-run-id>

# 5. End-to-End Evaluation (Full pipeline execution + baseline evaluation)
rag-eval e2e --limit 10 --ragas

# 6. Benchmark Comparison (Compares baseline and candidate report.json files)
rag-eval compare --baseline reports/rag_evaluation/<base_id>/report.json --candidate reports/rag_evaluation/<cand_id>/report.json
```

### Case Selection Precedence
When executing `retrieval` or `e2e`:
1. `--golden-file` OR `--type`: Mutually exclusive; defines the scope.
2. `--case-id`: Narrows down specific case IDs within selected scope.
3. `--limit`: Selects a deterministic round-robin sample across the 5 question types.

---

## 4. Evaluated Metrics & Targets

### Deterministic Metrics

| Metric Name | Scope | Description | Target |
| --- | --- | --- | --- |
| **`coordinate_recall`** | Retrieval | Ratio of required legal source coordinates (`doc_id`, `chapter`, `article`) present in retrieved chunks. | $\ge 0.85$ |
| **`evidence_recall`** | Retrieval | Ratio of golden truth context substrings present in retrieved text. | $\ge 0.85$ |
| **`citation_validity`** | Generation | Ratio of cases where cited chunk IDs (`[C1]`, `[C2]`) are valid subsets of retrieved chunks. | $1.00$ *(Blocking)* |
| **`citation_coverage`** | Generation | Percentage of non-abstained response sentences containing valid `[C<n>]` citations. | $\ge 0.90$ |
| **`abstention_accuracy`** | Generation | Accuracy of correctly outputting the exact abstention phrase on `unanswerable` questions. | $1.00$ |
| **`retrieval_latency_ms`** | Retrieval | Execution time for hybrid vector + lexical retrieval. | - |
| **`generation_latency_ms`** | Generation | Execution time for LLM generation. | - |
| **`end_to_end_latency_ms_p95`** | E2E / Gen | 95th percentile total response time across evaluated cases. | $\le 3000\text{ ms}$ |

### Optional Semantic Metrics (Ragas via `--ragas`)

| Metric Name | Phase | Description |
| --- | --- | --- |
| **`context_precision`** | Retrieval | Measures signal-to-noise ratio of retrieved contexts. |
| **`context_recall`** | Retrieval | Evaluates if all necessary ground truth information was retrieved. |
| **`faithfulness`** | Generation | Measures factual adherence of generated response to retrieved contexts. |
| **`answer_relevancy`** | Generation | Evaluates how directly the generated answer addresses the question. |

---

## 5. Observability & Telemetry Architecture

Integrated via `Tracer` (`src/observability/tracing.py`) using **Langfuse**.

### Trace Hierarchy & Span Schema

```
rag-request (Parent Trace)
├── retrieval (Child Span)
└── generation (Child Span)
```

1. **`rag-request` (Parent Trace)**: Captures total request latency, request ID, question, and final answer.
2. **`retrieval` (Child Span)**: Records hybrid retrieval latency, candidate hit counts, top-k hits metadata (`score`, `chunk_id`, `doc_id`, `chapter`, `article`, `position`, `source_name`).
3. **`generation` (Child Span)**: Logs LLM provider name, model identity, token usage (input/output tokens), raw response, citation mappings, and system/user prompts.

### Telemetry Modes & Redaction Safety
Configured via `TRACE_MODE` in `settings.py`:
- **`off`**: Telemetry disabled.
- **`metadata-only`**: Captures request IDs, timestamps, latencies, token counts, chunk metadata, and legal coordinates, but **redacts raw text** (`answer`, `context`, `parsed_text`, `prompt`, `question`, `response`, `system_instruction`, `text`, `user_prompt`).
- **`full`**: Captures complete prompt text, context chunks, and LLM output. Requires `ALLOW_SENSITIVE_TRACING=true`.

---

## 6. Output Folder Structure

Every evaluation execution generates a unique UUID run directory inside `reports/rag_evaluation/`:

```
reports/
└── rag_evaluation/
    └── <run_uuid>/
        ├── manifest.json              # Write-once execution metadata & lineage
        ├── report.json                # Aggregate metrics, validation, & case scores
        ├── index_snapshot.json        # (ingest/retrieval/e2e) Qdrant collection & chunk snapshot
        ├── retrieval.jsonl            # (retrieval/e2e) Header + per-case retrieval executions
        └── generation.jsonl           # (generation/e2e) Header + per-case generation executions
```

---

## 7. Output File Specifications & Data Structures

### A. `manifest.json` (`RunManifest`)
Write-once record establishing run provenance, environmental context, and artifact lineage.

```json
{
  "run_id": "c7a84e9d01f24a...",
  "created_at": "2026-08-07T10:15:00Z",
  "mode": "e2e",
  "arguments": {
    "golden_dir": "evaluation/golden_set",
    "limit": 10,
    "run_ragas": true
  },
  "git_revision": "a1b2c3d4...",
  "dataset_fingerprint": "8f3d0a...",
  "source_fingerprints": {
    "canonical": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "raw": "f4c8996fb92427ae41e4649b934ca495991b7852b855e3b0c44298fc1c149a"
  },
  "configuration_fingerprints": {
    "runtime": "9b12c8...",
    "selection": "3f4a12..."
  },
  "dependency_versions": {
    "python": "3.11.9",
    "ragas": "0.1.15"
  },
  "artifact_lineage": {
    "index_snapshot": "a8f12c...",
    "retrieval_run": "b9e34d...",
    "generation_run": "c0d56e..."
  }
}
```

### B. `report.json` (`EvaluationReport`)
The main summary output containing validation status, aggregate metrics, target comparisons, per-case breakdown, and baseline eligibility.

```json
{
  "run_id": "c7a84e9d01f24a...",
  "mode": "e2e",
  "status": "complete",
  "dataset_size": 100,
  "evaluated_cases": 100,
  "validation": {
    "errors": [],
    "warnings": [],
    "validated_cases": 100,
    "full_conformance": true
  },
  "aggregates": {
    "retrieval": {
      "overall": {
        "coordinate_recall": 0.92,
        "evidence_recall": 0.88,
        "retrieval_latency_ms": 145.2,
        "retrieval_latency_ms_p95": 280.0
      },
      "by_type": {
        "direct_lookup": { "coordinate_recall": 0.95, "evidence_recall": 0.92 },
        "multi_hop": { "coordinate_recall": 0.85, "evidence_recall": 0.80 }
      },
      "by_difficulty": {
        "easy": { "coordinate_recall": 1.0 },
        "medium": { "coordinate_recall": 0.90 },
        "hard": { "coordinate_recall": 0.82 }
      }
    },
    "generation": {
      "overall": {
        "citation_validity": 1.0,
        "citation_coverage": 0.94,
        "abstention_accuracy": 1.0,
        "generation_latency_ms": 1250.0,
        "end_to_end_latency_ms": 1395.2,
        "end_to_end_latency_ms_p95": 2450.0
      }
    }
  },
  "target_comparison": {
    "retrieval": {
      "coordinate_recall": { "target": 0.85, "meets_target": true },
      "evidence_recall": { "target": 0.85, "meets_target": true }
    },
    "generation": {
      "citation_validity": { "target": 0.85, "meets_target": true },
      "citation_coverage": { "target": 0.85, "meets_target": true },
      "abstention_accuracy": { "target": 0.85, "meets_target": true }
    }
  },
  "case_scores": {
    "DL-001": {
      "coordinate_recall": 1.0,
      "evidence_recall": 1.0,
      "citation_validity": 1.0,
      "citation_coverage": 1.0,
      "retrieval_latency_ms": 120.0,
      "generation_latency_ms": 980.0,
      "end_to_end_latency_ms": 1100.0
    }
  },
  "errors": [],
  "artifact_ids": {
    "index_snapshot": "a8f12c...",
    "retrieval_run": "b9e34d...",
    "generation_run": "c0d56e..."
  },
  "baseline_eligible": true,
  "report_path": "reports/rag_evaluation/c7a84e9d01f24a.../report.json"
}
```

### C. `index_snapshot.json` (`IndexSnapshot`)
Captures vector index state and chunk payloads at evaluation time.

```json
{
  "run_id": "c7a84e9d01f24a...",
  "document_id": "doc_2021_nd_cp_283247",
  "document_version": 1,
  "source_name": "01_2021_ND-CP_283247.docx",
  "canonical_doc_id": "01_2021_ND-CP_283247.md",
  "raw_source_hash": "f4c8996fb92427ae...",
  "canonical_source_hash": "e3b0c44298fc1c14...",
  "chunk_count": 142,
  "collection_name": "cowork_rag_chunks",
  "configuration": {
    "embedding_model": "text-embedding-3-small",
    "qdrant_collection": "cowork_rag_chunks"
  },
  "metadata_validation": { "full_conformance": true },
  "chunks": [ /* List of full Chunk objects */ ],
  "snapshot_fingerprint": "a8f12c..."
}
```

### D. `retrieval.jsonl` (`RetrievalRun`)
Streaming JSON Lines file containing header metadata followed by per-case retrieval execution results.

- **Line 1 (Header)**:
  `{"record_type": "header", "value": {"run_id": "...", "dataset_fingerprint": "...", "golden_dir": "evaluation/golden_set", "dataset_source_files": [...], "dataset_scope": "full", "canonical_source": "data/extracted/01_2021_ND-CP_283247.md", "index_snapshot_fingerprint": "...", "configuration": {...}, "run_fingerprint": "..."}}`

- **Lines 2..N (Cases)**:
  `{"record_type": "case", "value": {"case_id": "DL-001", "type": "direct_lookup", "difficulty": "easy", "expected_answer": "...", "golden_contexts": ["..."], "retrieval": {"request_id": "...", "question": "...", "latency_ms": 120.0, "hits": [...]}, "deterministic_scores": {"coordinate_recall": 1.0, "evidence_recall": 1.0}, "error": null}}`

### E. `generation.jsonl` (`GenerationRun`)
Streaming JSON Lines file containing header metadata followed by per-case LLM generation outputs.

- **Line 1 (Header)**:
  `{"record_type": "header", "value": {"run_id": "...", "retrieval_run_fingerprint": "...", "configuration": {...}, "run_fingerprint": "..."}}`

- **Lines 2..N (Cases)**:
  `{"record_type": "case", "value": {"case_id": "DL-001", "generation": {"request_id": "...", "answer": "...", "citations": [{"citation_id": "[C1]", "chunk_id": "..."}], "usage": {"input_tokens": 450, "output_tokens": 120}, "latency_ms": 980.0}, "deterministic_scores": {"citation_validity": 1.0, "citation_coverage": 1.0, "abstention_accuracy": null, "retrieval_latency_ms": 120.0, "generation_latency_ms": 980.0, "end_to_end_latency_ms": 1100.0}, "error": null}}`

---

## 8. Baseline Eligibility Rules

To prevent skewed or partial benchmark submissions from overwriting baseline benchmarks, a run is marked `baseline_eligible: true` **ONLY IF ALL** of the following conditions are met:
1. `mode == "e2e"`.
2. `status == "complete"` (no errors or unhandled exceptions).
3. `validation.full_conformance == true` (zero errors and zero warnings on golden set grounding).
4. `golden_dir == "evaluation/golden_set"` (default production golden directory).
5. `canonical_source == "data/extracted/01_2021_ND-CP_283247.md"`.
6. Dataset size = 100 cases, evaluated cases = 100 (unfiltered, no `--type`, `--golden-file`, `--case-id`, or `--limit` flags).
