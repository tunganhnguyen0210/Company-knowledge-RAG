# Retrieval, Generation & Citations Pipeline

## Fresher AI Engineer Key Concepts

> [!NOTE]
> **What is Hybrid Search & Citation Gating?**  
> - **Hybrid Search** combines two complementary search strategies: **Dense Search** (understanding overall semantic context and meaning) and **Lexical Search** (matching exact names, technical terms, and IDs using BM25).
> - **Reciprocal Rank Fusion (RRF)** combines ranked results from both strategies into a unified, high-precision hit list.
> - **Citation Gating** parses the LLM output for explicit citation markers (`[C1]`, `[C2]`) mapping back to retrieved text. If the model provides an answer without valid citations, the system forces an abstention response to prevent ungrounded hallucinations.

## Pipeline Architecture

```mermaid
flowchart TD
    Query[User Question Payload] --> Dense[Qdrant Dense Vector Search]
    Query --> Lexical[In-Process BM25 Lexical Search]
    
    Dense --> RRF[Reciprocal Rank Fusion RRF k=60]
    Lexical --> RRF
    
    RRF --> MinScore{Filter Score >= min_dense_score}
    MinScore -->|Hits Found| Prompt[Render System Prompt with Context Chunks]
    MinScore -->|No Hits| Abstain[Return Abstention Response]
    
    Prompt --> LLM[Call Provider Router Gemini / OpenRouter / OpenAI]
    LLM --> CitationCheck{Regex Verify Citations C1, C2...}
    
    CitationCheck -->|Valid Citations| Output[Return ChatResponse + Citations]
    CitationCheck -->|Missing / Invalid Citations| Abstain
```

## Detailed Workflow Steps

### 1. Hybrid Search (`src/retrieval/qdrant_store.py` & `src/retrieval/hybrid.py`)
- **Dense Vector Search**: Embeds the user query via Gemini embeddings (`gemini-embedding-001`) and queries Qdrant with a filter on `status == "ready"`.
- **Lexical Search (BM25)**: Tokenizes ready chunk payloads using regex word boundaries and ranks them using `BM25Okapi`.
- **Reciprocal Rank Fusion**: Combines dense and lexical ranks using RRF scoring:
  $$\text{Score}(d) = \sum_{m \in \{\text{dense}, \text{lexical}\}} \frac{1}{60 + \text{rank}_m(d)}$$

### 2. Prompt Construction & System Safeguards (`src/prompts/answer_v1.py`)
- Retained context chunks are rendered inside strict untrusted data blocks (`<context>` tags) in system prompts.
- The prompt explicitly instructs the LLM to format every factual claim with citation tags (`[C1]`, `[C2]`) referencing the index of the corresponding context chunk.

### 3. Provider Failover Router (`src/providers/router.py`)
- Dispatches prompt requests to the configured primary provider (e.g. Gemini, OpenRouter, or OpenAI).
- On transient network or rate-limit failures, automatically fails over to secondary configured providers.

### 4. Citation Verification & Abstention Guard (`src/generation/service.py`)
- Extracts citation markers `[C<n>]` from the generated answer text.
- Validates that `1 <= n <= len(chunks)` and maps each marker to a `Citation` object containing source file name, document ID, version, and excerpt.
- If no citations are parsed or all citations map to invalid indices, the service overrides the answer with the standard abstention string:
  > *"Không tìm thấy thông tin phù hợp trong tài liệu được phép truy cập."*
