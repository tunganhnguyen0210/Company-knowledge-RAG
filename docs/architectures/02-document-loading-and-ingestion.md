# Document Loading and Ingestion Pipeline

## Fresher AI Engineer Key Concepts

> [!NOTE]
> **Why is Ingestion the Foundation of RAG?**  
> An LLM is only as good as the context provided to it. The ingestion pipeline transforms raw unstructured documents (PDF, Markdown, Text) into clean, versioned, section-aware chunks stored in a vector database.

## Overview

The ingestion pipeline handles raw file upload, content hashing, document parsing, deterministic chunking, optional LLM contextual enrichment, vector embedding, and persistence to both Qdrant and the local document registry.

## Pipeline Architecture

```mermaid
flowchart LR
    File[Raw Upload Bytes] --> Hash[Compute SHA-256 Digest]
    Hash --> RegistryCheck{Check Registry}
    RegistryCheck -->|New File| Parse[Parse Text & Format]
    RegistryCheck -->|Same Hash & No Force| Skip[Return Existing Document]
    RegistryCheck -->|Updated Hash / Force| Parse

    Parse --> StatusCheck{Text Extracted?}
    StatusCheck -->|Yes| Chunk[Section-Aware Chunker]
    StatusCheck -->|PDF No Text| OCR[Status: needs_ocr]
    StatusCheck -->|Failed| Fail[Status: failed]

    Chunk --> Enrich{Enable Enrichment?}
    Enrich -->|Yes| LLMEnrich[Generate Summary & Qs]
    Enrich -->|No| Store
    LLMEnrich --> Store[Embed Vectors & Save to Qdrant]

    Store --> WriteDisk[Write Source Bytes to Disk]
    WriteDisk --> SaveReg[Upsert Document Registry]
```

## Key Ingestion Steps

### 1. Versioning & SHA-256 De-duplication (`src/ingestion/service.py`)
- Every uploaded document undergoes SHA-256 hashing.
- If a document with the same source filename and hash exists, ingestion returns the existing document without reprocessing unless `force=True`.
- If the content hash changes, the document version increments (e.g. `v1` -> `v2`), and prior chunk versions are safely pruned from Qdrant.

### Evaluation ingestion and coordinate recovery

The staged evaluator keeps the raw DOCX and the canonical Markdown source as
separate identities. `data/raw/01_2021_ND-CP_283247.docx` is the opt-in
ingestion input; `data/extracted/01_2021_ND-CP_283247.md` is the stable source
used to validate golden excerpts and their legal `doc_id`, chapter, and article
coordinates. Running `rag-eval ingest --source data/raw/01_2021_ND-CP_283247.docx`
is idempotent for unchanged bytes; `--force-reingest` is permitted only when a
source is supplied.

Legacy Qdrant points that lack compatible canonical coordinates cannot be used
for staged retrieval. Re-index them from the retained raw DOCX with that command,
then use the staged evaluator's preflight instead of treating old payloads as
equivalent. See the [evaluation operations contract](05-observability-evaluation-and-operations.md#staged-offline-rag-evaluation)
for the exact recovery and verification sequence.

### 2. Document Parsing (`src/ingestion/parser.py`)
- Supports `.md`, `.txt`, `.pdf`, and `.docx` formats.
- Extracted text is normalized to UTF-8. PDF files without extractable text are tagged with `status = DocumentStatus.NEEDS_OCR`.
- DOCX parsing walks the document body in order: Word heading styles become markdown headings so the chunker sees sections, and table rows are flattened to pipe-separated lines instead of being dropped.

### 3. Section-Aware Chunking (`src/ingestion/chunker.py`)
- Documents are split into logical chunks based on headings and paragraph boundaries (target size ~1,200 characters).
- Each chunk preserves section metadata and position indices to maintain logical context during retrieval.

### 4. Optional Contextual LLM Enrichment (`src/ingestion/enrichment.py`)
- When `ENABLE_ENRICHMENT=true` in `settings.py`, an LLM pass returns a validated `ChunkEnrichment` object (instructor-backed, so no hand-rolled JSON parsing) containing:
  1. A concise chunk summary.
  2. Hypothetical user questions answered by the chunk (capped at 5).
  3. A contextual prefix and key/value metadata labels.
- These synthetic additions are prepended to `retrieval_text`, dramatically improving dense vector retrieval hit rates for abstract questions.

### 5. Vector Store Upsert (`src/retrieval/qdrant_store.py`)
- Chunks are embedded using Gemini (`gemini-embedding-001`, task `RETRIEVAL_DOCUMENT`) into 1024-dimensional vectors.
- Payload objects containing chunk text, source name, status (`ready`), document ID, and version are written to Qdrant.
