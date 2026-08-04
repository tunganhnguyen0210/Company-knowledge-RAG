# Architecture Document: Company Knowledge RAG

## System Overview

Company Knowledge RAG is an enterprise-grade, source-grounded Retrieval-Augmented Generation (RAG) system built with **FastAPI**, **Qdrant**, and **Langfuse**. Operating as a **single-user / open workspace RAG assistant** (similar to a local Codex or Claude Cowork application), it enables users to ingest and query internal documents seamlessly, combining **Dense & Lexical (BM25) Hybrid Search** via Reciprocal Rank Fusion (RRF) and strictly validating LLM responses using **Citation-Gated Abstention**.

> [!NOTE]
> **Fresher AI Engineer Key Takeaway**: In open workspace local RAG systems, user experience and source-grounded accuracy are paramount. By removing multi-tenant authentication barriers, the system provides instant document access while maintaining strict post-generation citation verification to eliminate hallucinations.

## Architecture Diagram

```mermaid
graph TB
    subgraph Client["Client & Entry Points"]
        HTTP["HTTP API Client / Desktop UI"]
        CLI_Ingest["CLI Ingestion Tool"]
        CLI_Eval["CLI Golden-Set Evaluator"]
    end

    subgraph Backend["FastAPI Core & Services"]
        API["API Layer (app.py)"]
        IngestService["Ingestion Service (service.py)"]
        ChatService["Chat & Answer Service (service.py)"]
        Enricher["LLM Enricher (enrichment.py)"]
        LLMRouter["LLM Provider Router (router.py)"]
    end

    subgraph DataLayer["Storage & Vector Indexing"]
        Registry["JSON Document Registry (data/registry.json)"]
        SourceStorage["Source Upload Storage (data/uploads/)"]
        Qdrant["Qdrant Vector DB (Cosine 3072d)"]
        BM25["In-Process BM25 Lexical Index"]
    end

    subgraph Observability["Observability & Evaluation"]
        Langfuse["Langfuse Tracing (tracing.py)"]
        GoldenEval["Golden Set Runner (runner.py)"]
    end

    HTTP -->|Multipart Upload / Chat| API
    CLI_Ingest --> IngestService
    CLI_Eval --> ChatService

    API -->|Upload| IngestService
    API -->|Query| ChatService

    IngestService -->|Save Source| SourceStorage
    IngestService -->|Metadata/Version| Registry
    IngestService -->|Chunk & Enrich| Enricher
    IngestService -->|Embed & Store| Qdrant

    ChatService -->|"Hybrid Search (status=ready)"| Qdrant
    ChatService -->|Lexical Search| BM25
    ChatService -->|Untrusted Context Prompt| LLMRouter
    ChatService -->|Validate Citations / Abstain| ChatService

    ChatService -.->|Trace Spans| Langfuse
    GoldenEval -.->|Quality Metrics| ChatService
```

## Core Components

### 1. API Layer (`src/api/`)
- **Purpose**: Exposes open REST endpoints for document management, chat, health checks, and readiness.
- **Key Modules**: [`app.py`](src/api/app.py), [`settings.py`](src/settings.py)
- **Key Responsibilities**:
  - Handles file uploads (`POST /v1/documents`) and interactive chat requests (`POST /v1/chat`) without header authentication barriers.
  - Implements `/health` (process status) and `/ready` (vector store and LLM provider health check).

### 2. Ingestion & Document Pipeline (`src/ingestion/`)
- **Purpose**: Parses, versions, chunks, enriches, and indexes raw documents into search-ready vectors.
- **Key Modules**: [`service.py`](src/ingestion/service.py), [`parser.py`](src/ingestion/parser.py), [`chunker.py`](src/ingestion/chunker.py), [`enrichment.py`](src/ingestion/enrichment.py)
- **Key Responsibilities**:
  - **Parsing**: Converts UTF-8 Markdown, Plain Text, and PDF files. Sets status to `ready`, `needs_ocr`, or `failed`.
  - **Deterministic Chunking**: Splits text into section-aware chunks (up to ~1,200 chars) with deterministic position IDs.
  - **LLM Contextual Enrichment**: Optionally generates structured chunk summaries, hypothetical questions, and metadata, prepending them to `retrieval_text`.

### 3. Indexing & Storage Layer (`src/storage/` & `src/retrieval/`)
- **Purpose**: Manages multi-tiered persistence for raw sources, metadata, embeddings, and lexical payloads.
- **Key Modules**: [`registry.py`](src/storage/registry.py), [`qdrant_store.py`](src/retrieval/qdrant_store.py)
- **Key Responsibilities**:
  - **Source Store**: Stores raw upload bytes in `data/uploads/` to enable reindexing.
  - **Document Registry**: Tracks document IDs, versions, content hashes, and statuses in `data/registry.json`.
  - **Vector Collection**: Stores 3072-dimensional embeddings in Qdrant using cosine similarity, filtering exclusively on `status == "ready"`.

### 4. Retrieval & Generation Engine (`src/retrieval/` & `src/generation/`)
- **Purpose**: Retrieves ingested document chunks, builds prompts, calls LLM providers, and validates citations.
- **Key Modules**: [`hybrid.py`](src/retrieval/hybrid.py), [`service.py`](src/generation/service.py), [`router.py`](src/providers/router.py), [`answer_v1.py`](src/prompts/answer_v1.py)
- **Key Responsibilities**:
  - **Hybrid Search**: Combines Qdrant Dense Vector search with in-process BM25 Lexical search via Reciprocal Rank Fusion (RRF, `k=60`).
  - **Citation Gate & Abstention**: Validates that LLM output contains valid `[C<n>]` citation markers mapping to retrieved context; converts uncited outputs to standard abstention answers.

### 5. Observability & Quality Evaluation (`src/observability/` & `src/evaluation/`)
- **Purpose**: Provides operational tracing and automated quality evaluation.
- **Key Modules**: [`tracing.py`](src/observability/tracing.py), [`runner.py`](src/evaluation/runner.py)
- **Key Responsibilities**:
  - **Langfuse Tracing**: Captures nested request, retrieval, and generation spans. Supports `off`, `metadata-only` (default for privacy), and `full` trace modes.
  - **Golden-Set Evaluator**: Evaluates performance on golden-set datasets for retrieval accuracy, citation coverage, groundedness, abstention precision, and latency.

## Data Flow

### Ingestion Flow
```mermaid
sequenceDiagram
    autonumber
    actor Admin as User / Client
    participant API as FastAPI App
    participant Ingest as Ingestion Service
    participant Registry as JSON Registry
    participant Store as Qdrant & Disk

    Admin->>API: POST /v1/documents (File)
    API->>Ingest: ingest_bytes(filename, content)
    Ingest->>Ingest: Compute SHA-256 hash & check version
    Ingest->>Ingest: Parse text (Markdown/Text/PDF)
    Ingest->>Ingest: Chunk into section-based segments
    opt ENABLE_ENRICHMENT=true
        Ingest->>Ingest: Generate summary & hypothetical questions
    end
    Ingest->>Store: Save raw source bytes to disk
    Ingest->>Store: Upsert vectors & chunk payloads to Qdrant
    Ingest->>Registry: Upsert document metadata & status (ready)
    Registry-->>Admin: Document Response (id, version, status)
```

### Retrieval & Question Answering Flow
```mermaid
sequenceDiagram
    autonumber
    actor User as Client User
    participant API as FastAPI App
    participant Chat as Chat Service
    participant Qdrant as Qdrant Vector Store
    participant BM25 as Lexical Engine
    participant LLM as LLM Provider Router
    participant Tracing as Langfuse

    User->>API: POST /v1/chat (question)
    API->>Chat: answer(question)
    Chat->>Tracing: Start trace span (rag-request)
    
    par Dual Search
        Chat->>Qdrant: Dense Search (Query Vector, status=ready)
        Chat->>BM25: Lexical Search (BM25 token match)
    end

    Chat->>Chat: Apply Min Score Cutoff & Reciprocal Rank Fusion (RRF)
    
    alt No Ready Chunks Found
        Chat-->>User: Standard Abstention Response
    else Chunks Retrieved
        Chat->>LLM: Send Prompt (Question + Untrusted Context Chunks)
        LLM-->>Chat: Model Raw Answer (with [C<n>] markers)
        Chat->>Chat: Validate [C<n>] citations against context
        alt Valid Citations Present
            Chat-->>User: Answer + Structured Citations + Metadata
        else No Valid Citations
            Chat-->>User: Standard Abstention Response (Ungrounded Guardrail)
        end
    end
    Chat->>Tracing: End trace span
```

## Security & Governance

- **Single-User Workspace Isolation**: Simplifies operation by focusing on open, local workspace environments (ideal for local AI assistants like Codex or Claude Cowork).
- **Trace Privacy Modes**: Defaults to `metadata-only` tracing to prevent sensitive text from leaking into third-party observability backends like Langfuse.
- **Prompt Injection Defense**: Context chunks are wrapped in strict untrusted data blocks within system prompts, telling the LLM to ignore user instructions contained inside ingested documents.

## Key Design Decisions

| Decision | Choice Made | Rationale for Fresher AI Engineers | Alternatives & Why Rejected |
|---|---|---|---|
| **Vector DB** | Qdrant | Fast vector indexing & cosine similarity matching on `status == "ready"`. | ChromaDB, FAISS. |
| **Hybrid Search** | Dense + BM25 via RRF | Dense vectors capture semantic intent; BM25 captures exact IDs/code/jargon. RRF balances them smoothly without score normalization issues. | Dense-only (misses exact keyword matches like product codes), Vector+Sparse. |
| **Abstention Gate** | Hard Citation Regex Verification (`[C<n>]`) | Prevents hallucinations by rejecting answer outputs if the model fails to cite retrieved context. | Trusting LLM output directly (risks hallucinations in enterprise settings). |
| **Document Registry** | Lightweight JSON File (`data/registry.json`) | Simple, zero-dependency storage ideal for single-instance applications and hackathons/prototypes. | PostgreSQL (adds database setup overhead for smaller deployments; migrate when scaling out). |

## Architectural Index & Detailed Guides

| Guide | Deep-Dive Subject | Implementation Link |
|---|---|---|
| 01. System Context | Components, boundaries, entry points, deployment topology | [01-system-context.md](docs/architectures/01-system-context.md) |
| 02. Document Loading & Ingestion | File parsing, versioning, chunking, LLM enrichment pipeline | [02-document-loading-and-ingestion.md](docs/architectures/02-document-loading-and-ingestion.md) |
| 03. Indexing & Storage Layer | Registry, source storage, Qdrant vectors, status-based search | [03-indexing-storage-and-access-control.md](docs/architectures/03-indexing-storage-and-access-control.md) |
| 04. Retrieval, Generation & Citations | Hybrid search, RRF, prompt formatting, citation gating | [04-retrieval-generation-and-citations.md](docs/architectures/04-retrieval-generation-and-citations.md) |
| 05. Observability & Operations | Langfuse tracing, golden-set evaluation, health/readiness endpoints | [05-observability-evaluation-and-operations.md](docs/architectures/05-observability-evaluation-and-operations.md) |

For setup and quickstart instructions, see [README.md](README.md).
