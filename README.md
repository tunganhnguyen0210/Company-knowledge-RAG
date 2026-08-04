# Company Knowledge RAG

A production-oriented Retrieval-Augmented Generation (RAG) service for internal company documents built with **FastAPI**, **Qdrant**, **Gemini / OpenRouter / OpenAI**, **Instructor**, and **Langfuse**.

Operating as a **single-user / open workspace RAG assistant**, it enables instant document ingestion and source-grounded question answering with **Hybrid Search (Dense Vector + BM25 Lexical)**, **Gemini Key Rotation**, **Multi-Provider Failover**, and **Citation-Gated Abstention**.

---

## 📌 Key Features

- **Multi-Format Document Ingestion**: Parses `.md`, `.txt`, `.pdf`, and `.docx` with section-aware chunking and optional LLM contextual enrichment.
- **Hybrid Retrieval Engine**: Combines Qdrant dense vector search (Gemini Matryoshka embeddings) with in-process BM25 lexical search using Reciprocal Rank Fusion (RRF).
- **Grounded Answers & Citation Gating**: Employs `instructor` Pydantic schemas (`GroundedAnswer`) coupled with post-generation citation validation to force strict abstention on ungrounded claims.
- **Resilient Multi-Provider LLM Engine**: Automatic failover router (`Gemini` → `OpenRouter` → `OpenAI`) with a round-robin key rotation pool (`GEMINI_API_KEY`, `GEMINI_API_FALLBACK_KEY...`) for quota handling.
- **Privacy-First Telemetry**: Integrated Langfuse observability with `metadata-only` trace mode, stripping raw document and query content from telemetry payloads by default.
- **Built-in Quality Benchmarking**: CLI suite for golden-set evaluations measuring hit rate, groundedness proxy, citation coverage, and latency.

---

## 🏗️ Architecture Overview

### Data Flow Pipeline

```text
Upload / CLI → Parse (md/txt/pdf/docx) → Section Chunks → Gemini Embeddings → Qdrant Vector DB
                                                                                  ↓ status=ready
Client → FastAPI → Dense + BM25 Search → RRF Fusion → Grounded Answer → Provider Router (Gemini/OpenRouter/OpenAI)
                               └───────── Langfuse Tracing ──────────┘
```

### Module Layout

| Subsystem | Location | Primary Responsibilities |
| :--- | :--- | :--- |
| **API** | [`src/api/`](src/api/) | FastAPI web entrypoints (`/v1/chat`, `/v1/documents`, `/health`, `/ready`) |
| **Ingestion** | [`src/ingestion/`](src/ingestion/) | Document parsing, NFC cleaning, section-aware chunking, and LLM enrichment |
| **Retrieval** | [`src/retrieval/`](src/retrieval/) | Qdrant vector store integration, BM25 lexical indexer, and RRF rank fusion |
| **Providers** | [`src/providers/`](src/providers/) | Gemini key rotation pool, OpenRouter/OpenAI provider failover router |
| **Generation** | [`src/generation/`](src/generation/) | Instructor structured output generation & post-citation validation |
| **Observability** | [`src/observability/`](src/observability/) | Langfuse span tracing & privacy-preserving metadata redaction |
| **Evaluation** | [`src/evaluation/`](src/evaluation/) | Golden-set benchmark runner & RAG quality metrics |
| **Storage** | [`src/storage/`](src/storage/) | File upload store (`data/uploads/`) & JSON metadata registry (`data/registry.json`) |

> 📖 **Deep Dive Documentation**: For in-depth architectural specifications and design rationale, refer to [`RAG-ARCHITECTURE.md`](RAG-ARCHITECTURE.md) and [`docs/architectures/`](docs/architectures/).

---

## 🚀 Quickstart Guide

### Prerequisites

- **Python**: `>= 3.11`
- **Package Manager**: [`uv`](https://docs.astral.sh/uv/)
- **Qdrant**: Access to a Qdrant vector database instance (cloud or self-hosted endpoint)

### Setup Steps

1. **Clone & Setup Environment**
   ```bash
   cp .env.example .env
   ```
   Open `.env` and configure your API keys and service endpoints:
   - **`GEMINI_API_KEY`**: *(Required)* API key for Gemini embeddings and generation.
   - **`QDRANT_URL` & `QDRANT_API_KEY`**: *(Required)* Endpoint URL (e.g. `http://localhost:6333` or Qdrant Cloud URL) and API key for your Qdrant vector store.
   - **`MAIN_PROVIDER`**: Set primary LLM provider (`gemini`, `openrouter`, or `openai`).
   - **`OPENROUTER_API_KEY` / `OPENAI_API_KEY`**: API key(s) if using OpenRouter or OpenAI as main provider or failover.
   - **`JINA_API_KEY`**: API key if using Jina embeddings/reranker.

2. **Install Dependencies**
   ```bash
   uv sync --locked --group dev
   ```

3. **Start API Server**
   ```bash
   uv run company-rag-serve --reload
   ```

4. **Explore Interactive Docs**
   Open Swagger UI at [`http://localhost:8000/docs`](http://localhost:8000/docs).

---

## 💻 Usage & CLI Reference

### CLI Commands

- **Start API Server**:
  ```bash
  uv run company-rag-serve --host 0.0.0.0 --port 8000
  ```
- **Ingest Document Directory**:
  ```bash
  uv run company-rag-ingest ./data/seed
  ```
- **Run Golden-Set Evaluation**:
  ```bash
  uv run company-rag-evaluate --dataset evaluation/golden_set.json
  ```

### API Examples

#### 1. Ingest a Document (`POST /v1/documents`)
```bash
curl -X POST http://localhost:8000/v1/documents \
  -F "file=@policy.md;type=text/markdown" \
  -F 'metadata={"department":"hr"}'
```

#### 2. Query Chat RAG (`POST /v1/chat`)
```bash
curl -X POST http://localhost:8000/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"question":"Nhân viên được nghỉ phép bao nhiêu ngày?"}'
```

#### 3. Health & Readiness Probes
```bash
# Process check
curl http://localhost:8000/health

# End-to-end LLM provider & Qdrant connectivity check
curl http://localhost:8000/ready
```

---

## ⚙️ Configuration Reference

| Environment Variable | Default | Description |
| :--- | :--- | :--- |
| `MAIN_PROVIDER` | `gemini` | Primary generation LLM provider (`gemini`, `openrouter`, `openai`) |
| `GEMINI_API_KEY` | *Required* | API key for Gemini embeddings & LLM generation |
| `GEMINI_API_FALLBACK_KEY` | `None` | Secondary API key for Gemini key rotation pool (429 handling) |
| `QDRANT_URL` | `http://localhost:6333` | Qdrant vector database endpoint URL |
| `QDRANT_API_KEY` | `None` | API key for authenticating with Qdrant vector store |
| `OPENROUTER_API_KEY` | `None` | API key required when `MAIN_PROVIDER=openrouter` or for fallback |
| `OPENAI_API_KEY` | `None` | API key required when `MAIN_PROVIDER=openai` or for fallback |
| `JINA_API_KEY` | `None` | API key required when using Jina embedding/reranker models |
| `EMBEDDING_MODEL` | `jina-embeddings-v5-omni-small` | Model used for document vector embeddings |
| `EMBEDDING_DIMENSIONS` | `1024` | Vector dimension (must match Qdrant collection schema) |
| `TRACE_MODE` | `metadata-only` | Telemetry mode (`metadata-only`, `full`, `disabled`) |
| `ENABLE_ENRICHMENT` | `false` | Enable LLM chunk summary & hypothetical query generation |

---

## 🔭 Langfuse Observability

Set these values in `.env`; never commit real keys.

```dotenv
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_BASE_URL=https://cloud.langfuse.com
ENVIRONMENT=development
TRACE_MODE=metadata-only
```

`LANGFUSE_HOST` is also accepted. `TRACE_MODE=metadata-only` is recommended for shared projects because it removes raw document and query text from trace payloads; use `full` only with explicit approval.

Run one supported file to create an ingestion observation. The CLI flushes Langfuse before it exits.

```powershell
uv run company-rag-ingest .\data\seed\01_2021_ND-CP_283247.docx
```

To inspect it later, open the Langfuse project, then open **Observations**. Filter by environment (`development`), name (`ingestion`), and the run time; open the root observation, then its linked trace for the waterfall. Child observations for a non-idempotent ingest are `parse`, `chunking`, `indexing`, and `registry`.

If a `development` filter is empty, retry with `default` and record the mismatch before treating environment-based filtering as reliable. This repository currently has a live observation verified under `default`; the application setting still resolves to `development`, so this needs follow-up rather than silent assumptions.

For a read-only CLI check, first export `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, and `LANGFUSE_BASE_URL` into the current shell (the CLI does not read `.env` automatically). Then omit IO/metadata fields:

```powershell
npx langfuse-cli api observations list --environment development --name ingestion --limit 10 --fields basic,time,metrics,trace_context --json
```

---

## 🧪 Testing & Code Quality

Run tests and static analysis before submitting changes:

```bash
# Run pytest test suite
uv run pytest

# Run Ruff linter
uv run ruff check .

# Run MyPy static type checking
uv run mypy
```

---

## ❓ Troubleshooting & FAQ

- **`/ready` returns `503 Service Unavailable`**: Check response `detail` payload for provider error messages. Verify `GEMINI_API_KEY`, primary provider key, Qdrant service state, and matching vector dimensions.
- **Qdrant Vector Dimension Mismatch**: If Qdrant errors with `vector size is N; expected M`, the Qdrant collection was created with a different `EMBEDDING_DIMENSIONS`. Delete the collection and re-index.
- **Chat Always Returns Abstention**: Occurs when no hits exceed `MIN_DENSE_SCORE` or model citations fail post-generation validation. Check the `retrieval` span in Langfuse traces.
- **Document Upload Returns `needs_ocr`**: The uploaded PDF contains scanned images without selectable text. Perform OCR preprocessing prior to re-indexing.
- **Ingestion Slowdown / Rate Limits**: Gemini API hit a rate limit. Add additional fallback keys (`GEMINI_API_FALLBACK_KEY2...`) to the rotation pool to increase throughput.

