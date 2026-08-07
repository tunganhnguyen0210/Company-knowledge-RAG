# Advanced Retrieval Workflow

```mermaid
flowchart TD
    subgraph INGESTION["1. Offline Ingestion Pipeline"]
        A[Raw Document] --> B[Chunking: Semantic / Parent-Child]
        B --> C["LLM Enrichment (Contextual: situational_context)"]
        C --> D["Embedding: Jina v5 Omni (MRL 128-d & 1024-d)"]
        D --> E[(Qdrant Vector DB & BM25 Index)]
    end

    subgraph RETRIEVAL["2. Online Retrieval Pipeline"]
        UQ[User Query] --> QT{Query Transform}
        
        QT -->|Multi-Query| MQ["LLM Expand (N Queries)"]
        QT -->|HyDE| HD["LLM Generate Hypothetical Doc"]
        QT -->|Raw| RAW[Raw Query]
        
        MQ & HD & RAW --> DENSE["Dense Search (MRL 2-Stage)"]
        RAW --> BM25["Sparse Search (BM25)"]
        
        subgraph MRL["MRL 2-Stage Filter"]
            DENSE --> MRL1["Stage 1: Fast Filter (128-d) -> Top 200"]
            MRL1 --> MRL2["Stage 2: Cosine Re-score (1024-d) -> Top 50"]
        end
        
        MRL2 & BM25 --> RRF["Reciprocal Rank Fusion (RRF)"]
        
        RRF --> RERANK["Cross-Encoder Reranker (Jina v3.5)"]
        RERANK --> MMR["MMR (Maximal Marginal Relevance)"]
        MMR --> TOPN[Top N Final Contexts]
    end

    TOPN --> LLM[LLM Generation / ChatService]
```

## Chi tiết luồng thực thi

### A. Ingestion (Index time)
1. **Chunking**: Semantic / Parent-Child chia nhỏ văn bản.
2. **Contextual Enrichment**: [`src/ingestion/enrichment.py`](file:///D:/User/ProjectGithub/hiepnguyenn-99/Company-knowledge-RAG/src/ingestion/enrichment.py) thêm `situational_context` định vị điều/khoản/tên văn bản vào chunk.
3. **MRL Indexing**: Embed 1024-d, lưu payload phục vụ tra cứu.

### B. Search & Retrieval (Query time)
1. **Query Transformation**: [`src/retrieval/query_transform.py`](file:///D:/User/ProjectGithub/hiepnguyenn-99/Company-knowledge-RAG/src/retrieval/query_transform.py) Multi-Query hoặc HyDE.
2. **Two-Stage Hybrid Search**: [`src/retrieval/qdrant_store.py`](file:///D:/User/ProjectGithub/hiepnguyenn-99/Company-knowledge-RAG/src/retrieval/qdrant_store.py) (MRL Fast 128-d -> MRL Precise 1024-d + BM25).
3. **Fusion & Reranking**: [`src/retrieval/hybrid.py`](file:///D:/User/ProjectGithub/hiepnguyenn-99/Company-knowledge-RAG/src/retrieval/hybrid.py) (RRF -> Jina Reranker v3.5 -> MMR).
4. **Generation**: [`src/generation/service.py`](file:///D:/User/ProjectGithub/hiepnguyenn-99/Company-knowledge-RAG/src/generation/service.py) tổng hợp ngữ cảnh và trả lời.
