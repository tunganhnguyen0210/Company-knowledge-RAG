# Design Spec: Architecture Documentation Standards & Index (`docs/architectures/README.md`)

**Date**: 2026-08-04  
**Topic**: Document Formatting Standards and Directory Index for `docs/architectures/`  
**Target File**: [`docs/architectures/README.md`](../../docs/architectures/README.md)

---

## 1. Goal & Context

To maintain consistent formatting, clear modular documentation layout, and renderer-safe Mermaid diagrams across the codebase, this spec defines the design for `docs/architectures/README.md`.

This file acts as the directory index and formatting contract for human developers and AI coding agents (such as Codex, Claude, and Gemini agents) when creating or updating deep-dive architecture docs in `docs/architectures/`.

---

## 2. Distinction from Root `ARCHITECTURE.md`

- **Root [`ARCHITECTURE.md`](../../ARCHITECTURE.md)**: High-level system architecture overview, global component matrix, environment configuration, and end-to-end runtime topology.
- **Directory [`docs/architectures/README.md`](../../docs/architectures/README.md)**: Folder index mapping deep-dive modular specs (`01` through `06`), agent formatting standards, Mermaid syntax guardrails, and starter template.

---

## 3. Specifications for `docs/architectures/README.md`

### 3.1 Header & System Cross-Reference
The document begins with a clear system reference link pointing back to root `ARCHITECTURE.md` so agents understand the hierarchy.

### 3.2 Modular Architecture Document Index Table
A markdown table listing all current files in `docs/architectures/`:

| File | Subsystem Topic | Key Focus & Capabilities | Primary Implementation Files |
| :--- | :--- | :--- | :--- |
| [`01-system-context.md`](01-system-context.md) | System Context & Topology | Architecture context, API entry points, component matrix | [`src/api/app.py`](../../src/api/app.py), [`src/ingestion/service.py`](../../src/ingestion/service.py) |
| [`02-document-loading-and-ingestion.md`](02-document-loading-and-ingestion.md) | Ingestion & Document Pipeline | Document parsing, hashing, text cleaning, chunking | [`src/ingestion/service.py`](../../src/ingestion/service.py), [`src/storage/registry.py`](../../src/storage/registry.py) |
| [`03-indexing-storage-and-access-control.md`](03-indexing-storage-and-access-control.md) | Indexing & Storage Layer | Qdrant vector store, status flags (`ready`), persistence | [`src/retrieval/qdrant_store.py`](../../src/retrieval/qdrant_store.py) |
| [`04-retrieval-generation-and-citations.md`](04-retrieval-generation-and-citations.md) | Retrieval & Generation Engine | Hybrid search (RRF), context prompts, citation gating | [`src/retrieval/hybrid.py`](../../src/retrieval/hybrid.py), [`src/generation/service.py`](../../src/generation/service.py) |
| [`05-observability-evaluation-and-operations.md`](05-observability-evaluation-and-operations.md) | Operations & Observability | Langfuse telemetry tracing, golden set benchmark runner | [`src/observability/tracing.py`](../../src/observability/tracing.py), [`src/evaluation/runner.py`](../../src/evaluation/runner.py) |
| [`06-simple-rag-vs-company-rag-comparison.md`](06-simple-rag-vs-company-rag-comparison.md) | RAG Pipeline Comparison | Baseline vs. Production RAG side-by-side comparison | All core pipeline files |

### 3.3 Agent Formatting & Structural Rules

Every document in `docs/architectures/` MUST follow this exact structure:

1. **Document Title (`# <Title>`)**: H1 title at top of document.
2. **Fresher AI Engineer Key Concepts (`## Fresher AI Engineer Key Concepts`)**:
   - Must include a GitHub alert block (`> [!NOTE]`) explaining domain terms simply.
3. **Overview / Purpose (`## Overview` or `## Purpose`)**:
   - Concise summary of the subsystem's goals and operational constraints.
4. **Component Matrix / Workflow (`## Component Matrix` or `## Detailed Workflow Steps`)**:
   - Markdown table linking implementation files (`../../src/...`) and key interfaces/methods.
5. **Architecture Diagram (`## Pipeline Architecture` or `## Diagram`)**:
   - Mermaid diagram depicting flow or topology.

### 3.4 Mermaid Syntax Guardrails

To prevent diagram parse errors across IDE previewers:
- **Always double-quote node text**: `Node["Text"]` or `Decision{"Text"}`.
- **No unescaped brackets in decision nodes**: Replace `[C1]` with `(C1)` or quote the string.
- **No unescaped HTML tags**: Replace `<context>` with `Context` or use HTML entities (`&lt;context&gt;`).
- **No ampersands as word joiners**: Use `and` instead of `&` to avoid confusion with Mermaid junction operators.
- **Use Subgraph Phase Boxes**: Group multi-phase workflows into `subgraph Phase1["Phase 1: Title"]`.

### 3.5 Relative Code Linking Standard

- File links MUST use relative Markdown links from `docs/architectures/` to `../../src/...`:
  - `[`src/generation/service.py`](../../src/generation/service.py)`
- Symbols MUST use backticks: `IngestionService.ingest_bytes()`, `status == "ready"`.

### 3.6 Copy-Paste Starter Template
A complete code block template for any new `NN-<topic>.md` document.

---

## 4. Verification & Testing

- Validate that `docs/architectures/README.md` renders cleanly without broken Markdown links or invalid Mermaid blocks.
- Ensure all relative file paths from `docs/architectures/` to `../../src/` and to `../../ARCHITECTURE.md` are valid.
