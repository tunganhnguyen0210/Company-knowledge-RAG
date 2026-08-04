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
- **`metadata-only`** *(Default)*: Sends request IDs, timestamps, latency, token usage, and hit counts to Langfuse, but redacts raw query text and document content to protect data privacy.
- **`full`**: Captures complete prompt text, context chunks, and raw LLM answers. Requires explicit `ALLOW_SENSITIVE_TRACING=true`.

### Active Traced Pipelines & Payload Schema

The system actively traces two primary workflows: the **Query & Generation Pipeline** (`ChatService`) and the **Document Ingestion Pipeline** (`IngestionService`).

#### 1. Query & Generation Pipeline (`src/generation/service.py`)

| Span Name | Type | Input Payload / Initial Metadata | Output / Execution Updates |
| --- | --- | --- | --- |
| **`rag-request`** | Parent Trace | `request_id`, `question` | Total end-to-end request latency and final `ChatResponse` |
| **`retrieval`** | Child Span | `request_id`, `question` | `result_count`, `latency_ms`, and `top_k` chunk hits (`rank`, `score`, `chunk_id`, `document_id`, `version`, `source_name`, `section`, `position`, `content_hash`, `text`) |
| **`generation`** | Child Span | `request_id`, `question`, `context` (retrieved chunks), `prompt_version`, `system_instruction`, `user_prompt` | `provider`, `model`, `token_usage` (input/output), `response` (structured model dump), `citation_ids` (`[C1]`, `[C2]`), `answer` |

#### 2. Document Ingestion Pipeline (`src/ingestion/service.py`)

| Span Name | Type | Input Payload / Initial Metadata | Output / Execution Updates |
| --- | --- | --- | --- |
| **`ingestion`** | Parent Trace | `source_name` (filename), `file_bytes` | Pipeline status & completion time |
| **`parse`** | Child Span | `source_name`, `file_bytes` | Extracted text size and document parse latency |
| **`chunking`** | Child Span | `source_name`, `file_bytes` | Total chunk count created & chunking stats |
| **`registry`** | Child Span | `document_id`, `version` | Document metadata registration status |
| **`indexing`** | Child Span | `document_id`, `version` | Vector embedding generation & Qdrant insertion latency |

## Automated Quality Evaluation Suite

### CLI Evaluator (`src/evaluation/runner.py`)
Run via CLI command:
```bash
company-rag-evaluate
```

The evaluator executes golden test cases (defined in JSON test suites) and computes five core metrics:

| Evaluation Metric | Description | Success Target |
| --- | --- | --- |
| **Retrieval Hit Rate** | Ratio of test cases where expected source documents are present in retrieved context. | $\ge 0.85$ |
| **Groundedness** | Ratio of non-abstained answers supported by citation sources. | $1.00$ |
| **Citation Coverage** | Percentage of generated sentences containing valid `[C<n>]` citations. | $\ge 0.90$ |
| **Abstention Precision** | Accuracy of abstaining on unanswerable questions. | $1.00$ |
| **Average Latency** | Mean end-to-end response time across all golden set questions. | $< 3000\text{ ms}$ |

## Operational Health & Readiness Endpoints

- **Liveness Probe (`GET /health`)**:
  Returns process status and active LLM provider model string (`status: "ok"`).
- **Readiness Probe (`GET /ready`)**:
  Verifies connectivity to Qdrant vector database and LLM provider ready status (`status: "ready"`). Returns HTTP 503 if dependencies are unreachable.
