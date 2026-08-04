# Design Spec: RAG Architecture Overhaul & Documentation Standards

**Date**: 2026-08-04  
**Topic**: Rename `ARCHITECTURE.md` → `RAG-ARCHITECTURE.md` with Key Decisions by RAG Phase, and establish `docs/architectures/README.md` Index & Agent Standard  
**Target Files**:
- [`RAG-ARCHITECTURE.md`](../../RAG-ARCHITECTURE.md) (Renamed from `ARCHITECTURE.md`)
- [`docs/architectures/README.md`](../../docs/architectures/README.md)

---

## 1. Goal & Context

To enable developers and AI coding agents to make **Key Architectural Decisions** at a glance, the root system architecture document is renamed to `RAG-ARCHITECTURE.md` and restructured around the core **RAG Pipeline Phases** (referencing RAG pipeline deep-dive principles: Ingestion/Indexing, Retrieval, Generation/Routing, Safety/Citations, and Operations).

Concurrently, `docs/architectures/README.md` serves as the directory index and formatting contract for detailed modular docs in `docs/architectures/`.

---

## 2. File Roles & Relationships

1. **`RAG-ARCHITECTURE.md` (Root)**:
   - High-level system architecture overview.
   - **RAG Phase Key Decisions Matrix**: Summarizes decisions, rationale, and implementation modules for each RAG Phase (Ingestion, Retrieval, Generation, Safety, Operations).
   - Component Topology & Subsystem Map.

2. **`docs/architectures/README.md` (Subfolder Index & Agent Standard)**:
   - Index mapping deep-dive modular specs (`01` through `06`).
   - Formatting rules & Mermaid syntax standards for AI coding agents.
   - Copy-paste Markdown starter skeleton (`07-*.md`).

---

## 3. Specifications for `RAG-ARCHITECTURE.md`

### 3.1 Restructured RAG Phase Key Decisions Matrix

The root document will include an explicit **Key Decisions by RAG Phase** section:

#### Phase 1: Ingestion & Indexing (Offline)
- **1.1 Document Loading & Cleaning**:
  - *Key Decision*: Standardize multi-format parsing (PDF, Markdown, Text) with Unicode NFC normalization and status tracking (`ready`, `needs_ocr`, `failed`).
  - *Rationale*: Eliminates text noise to prevent downstream retrieval degradation.
- **1.2 Chunking Strategy**:
  - *Key Decision*: Section-aware recursive character chunking (~1,200 chars with 10–20% overlap).
  - *Rationale*: Preserves natural paragraph boundaries while preventing context truncation at chunk seams.
- **1.3 Contextual Enrichment (Optional)**:
  - *Key Decision*: Prepend LLM-generated summaries and hypothetical questions to retrieval text.
  - *Rationale*: Enhances recall for high-level thematic queries that lack direct keyword matches.
- **1.4 Vector & Storage Engine**:
  - *Key Decision*: Decoupled Qdrant Vector DB (Cosine 1024d, Gemini embeddings), JSON Registry (`data/registry.json`), and Raw Source Retention (`data/uploads/`).
  - *Rationale*: Enables instant reindexing without re-uploading bytes and restricts vector queries to ready files.

#### Phase 2: Query & Retrieval (Runtime)
- **2.1 Hybrid Retrieval Strategy**:
  - *Key Decision*: Parallel Qdrant Dense Search + In-process BM25 Lexical Search fused via **Reciprocal Rank Fusion (RRF k=60)**.
  - *Rationale*: Overcomes the "hard ceiling" of vector-only search by capturing exact keywords, names, and IDs via BM25 alongside semantic vectors.
- **2.2 Score Thresholding**:
  - *Key Decision*: `min_dense_score` gating before prompt rendering.
  - *Rationale*: Filters out low-relevance noise to save tokens and improve answer quality.

#### Phase 3: Generation & LLM Routing (Runtime)
- **3.1 Prompt Context Isolation**:
  - *Key Decision*: Untrusted context blocks (`<context>` tags) in system prompt (`answer_v1.py`).
  - *Rationale*: Protects against prompt injection from ingested document text.
- **3.2 Provider Failover Router**:
  - *Key Decision*: Multi-provider LLM Router (Gemini, OpenRouter, OpenAI) with automatic retry fallback.
  - *Rationale*: Prevents service downtime caused by third-party provider outages or rate limits.

#### Phase 4: Safety & Citation Guardrails (Runtime)
- **4.1 Citation Verification & Abstention Guard**:
  - *Key Decision*: Deterministic regex validation of `[C1]`, `[C2]` citation markers; forces automatic abstention (*"Không tìm thấy thông tin phù hợp..."*) if citations are missing or invalid.
  - *Rationale*: Guarantees zero ungrounded hallucinations.

#### Phase 5: Operations & Quality Evaluation
- **5.1 Observability**: Langfuse span tracing with configurable privacy modes (`off`, `metadata-only`, `full`).
- **5.2 Golden Set Evaluation**: Automated CLI runner (`company-rag-evaluate`) against `evaluation/golden_set.json` to catch silent retrieval regressions.

---

## 4. Specifications for `docs/architectures/README.md`

1. **System Reference Link**: Points back to `RAG-ARCHITECTURE.md`.
2. **Modular Index Table**: Maps `01` through `06` files to subsystem topics and primary code files.
3. **Agent Formatting Rules**: Mandates `# Title` → `## Fresher AI Engineer Key Concepts` (`> [!NOTE]`) → `## Overview` → `## Component Matrix` → `## Diagram`.
4. **Mermaid Syntax Guardrails**: Double-quoted node labels, no unescaped brackets `[C1]` in decision nodes, no ampersands `&`, nested phase subgraphs.
5. **Relative Link Standard**: Links relative to `../../src/...`.
6. **Starter Template**: Ready-to-copy skeleton block.

---

## 5. Verification & Plan

1. Rename `ARCHITECTURE.md` → `RAG-ARCHITECTURE.md` and insert the **RAG Phase Key Decisions Matrix**.
2. Update internal relative links pointing to `ARCHITECTURE.md` across repository docs to `RAG-ARCHITECTURE.md`.
3. Create `docs/architectures/README.md` with the index, rules, and template.
4. Verify markdown rendering and git commit changes.
