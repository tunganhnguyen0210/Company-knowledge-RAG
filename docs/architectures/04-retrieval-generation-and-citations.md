# Retrieval, Generation & Citations Pipeline

## Fresher AI Engineer Key Concepts

> [!NOTE]
> **What is Hybrid Search & Citation Gating?**  
> - **Hybrid Search** combines two complementary search strategies: **Dense Search** (understanding overall semantic context and meaning) and **Lexical Search** (matching exact names, technical terms, and IDs using BM25).
> - **Reciprocal Rank Fusion (RRF)** combines ranked results from both strategies into a unified, high-precision hit list.
> - **Citation Gating** reads the citation indexes the LLM returns in a validated `GroundedAnswer` object (via [instructor](https://github.com/567-labs/instructor)) and maps them back to retrieved text. If the model provides an answer without valid citations, the system forces an abstention response to prevent ungrounded hallucinations.

> [!TIP]
> **Deep dive with concrete input/output at every stage:**
> [`docs/references/CHUNKING-AND-RETRIEVAL-FLOW.md`](../references/CHUNKING-AND-RETRIEVAL-FLOW.md) (Vietnamese).

## Pipeline Architecture

```mermaid
flowchart TD
    Query[User Question Payload] --> Dense[Qdrant Dense Vector Search]
    Query --> Lexical[In-Process BM25 Lexical Search]

    Dense --> RRF[Reciprocal Rank Fusion RRF k=60]
    Lexical --> RRF

    RRF --> MinScore{"Filter Score >= min_dense_score"}
    MinScore -->|Hits Found| Expand["Hierarchical Sibling Expansion (whole legal section)"]
    MinScore -->|No Hits| Abstain["Return Abstention Response"]
    Expand --> Prompt["Render System Prompt with Context Chunks"]

    Prompt --> LLM[Call Provider Router Gemini / OpenRouter / OpenAI]
    LLM --> Structured[Instructor Validates GroundedAnswer Schema + Reask on Failure]
    Structured --> CitationCheck{Citation Indexes Within Context Range}

    CitationCheck -->|Valid Citations| Output[Return ChatResponse + Citations]
    CitationCheck -->|Missing / Invalid Citations| Abstain
```

## Detailed Workflow Steps

### 1. Hybrid Search (`src/retrieval/qdrant_store.py` & `src/retrieval/hybrid.py`)
- **Dense Vector Search**: Embeds the user query with **Jina (`jina-embeddings-v5-omni-small`, 1024-d)** and queries Qdrant with a filter on `status == "ready"`, then drops hits below `MIN_DENSE_SCORE` (0.35).
- **Lexical Search (BM25)**: Scrolls up to `LEXICAL_CANDIDATE_LIMIT` (500) ready chunks -- more than the whole 297-chunk collection -- tokenizes with regex word boundaries and ranks with `BM25Okapi`. That scroll is also what makes sibling expansion free of extra round trips.
- **Candidate width**: `candidate_limit = max(rerank_candidate_limit, limit)` when a reranker is configured, otherwise `max(limit * 4, limit)`. Production leaves `RERANKER_MODEL` empty, so with `RETRIEVAL_LIMIT=9` the pool is **36**, not 50.
- **Read resilience**: every Qdrant read goes through `_read_with_retry()` (3 attempts, 0.5s backoff, transient-only).
- **Reciprocal Rank Fusion**: Combines dense and lexical ranks using RRF scoring:
  $$\text{Score}(d) = \sum_{m \in \{\text{dense}, \text{lexical}\}} \frac{1}{60 + \text{rank}_m(d)}$$

### 1b. Hierarchical Sibling Expansion (`src/retrieval/hierarchical.py`)
- After the top-K cut, `expand_with_siblings()` pulls in the missing chunks of a hit's own legal section so the article reads whole, reusing the BM25 scroll already in memory.
- **All-or-nothing per section**: scoring joins a section's chunks with `"".join(...)`, so a family missing a middle piece would glue non-adjacent text together. A family that does not fit the budget is skipped entirely.
- Siblings come back as real `SearchHit`s with real coordinates, so they are independently citable.
- Controlled by `HIERARCHICAL_*`; disabling the flag makes `search()` return its input unchanged.

### 2. Prompt Construction & System Safeguards (`src/prompts/answer_v4.py`)
- Context chunks are rendered as `[C1] source=... version=...` blocks. There are no `<context>` tags -- untrusted data is fenced by an explicit instruction not to follow anything inside CONTEXT.
- `answer_v4` states abstention as **Rule 0 with absolute precedence**, then six citation rules: every sentence needs a marker (including short verdict openers like "Không đúng"), markers go **before** the closing punctuation, and multiple sources are written `[C1][C2]`, never `[C1, C2]`.
- `normalize_citation_markers()` in `generation/service.py` deterministically rewrites any grouped `[C1, C2]` the model still emits.

### 3. Provider Failover Router (`src/providers/router.py`)
- Dispatches prompt requests to the configured primary provider (e.g. Gemini, OpenRouter, or OpenAI).
- On transient network or rate-limit failures, automatically fails over to secondary configured providers.
- `generate_structured()` shares that failover path; a schema the model cannot satisfy raises a non-transient `ProviderError` instead of burning the fallback.

### 4. Structured Output Contract (`src/providers/structured.py`)
- Every provider exposes `generate_structured(request, response_model)` and returns a validated Pydantic object, never raw text.
- instructor selects the strongest mechanism per provider: native `responseSchema` for Gemini, tool calling for OpenAI, and prompt-carried JSON schema for OpenRouter's mixed backends.
- Malformed or invalid payloads are reasked with the validation error attached, up to `STRUCTURED_MAX_RETRIES` attempts.

### 5. Citation Verification & Abstention Guard (`src/generation/service.py`)
- Reads the `citations` list from the validated `GroundedAnswer`.
- Validates that `1 <= n <= len(chunks)` and maps each index to a `Citation` object containing source file name, document ID, version, and excerpt.
- If no citations are parsed or all citations map to invalid indices, the service overrides the answer with the standard abstention string:
  > *"Không tìm thấy thông tin phù hợp trong tài liệu được phép truy cập."*

## Staged evaluation replay

`rag-eval retrieval` saves the captured retrieval evidence before any generation
phase. `rag-eval generation --from-run <retrieval-run-id>` reloads that evidence
and inherits the retrieval run's golden directory, file scope, and canonical
source; it rejects incompatible dataset or artifact fingerprints rather than
silently selecting a new population. The detailed selection precedence,
write-once artifact paths, and report-only Ragas option are in the
[evaluation operations contract](05-observability-evaluation-and-operations.md#staged-offline-rag-evaluation).
