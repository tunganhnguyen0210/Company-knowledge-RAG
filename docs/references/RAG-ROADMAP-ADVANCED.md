# Lộ Trình Phát Triển RAG: Từ Baseline Đến Advanced & Agentic RAG

> **Phiên bản hiện tại:** `v1.3` | **Cập nhật lần cuối:** 2026-08-05 | **Trạng thái:** 🟢 Active

Tài liệu này định hình lộ trình nâng cấp hệ thống **Company Knowledge RAG** từ kiến trúc **Baseline RAG + Evaluation** hiện tại tiến lên các cấp độ **Advanced RAG**, **GraphRAG**, **Agentic RAG**, và **Production LLMOps**.

---

## Changelog

| Phiên bản | Ngày | Nội dung thay đổi | Tác giả |
|---|---|---|---|
| `v1.3` | 2026-08-05 | Bổ sung mục 4.8 System Rate Limiting, Throttling & Cost Control Strategy | Team AI |
| `v1.2` | 2026-08-05 | Bổ sung mục 4.5 SLA, 4.6 Incident Runbook, 4.7 Schema Versioning & Migration Strategy | Team AI |
| `v1.1` | 2026-08-05 | Hoàn thiện lộ trình Level 1–5: Action Items, DoD, Rollback Strategy từng cấp | Team AI |
| `v1.0` | 2026-08-05 | Khởi tạo tài liệu: Hiện trạng Level 0, Sơ đồ Level 1–5, Implementation Matrix | Team AI |

---


## 1. Hiện Trạng Hệ Thống Hiện Tại (Production-Grade Advanced RAG)

Dựa trên tài liệu kiến trúc [`RAG-ARCHITECTURE.md`](../RAG-ARCHITECTURE.md) và tra cứu từ `corpus2skill` ([`SKILL_TREE.md`](../.agents/skills/corpus2skill/SKILL_TREE.md)), hệ thống đã vượt trên mức Naive Baseline đơn thuần và đạt chuẩn **Production-Grade Advanced RAG** với các kỹ thuật chính đã tích hợp:

| Thành Phần | Công Nghệ / Kỹ Thuật Đang Sử Dụng | File Mã Nguồn / Cấu Hình | Đánh Giá Hiện Trạng |
| --- | --- | --- | --- |
| **Multi-Format Ingestion** | Parsing đa định dạng (PDF, DOCX, MD, TXT) + Unicode NFC Text Normalization + Registry Status Tracking (`ready`, `needs_ocr`, `failed`) | [`src/ingestion/parser.py`](../src/ingestion/parser.py)<br>[`src/storage/registry.py`](../src/storage/registry.py) | Xử lý tài liệu đa định dạng sạch, chuẩn hóa văn bản và theo dõi trạng thái index. |
| **Section-Aware Chunking** | Section-aware Recursive Character Chunking (~1,200 chars, 10–20% overlap) | [`src/ingestion/chunker.py`](../src/ingestion/chunker.py) | Giữ ngữ cảnh tự nhiên theo tiêu đề/đoạn văn, tránh ngắt đứt ý ở ranh giới chunk. |
| **Contextual Enrichment** | Prepend LLM Document Summaries & Hypothetical Q&A (HyQA) | [`src/ingestion/enrichment.py`](../src/ingestion/enrichment.py) | Bổ sung thông tin ngữ cảnh tổng quan trước khi embed, tăng Recall cho query chủ đề. |
| **Dense Vector Storage** | Qdrant Vector Store + Embedding Models (Gemini `text-embedding-004`) + Score Thresholding (`min_dense_score`) | [`src/retrieval/qdrant_store.py`](../src/retrieval/qdrant_store.py) | Tìm kiếm ngữ nghĩa (Semantic Search) chính xác với bộ lọc điểm số tối thiểu. |
| **Lexical BM25 Search** | In-process BM25 (Rank-BM25) với Tokenization tiếng Việt & tiếng Anh | [`src/retrieval/bm25.py`](../src/retrieval/bm25.py) | Đảm bảo exact-match cho từ khóa, tên riêng, mã số tài liệu mà Vector Search bỏ lỡ. |
| **Rank Fusion (RRF)** | Reciprocal Rank Fusion (RRF $k=60$) kết hợp Dense + Lexical Ranks | [`src/retrieval/hybrid.py`](../src/retrieval/hybrid.py) | Gộp rank độc lập từ 2 retriever, khắc phục điểm yếu của từng phương pháp. |
| **Multi-Provider Router** | Multi-Provider Failover Router (Gemini, OpenRouter, OpenAI) + Auto Retry | [`src/providers/`](../src/providers/) | Tự động chuyển đổi provider LLM khi gặp lỗi API hoặc rate limit, đảm bảo uptime. |
| **Citation-Gated Guardrails** | Citation Tagging (`[Doc X, Chunk Y]`) + Pydantic/Instructor Structured Output (`GroundedAnswer`) + Auto-Abstention Gate | [`src/generation/generator.py`](../src/generation/generator.py)<br>[`src/prompts/`](../src/prompts/) | Bắt buộc kiểm tra trích dẫn nguồn; tự động từ chối trả lời nếu dữ liệu không đủ (chống hallucination). |
| **Observability & Tracing** | Langfuse Span Tracing (Telemetry, Latency, Token & Cost Tracking) | [`src/observability/langfuse.py`](../src/observability/langfuse.py)<br>[`docker-compose.langfuse.yml`](../docker-compose.langfuse.yml) | Giám sát toàn bộ pipeline runtime, đo độ trễ từng span và chi phí token. |
| **Evaluation & Benchmark** | Ground Truth Golden Set Dataset + CLI Evaluator (`company-rag-evaluate`) + LLM-as-a-Judge Rubrics | [`evaluation/GOLDEN_SET_SPEC.md`](../evaluation/GOLDEN_SET_SPEC.md)<br>[`src/evaluation/`](../src/evaluation/)<br>[`src/cli.py`](../src/cli.py) | Đánh giá định kỳ tự động Faithfulness và Precision/Recall chống regression. |

---

## 2. Lộ Trình Nâng Cấp Từng Cấp Độ (Evolution Roadmap)

> **Dependency Chain:** Level 1 → Level 3 (Self-RAG cần Reranker làm input) → Level 4 (Safety bao quanh toàn pipeline). Level 2 (GraphRAG) có thể triển khai song song sau Level 1. Level 5 là tùy chọn khi corpus domain-specific cần fine-tune embedding/LLM.

```
Level 0: Baseline RAG + Evals ✅ (Hiện tại: Ingestion, BM25+Dense Hybrid RRF, Citation Gate, Langfuse)
  │
  ├──► Level 1: Advanced Retrieval & Context Engineering  [Ưu tiên 1 - 1-2 tuần]
  │      ├── Semantic Chunking & RAPTOR Tree Summarization
  │      ├── Hierarchical Chunking (Parent-Child) & Late Chunking / Contextual Embeddings
  │      ├── Two-Stage Retrieval (Cross-Encoder Reranking, ColBERT Late Interaction, SPLADE)
  │      ├── Matryoshka Representation Learning (MRL) & MMR Diversification
  │      └── Query Transformation (HyDE, HyQA, Multi-Query Expansion)
  │
  ├──► Level 2: GraphRAG & Knowledge Graphs [Ưu tiên 3 - Song song/Dài hạn]
  │      ├── Coreference Resolution & Entity-Relation Triple Extractors (Neo4j/Memgraph)
  │      ├── Subgraph Traversal (BFS k=2) & LightRAG Dual-Level Embeddings
  │      └── Microsoft GraphRAG (Leiden Community Detection & Global Thematic Search)
  │
  ├──► Level 3: Agentic RAG & Stateful Workflows [Ưu tiên 2 - 3-4 tuần]
  │      ├── LangGraph State Machine (TypedState, Checkpointing, Reducers, Recovery)
  │      ├── Self-RAG (Relevance & Hallucination Self-Check Loop) & Corrective RAG (CRAG)
  │      ├── Multi-Session Memory Management (Episodic, Semantic, Working Memory)
  │      ├── Multi-Agent Debate Pattern (Adversarial Collaboration)
  │      ├── FastAPI Integration Bridge (Agent ↔ REST API)
  │      └── Human-in-the-Loop (HITL Interrupt Gate)
  │
  ├──► Level 4: Production LLMOps, Inference Optimization & Safety Guardrails [Ưu tiên 2 - Đồng thời]
  │      ├── Defense-in-Depth 4 Tầng (PII Redaction, Spotlighting, Llama Guard 3, NLI Entailment)
  │      ├── vLLM Serving (PagedAttention, Prefix Caching, Continuous Batching, Speculative Decoding)
  │      ├── Vector Index Quantization (HNSW, IVF-PQ, SQ8) & Redis Semantic Caching
  │      ├── Model Quantization & Parallelism (FP8/AWQ, Disaggregated Prefill/Decode)
  │      └── Continuous Evaluation CI/CD (RAGAS auto-gate trên Golden Set)
  │
  └──► Level 5: Fine-tuning & Domain Adaptation [Tùy chọn - Dài hạn]
         ├── Embedding Fine-tuning (Domain-specific Contrastive Learning)
         ├── LLM Instruction Tuning (LoRA / QLoRA trên dữ liệu nội bộ)
         └── Alignment (DPO / ORPO với dữ liệu phản hồi từ Golden Set)
```

---

## 3. Chi Tiết Từng Cấp Độ Nâng Cấp & Trích Dẫn Triển Khai

---

### Cấp Độ 1: Advanced Retrieval & Context Engineering

#### **Mục Tiêu & Vấn Đề Cần Giải Quyết:**
1. Khắc phục ranh giới cắt đứt ngữ cảnh (*lost context boundary*) của Fixed-size Chunking bằng Semantic Chunking, RAPTOR và Parent-Child phân cấp.
2. Tăng Precision & Recall giai đoạn Retrieval qua Two-Stage (Cross-Encoder, ColBERT) và lọc trùng lặp (MMR).
3. Thu hẹp khoảng cách từ vựng (vocab gap) giữa câu hỏi và tài liệu qua Query Transformation.

> **Trích dẫn từ RAG Knowledge Handbook (`RAG-KNOWLEDGE-SUMMARY.md` Mục 1.2 & 2.3):**
> - *Semantic Chunking:* "Cắt theo ranh giới thay đổi chủ đề bằng Cosine Similarity giữa câu liên tiếp (ngưỡng ≈ 0.85) — tránh cắt ngang ý."
> - *RAPTOR:* "Gom cụm chunk → LLM tóm tắt đệ quy thành cây tri thức. Retrieve linh hoạt: câu hỏi chi tiết ở nút lá, câu hỏi tổng hợp ở nút cấp cao."
> - *Parent-Child Chunking:* "Index các đoạn nhỏ (Child 256 tokens) để Precision cao, inject đoạn lớn hơn (Parent 1024–2048 tokens) vào Prompt giữ đầy đủ ngữ cảnh."
> - *Contextual Embeddings:* "Dùng LLM bổ sung 1 câu ngữ cảnh toàn văn bản vào đầu mỗi chunk → Giảm lỗi retrieval từ 49% đến 67%."
> - *ColBERT Late Interaction:* "Giữ 1 vector/token. Toán tử MaxSim tìm match token-by-token → Chi tiết hơn Bi-encoder, nhanh hơn Cross-encoder."
> - *Two-Stage Reranking:* "Stage 1: Top 50–100 bằng Bi-encoder/BM25. Stage 2: Cross-encoder (`bge-reranker-v2-m3`, `Cohere Rerank v3.5`) → Top 3–5 (tăng 15–25% precision)."
> - *MMR:* "$MMR = \arg\max_{d \in R \setminus S} \left[ \lambda \text{Sim}_1(d, q) - (1-\lambda) \max_{d_j \in S} \text{Sim}_2(d, d_j) \right]$ — loại bỏ chunk trùng lặp."

#### **Hành Động Triển Khai (Action Items):**
1. **Nâng Cấp Chunking Strategies (`src/ingestion/chunker.py`):**
   - Thêm **Semantic Chunking**: Cắt theo ranh giới thay đổi chủ đề (Cosine Similarity ~0.85 giữa các câu liên tiếp), giúp chunk tự nhiên hơn Fixed-size.
   - Triển khai **Parent-Child Chunking**: Lưu Child Chunk (256 tokens) trong Qdrant; khi generate nạp Parent Chunk (1024 tokens) vào Context Window.
   - Thêm **RAPTOR Tree Summarization** (`src/ingestion/raptor.py`): Cluster chunks → LLM tóm tắt đệ quy, index cả summary nodes vào Qdrant để hỗ trợ query tổng hợp.
2. **Nâng Cấp Enrichment (`src/ingestion/enrichment.py`):**
   - Thêm **Contextual Embeddings** (Anthropic pattern): Prepend 1–2 câu tóm tắt ngữ cảnh văn bản vào đầu từng chunk trước khi embed.
   - Ứng dụng **MRL (Matryoshka Representation Learning)**: Dùng 128-d vector filter thô nhanh, rerank bằng 768-d vector.
3. **Two-Stage Retrieval & Reranking (`src/retrieval/hybrid.py`):**
   - **Stage 1:** Giữ nguyên Hybrid Dense + BM25 RRF lấy Top 50 candidates.
   - **Stage 2:** Thêm Cross-Encoder Reranker (`bge-reranker-v2-m3` hoặc `Cohere Rerank API`) re-score Top 50 → Top 5.
   - Tích hợp **MMR Diversification** ($\lambda = 0.7$) sau reranking để loại trùng lặp nội dung.
4. **Query Transformation Layer (`src/retrieval/query_transform.py`):**
   - **HyDE**: Sinh tài liệu giả định từ query → embed tài liệu giả định thay vì embed câu hỏi thô.
   - **Multi-Query Expansion**: Sinh 3–5 paraphrase của query → search song song → merge kết quả.
   - **HyQA** (đã có qua enrichment): Tận dụng các hypothetical questions đã index.

#### **Tiêu Chí Hoàn Thành (Definition of Done):**
- [ ] Precision@5 trên Golden Set tăng ≥ 15% so với baseline.
- [ ] Latency P95 tăng không quá 150ms (budget cho Stage 2 Reranker).
- [ ] Đo bằng: `company-rag-evaluate --level 1 --compare-baseline`.

#### **Rollback Strategy:**
- Nếu Reranker tăng latency > 200ms P95: tắt Stage 2, giữ MMR trên RRF output.
- Nếu RAPTOR gây index quá lớn: giới hạn depth = 1 (chỉ 1 cấp summary).

---

### Cấp Độ 2: GraphRAG & Knowledge Graphs (Multi-Hop Reasoning)

#### **Mục Tiêu & Vấn Đề Cần Giải Quyết:**
Giải quyết 3 hạn chế cốt lõi của Flat RAG: câu hỏi liên kết nhiều bước (*multi-hop relational*), câu hỏi tổng quan toàn bộ corpus (*global thematic*), và suy luận xuyên văn bản (*cross-document reasoning*).

> **⚠️ Dependency:** Level 1 (Chunking chất lượng cao) nên hoàn thành trước để Graph nodes có nội dung đầy đủ hơn.

> **Trích dẫn từ RAG Knowledge Handbook (Mục 3.1, 3.2 & 3.3):**
> - *Ranh giới Flat RAG vs GraphRAG:* "Flat RAG thất bại với: 1. Multi-hop relational; 2. Global thematic; 3. Cross-document reasoning. GraphRAG biểu diễn tri thức dạng Đồ thị: Node (Entity), Edge (Relation), Triple (Subject, Predicate, Object)."
> - *Coreference Resolution:* "Quy chiếu đại từ ('Ông ấy', 'Công ty này') về đúng tên riêng → Tránh mất 30–40% liên kết đồ thị."
> - *Entity Disambiguation & Deduplication:* "Chuẩn hóa biến thể tên ('OpenAI', 'Open AI', 'OAI' → 1 Node duy nhất)."
> - *Microsoft GraphRAG & LightRAG:* "Leiden Community Detection → Pre-compute báo cáo cộng đồng cho Global Search. LightRAG dùng dual-level vector search cho cả Nodes và Edges — không cần pre-compute đắt đỏ."

#### **Hành Động Triển Khai (Action Items):**
1. **Cơ Sở Dữ Liệu Đồ Thị (`docker-compose.yml`):**
   - Thêm container **Neo4j** hoặc **Memgraph** vào stack hạ tầng bên cạnh Qdrant.
2. **Pipeline Trích Xuất Đồ Thị (`src/ingestion/graph_extractor.py`):**
   - Thêm bước **Coreference Resolution** chuẩn hóa đại từ nhân xưng trước khi trích xuất.
   - Dùng LLM trích xuất Triples `(Subject, Predicate, Object)` + **Entity Disambiguation & Deduplication** (chuẩn hóa tên biến thể về 1 Node duy nhất) vào Neo4j.
3. **Triển Khai Hybrid Graph-Vector Search (`src/retrieval/graph_retriever.py`):**
   - Vector search tìm Seed Nodes → Traversal BFS ($k=2$ hops) lấy Subgraph Triples nạp vào Prompt.
   - Triển khai **Leiden Community Detection** (Microsoft GraphRAG) sinh báo cáo cộng đồng đệ quy phục vụ Global Search.

#### **Tiêu Chí Hoàn Thành (Definition of Done):**
- [ ] Multi-hop queries (≥ 2 entity hops) trả lời đúng ≥ 70% trên golden set multi-hop.
- [ ] Graph build time < 30 phút cho 1,000 tài liệu.

#### **Rollback Strategy:**
- Nếu Graph traversal trả về quá nhiều noise: giảm BFS depth xuống $k=1$.
- Nếu Leiden pre-compute quá tốn kém: dùng LightRAG (no pre-compute) thay thế.

---

### Cấp Độ 3: Agentic RAG & Stateful Workflows (LangGraph Architecture)

#### **Mục Tiêu & Vấn Đề Cần Giải Quyết:**
Chuyển đổi từ RAG tĩnh 1-pass sang **Cyclic State Machine**: tự đánh giá context/answer (Self-RAG), tự bổ sung nguồn (Corrective RAG), quản lý hội thoại đa phiên, phối hợp đa Agent, và hỗ trợ Human-in-the-Loop.

> **⚠️ Dependency:** Level 1 (Cross-Encoder Reranker) phải hoàn thành trước — Self-RAG Evaluator Node dùng Reranker score làm input đánh giá Context Relevance.

> **Trích dẫn từ RAG Knowledge Handbook (Mục 4.1, 4.2 & 4.3):**
> - *LangGraph Orchestration:* "Khắc phục nhược điểm LCEL 1 chiều. Core: `StateGraph`, `TypedState`, `Node`, `Edge` & `Conditional Edges`. Reducers kiểm soát luật merge state (`Overwrite` cho status; `Annotated[list, add]` cho append messages)."
> - *Checkpointing:* "Snapshot state sau mỗi super-step qua `MemorySaver`, `SqliteSaver`, `PostgresSaver`. Gắn `thread_id` phân biệt session. Fault Tolerance: Retry (exponential backoff) → Fallback model → Dead-letter queue."
> - *Multi-Agent Debate:* "Các agent (GPT-4o, Claude, Gemini) critique lẫn nhau → Judge tổng hợp (giảm 15–25% hallucination)."
> - *Memory Management:* "Episodic Memory (per-session context), Semantic Memory (long-term facts), Working Memory (active context window)."
> - *HITL:* "`interrupt({action, risk, evidence})` tạm dừng graph trước action nguy hiểm. Resume: `compiled.invoke(Command(resume={approved: True}), config)`."

#### **Hành Động Triển Khai (Action Items):**
1. **Khởi Tạo LangGraph Engine (`src/agent/graph.py`):**
   - Xây dựng `TypedState` lưu trữ: `query`, `retrieved_chunks`, `generation`, `eval_scores`, `retry_count`, `conversation_history`.
   - Cấu hình Persistence: `SqliteSaver` (dev) / `PostgresSaver` (prod) gắn `thread_id` — hỗ trợ crash recovery & multi-session.
   - Cấu hình **Fault Tolerance**: Retry với exponential backoff → Fallback provider → Dead-letter queue log.
2. **Dynamic Nodes & Routing (`src/agent/nodes.py`):**
   - **Query Router Node:** Phân loại ý định (Direct Answer, RAG Vector Search, Graph Search, SQL Query, External Web Search).
   - **Self-RAG Evaluator Node:** Dùng LLM chấm điểm `Context Relevance` và `Faithfulness`. Nếu thấp hơn ngưỡng → Rewriter Node viết lại Query → search lại (tối đa `retry_count=3`).
   - **Corrective RAG (CRAG) Node:** Nếu dữ liệu nội bộ không đủ → gọi Web Search API (Tavily / Google Search) làm nguồn bổ sung.
3. **Memory Management (`src/agent/memory.py`):**
   - **Working Memory:** Giới hạn `conversation_history` window (tối đa 10 turns) → tóm tắt bằng LLM nếu vượt.
   - **Episodic Memory:** Lưu toàn bộ lịch sử hội thoại theo `thread_id` vào DB (PostgreSQL/SQLite).
   - **Semantic Memory:** Tóm tắt facts quan trọng từ các session trước, embed vào Qdrant collection riêng cho long-term recall.
4. **FastAPI Integration Bridge (`src/api/routes.py`, `src/agent/bridge.py`):**
   - Tạo `AgentBridge` class wrap LangGraph compiled graph.
   - Expose endpoint `POST /api/v1/chat` nhận `{query, thread_id, session_config}` → invoke agent → stream response.
   - Giữ nguyên endpoint `POST /api/v1/query` (non-agentic 1-pass) cho backward compatibility.
5. **Multi-Agent Debate & HITL (`src/agent/debate.py`, `src/agent/hitl.py`):**
   - Triển khai **Debate Pattern**: Gemini + OpenRouter tranh luận → LLM Judge chốt (cho câu hỏi phức tạp, confidence thấp).
   - `interrupt({action, risk, evidence})` trước các hành động ghi dữ liệu hoặc thực thi lệnh nhạy cảm.

#### **Tiêu Chí Hoàn Thành (Definition of Done):**
- [ ] Self-RAG loop giảm Hallucination (Faithfulness) ít nhất 10% so với 1-pass trên Golden Set.
- [ ] Multi-session conversation duy trì context đúng qua ≥ 5 turns liên tiếp.
- [ ] API `/api/v1/chat` hoạt động song song với `/api/v1/query` không breaking change.

#### **Rollback Strategy:**
- Nếu Self-RAG loop gây latency > 3s: tắt loop (`retry_count=0`), dùng 1-pass.
- Nếu Memory làm context window overflow: tắt Episodic Memory, chỉ dùng Working Memory.

---

### Cấp Độ 4: Production LLMOps, Inference Optimization & Safety Guardrails

#### **Mục Tiêu & Vấn Đề Cần Giải Quyết:**
Bảo mật doanh nghiệp (chống Prompt Injection, Lethal Trifecta), tối ưu hóa Latency (TTFT < 100ms P95), tăng Throughput, và thiết lập Continuous Evaluation CI/CD pipeline chống regression tự động.

> **Trích dẫn từ RAG Knowledge Handbook (Mục 5.1, 5.3, 6.1, 7.1, 8.1 & 8.3):**
> - *The Lethal Trifecta & Defense-in-Depth:* "L1 Input (<30ms): PII redaction (Presidio), Meta Prompt Guard. L2 LLM Layer: System prompt hardening + Spotlighting (giảm ASR >50% → <2%). L3 Output (<50ms): Llama Guard 3 8B, NLI Entailment (SelfCheckGPT, Semantic Entropy). L4 Audit: Async logging. Tổng budget ≤ 80-100ms P95."
> - *vLLM & PagedAttention:* "PagedAttention loại bỏ 60–80% lãng phí RAM KV Cache, tăng 24× throughput. Prefix Caching giảm 70–90% TTFT. Speculative Decoding cải thiện TPOT."
> - *Quantization & Vector Index:* "HNSW / IVF-PQ / SQ8 nén RAM 32×. FP8 / AWQ 4-bit serving ít suy giảm accuracy."
> - *Eval-Driven Development (EDD):* "Evals = Unit Tests mới. L2: CI/CD Regression Release Gates — gate deployment nếu Golden Set metrics sụt giảm."

#### **Hành Động Triển Khai (Action Items):**
1. **Defense-in-Depth 4 Tầng (`src/observability/guardrails.py`):**
   - **L1 Input Guard:** Presidio ẩn PII + Meta Prompt Guard chặn Prompt Injection direct/indirect (<30ms).
   - **L2 LLM Layer:** **Spotlighting (Microsoft)** wrap toàn bộ RAG context bằng thẻ định danh an toàn chống Lethal Trifecta.
   - **L3 Output Guard:** `Llama Guard 3 8B` kiểm tra an toàn nội dung + `DeBERTa-v3` NLI Entailment check phát hiện hallucination (<50ms).
   - **L4 Audit Layer:** Async audit log với Object Lock S3 phục vụ truy xuất an ninh.
2. **LLM Serving Engine vLLM (`docker-compose.yml`, `src/providers/vllm.py`):**
   - Chạy local LLM (Qwen-2.5 / Llama-3) trên vLLM với **PagedAttention**, **Prefix Caching (RadixAttention)**, **Continuous Batching**.
   - Thiết lập **Speculative Decoding** với Draft model nhỏ để tăng TPOT.
3. **Vector Index & Semantic Cache (`src/retrieval/cache.py`):**
   - Cấu hình **HNSW + SQ8 / IVF-PQ** trên Qdrant khi corpus > 100k chunks.
   - **Redis Semantic Cache**: Trả kết quả ngay nếu Cosine Similarity > 0.95 với query cache — giảm 60-70% LLM calls cho câu hỏi lặp lại.
4. **Continuous Evaluation CI/CD Pipeline (`.github/workflows/eval.yml`):**
   - Trigger mỗi PR merge vào `main`: chạy `company-rag-evaluate` trên toàn bộ Golden Set.
   - **Quality Gate:** Nếu `Faithfulness < 0.85` hoặc `Context Recall < 0.80` → block deployment tự động.
   - Ghi kết quả eval vào Langfuse dataset để track trend theo thời gian.

#### **Tiêu Chí Hoàn Thành (Definition of Done):**
- [ ] TTFT P95 < 100ms với Prefix Caching bật.
- [ ] ASR (Attack Success Rate) Prompt Injection < 2% sau Spotlighting.
- [ ] CI/CD pipeline tự động block deployment khi eval metrics sụt.

#### **Rollback Strategy:**
- Nếu vLLM local không đủ GPU: fallback về Cloud API (Gemini/OpenRouter) với guardrails layer giữ nguyên.
- Nếu Llama Guard 3 làm latency > 80ms: dùng rule-based filter thay thế cho L3.

---

### Cấp Độ 5: Fine-tuning & Domain Adaptation (Tùy Chọn)

#### **Mục Tiêu & Vấn Đề Cần Giải Quyết:**
Khi corpus domain-specific của công ty có vocabulary đặc thù mà base embedding model hoặc LLM không hiểu tốt, cần fine-tune để tăng chất lượng retrieval và generation trên dữ liệu nội bộ.

> **Trích dẫn từ RAG Knowledge Handbook (Mục 8 - Fine-Tuning & Alignment):**
> - *LoRA/QLoRA:* "Cập nhật ma trận low-rank thay vì toàn bộ weight. QLoRA = LoRA trên base model 4-bit quantized → Fine-tune LLM 7B trên GPU 24GB."
> - *DPO (Direct Preference Optimization):* "Học từ cặp (preferred, rejected) response không cần Reward Model riêng biệt."
> - *ORPO (Odds Ratio Preference Optimization):* "Kết hợp SFT + Preference Alignment trong 1 loss function — ít data hơn DPO."

#### **Điều Kiện Kích Hoạt Level 5:**
- Golden Set `Context Recall < 0.75` sau Level 1 → Embedding không hiểu domain vocabulary → cần Embedding Fine-tuning.
- `Faithfulness < 0.80` sau Level 3 → LLM không quen format/style tài liệu nội bộ → cần Instruction Tuning.

#### **Hành Động Triển Khai (Action Items):**
1. **Embedding Fine-tuning (`scripts/finetune_embedding.py`):**
   - Tạo tập training từ Golden Set: `(query, positive_chunk, negative_chunks)`.
   - Fine-tune `text-embedding-004` hoặc `bge-m3` với Contrastive Learning (InfoNCE loss).
2. **LLM Instruction Tuning (`scripts/finetune_llm.py`):**
   - Dùng **QLoRA** fine-tune Llama-3 / Qwen-2.5 (7B) trên tập `(question, context, grounded_answer)` từ Golden Set.
   - Target: model hiểu format trích dẫn `[Doc X, Chunk Y]` và tự động abstain khi thiếu nguồn.
3. **Alignment với DPO/ORPO (`scripts/alignment.py`):**
   - Thu thập cặp `(preferred_answer, rejected_answer)` từ Langfuse feedback.
   - Chạy **ORPO** để align model với hành vi trả lời có trích dẫn, từ chối khi không chắc.

#### **Rollback Strategy:**
- Nếu fine-tuned model kém hơn base model trên Golden Set → revert về base model + system prompt.

---

## 4. Bảng So Sánh Lộ Trình Triển Khai (Implementation Matrix)

| Tiêu Chí | Baseline (Hiện Tại) | Level 1: Advanced RAG | Level 2: GraphRAG | Level 3: Agentic RAG | Level 4: Production LLMOps |
| --- | --- | --- | --- | --- | --- |
| **Retrieval Engine** | Dense + BM25 + RRF | Dense + BM25 + Cross-Encoder + ColBERT + HyDE + Multi-Query | Vector + Knowledge Graph (Neo4j) | Dynamic Multi-Source Routing (Router Node) | Semantic Cache + Multi-Index HNSW/SQ8 |
| **Chunking & Context** | Section-aware Recursive | Semantic + Parent-Child + RAPTOR + Contextual Embeddings | Entity-Relation Triples + Coreference | Dynamic chunks per query type | Prefix-Cached Context Window |
| **Execution Flow** | Linear 1-Pass | Linear 1-Pass + Rerank + Query Transform | Graph Traversal + Vector Hybrid | Cyclic State Machine (LangGraph) | Async Distributed Pipeline |
| **Self-Correction** | Abstention tĩnh | Abstention tĩnh | Abstention tĩnh | Self-RAG Loop + CRAG Web Search (retry ≤ 3) | NLI Entailment & Semantic Entropy Check |
| **Memory** | Stateless | Stateless | Stateless | Working + Episodic + Semantic Memory | Stateful + Redis Cache |
| **Safety & Guardrails** | Basic Citation Gate | Basic Citation Gate | Basic Citation Gate | HITL Interrupt Gate | Defense-in-Depth 4 Tầng (Spotlighting + Llama Guard 3) |
| **Serving & Latency** | Cloud API (Gemini/OpenAI) | Cloud API + Local Reranker (+30–50ms) | Cloud API + Graph DB | Multi-Agent Orchestration (>1s complex queries) | Local vLLM TTFT <100ms P95 |
| **Evaluation Mechanism** | Golden Set CLI Manual | Golden Set CLI + Level 1 Delta Report | Multi-hop Golden Set | Self-RAG internal scores + Golden Set | CI/CD Auto-gate (RAGAS) on every PR |
| **Estimated Effort** | ✅ Done | 1–2 tuần | 3–5 tuần (song song) | 3–4 tuần | 2–3 tuần (infra) + ongoing |

---

## 4.5 Khung Cam Kết Chất Lượng Dịch Vụ (Non-Cost Production SLA)

Để đảm bảo hệ thống vận hành ổn định trong môi trường Enterprise Production, các chỉ số SLA (ngoại trừ chi phí) được quy định như sau:

### 1. Latency SLA (Độ Trễ Phản Hồi)
- **TTFT (Time To First Token):**
  - Standard Query (1-pass): $\le 300\text{ms}$ (P95), $\le 500\text{ms}$ (P99).
  - Prefix-cached / Local vLLM: $\le 100\text{ms}$ (P95).
- **Total Latency (Thời gian trả kết quả hoàn chỉnh):**
  - Standard Query (1-pass): $\le 2.0\text{s}$ (P95).
  - Agentic Multi-step / Self-RAG loop: $\le 5.0\text{s}$ (P95).
- **Reranking Stage 2 Overhead:** $\le 150\text{ms}$ (P95).

### 2. Availability & Reliability SLA (Độ Sẵn Sàng & Độ Tin Cậy)
- **System Uptime:** $\ge 99.9\%$ (tương đương downtime $\le 43.8$ phút/tháng).
- **API Error Rate:** $\le 0.1\%$ tổng số requests (lỗi HTTP 5xx).
- **Failover Recovery Time:** $\le 2\text{s}$ để tự động chuyển đổi provider khi primary LLM gặp sự cố.

### 3. Throughput & Concurrency SLA (Sức Chứa & Tải)
- **Concurrent Users / RPS:** Tối thiểu $50\text{ RPS}$ cho API non-agentic và $10\text{ RPS}$ cho Agentic graph.
- **Queue Wait Time:** $\le 200\text{ms}$ khi hệ thống chạm đỉnh tải (peak hour).

### 4. Quality & Accuracy SLA (Chất Lượng & An Toàn Ngữ Cảnh)
- **Faithfulness (Chống bịa đặt):** $\ge 90\%$ trên Golden Set.
- **Context Recall:** $\ge 85\%$ (đảm bảo tìm đúng thông tin cần thiết).
- **Abstention Accuracy (Từ chối khi thiếu thông tin):** $\ge 95\%$ (tự động từ chối khi context rỗng hoặc không liên quan).
- **Citation Accuracy:** $100\%$ câu trả lời chứa thông tin từ context phải gắn trích dẫn `[Doc X, Chunk Y]`.

### 5. Security & Safety SLA (An Ninh & An Toàn Hệ Thống)
- **Prompt Injection Defense:** ASR (Attack Success Rate) $\le 1\%$.
- **PII Leakage Rate:** $0\%$ (100% PII nhạy cảm như CCCD, email, API key bị mask trước khi lưu trữ hoặc gửi tới LLM).
- **Guardrail Latency Overhead:** Overhead từ 4 tầng Defense-in-Depth $\le 80\text{ms}$ (P95).

### 6. Ingestion & Data SLA (Xử Lý Dữ Liệu)
- **Ingestion Latency:** $\le 10\text{ giây}$ / tài liệu chuẩn (PDF/DOCX < 20 trang).
- **Index Freshness:** Dữ liệu cập nhật xuất hiện trong Vector DB & Cache trong vòng $\le 2\text{ phút}$.
- **Graph Extraction Rate (Level 2):** $\le 30\text{ phút}$ cho 1,000 tài liệu.

---

## 4.6 Incident Response Runbook (Xử Lý Sự Cố Khi Vi Phạm SLA)

Khi bất kỳ chỉ số SLA nào bị vi phạm trong môi trường Production, team phải thực hiện theo quy trình sau:

### Phân Loại Mức Độ Sự Cố

| Mức | Điều kiện kích hoạt | Thời gian xử lý tối đa |
|---|---|---|
| **P0 — Critical** | Uptime < 99%, API Error Rate > 5%, PII Leakage phát hiện | **15 phút** |
| **P1 — High** | TTFT P95 > 1s, Faithfulness < 80%, Prompt Injection ASR > 5% | **1 giờ** |
| **P2 — Medium** | Context Recall < 75%, Ingestion Latency > 60s, Queue Wait > 500ms | **4 giờ** |
| **P3 — Low** | Quality degradation nhẹ, KPI sụt nhưng vẫn trong ngưỡng SLA ± 5% | **1 ngày làm việc** |

### Quy Trình Xử Lý Theo Từng Tình Huống

#### 🔴 P0: Hệ thống Down / PII Leakage
1. **Phát hiện:** Langfuse Alert / CI/CD Gate fail / user report.
2. **Ngay lập tức (< 5 phút):** Kích hoạt Multi-Provider Failover (`src/providers/`) → chuyển sang provider dự phòng.
3. **Nếu toàn bộ provider fail:** Bật chế độ **Static Fallback** — trả về thông báo "Hệ thống đang bảo trì" thay vì lỗi 500.
4. **PII Leakage:** Cô lập session bị ảnh hưởng, tắt Ingestion pipeline ngay, audit log toàn bộ request 24h trước.
5. **Escalate:** Báo cáo kỹ sư chịu trách nhiệm trong **15 phút**; cập nhật status page.

#### 🟠 P1: Latency cao / Faithfulness sụt mạnh
1. **Langfuse Trace:** Xác định span nào gây bottleneck (Retrieval? Reranker? Generation? Guardrails?).
2. **Latency cao:**
   - Reranker overhead > 200ms → **Rollback**: tắt Stage 2 reranker (`retry_count=0`), giữ RRF output.
   - vLLM TTFT cao → kiểm tra Prefix Cache hit rate; restart vLLM service nếu cần.
3. **Faithfulness sụt < 80%:**
   - Kiểm tra xem có chunk lạ / tài liệu mới inject noise vào Qdrant không.
   - Kích hoạt re-evaluation ngay: `company-rag-evaluate --quick --top 50`.
   - Nếu model provider thay đổi (API version bump) → pin lại model version trong `src/providers/`.

#### 🟡 P2: Quality Degradation / Ingestion Chậm
1. **Context Recall < 75%:** Re-index lại collection bị ảnh hưởng; kiểm tra chunking config có thay đổi không.
2. **Ingestion chậm:** Kiểm tra OCR pipeline (nếu tài liệu scan); scale worker hoặc giảm batch size.
3. Mở ticket tracking, fix trong **4 giờ** làm việc.

### Kênh Thông Báo & Công Cụ
- **Phát hiện tự động:** Langfuse Alerts + CI/CD Quality Gate (`.github/workflows/eval.yml`).
- **Log truy vết:** Audit log S3 Object Lock (Level 4) cho các sự cố bảo mật.
- **Post-mortem:** Viết báo cáo sau mọi sự cố P0/P1 trong vòng 24 giờ, lưu vào `docs/incidents/`.

---

## 4.7 Schema Versioning & Data Migration Strategy (Chiến Lược Phiên Bản Hóa & Di Chuyển Dữ Liệu)

Mỗi khi nâng cấp chunking strategy hoặc embedding model, toàn bộ dữ liệu trong Vector DB cần được re-index. Chiến lược này đảm bảo **zero-downtime migration**.

### Quy Tắc Khi Nào Cần Re-index

| Thay đổi | Bắt buộc Re-index? |
|---|---|
| Thay đổi chunking strategy (Fixed → Semantic → Parent-Child) | ✅ Bắt buộc |
| Thay đổi embedding model (ví dụ: đổi dimension từ 768-d → 1536-d) | ✅ Bắt buộc |
| Thêm Contextual Enrichment (HyQA, document summary) vào chunk | ✅ Bắt buộc |
| Thay đổi `chunk_size` / `overlap` | ✅ Bắt buộc |
| Thêm metadata field mới vào payload | ⚠️ Partial (chỉ cần update payload, không re-embed) |
| Cập nhật nội dung tài liệu | ⚠️ Partial (chỉ re-index tài liệu đó) |

### Quy Trình Migration Zero-Downtime (Blue-Green Index)

```
Bước 1: Tạo Qdrant Collection mới với schema mới
        collection_name = "company_rag_v{N+1}"

Bước 2: Chạy ingestion pipeline song song vào collection mới
        (giữ nguyên collection cũ "company_rag_v{N}" đang phục vụ traffic)

Bước 3: Chạy eval song song:
        company-rag-evaluate --collection v{N}   → baseline
        company-rag-evaluate --collection v{N+1} → candidate

Bước 4: Nếu v{N+1} ≥ SLA targets → Switch Traffic:
        Cập nhật config ACTIVE_COLLECTION = "company_rag_v{N+1}"
        (không downtime, chỉ đổi biến môi trường / config)

Bước 5: Giữ collection cũ v{N} thêm 48 giờ → xóa nếu không có rollback.
```

### Schema Version Registry (`src/storage/registry.py`)

Mỗi collection phải lưu metadata phiên bản trong `registry.py`:

```python
SCHEMA_VERSION = {
    "version": "v2",                        # Phiên bản schema
    "embedding_model": "text-embedding-004",
    "embedding_dim": 768,
    "chunk_strategy": "parent_child",       # fixed | semantic | parent_child | raptor
    "chunk_size": 1200,
    "overlap_pct": 0.15,
    "enrichment": ["hyqa", "summary", "contextual"],
    "created_at": "2026-08-05T00:00:00Z",
    "deprecated_at": None                   # Set khi collection bị retire
}
```

### Rollback Plan
- Nếu collection mới kém hơn → đổi `ACTIVE_COLLECTION` về `v{N}` — **< 30 giây**.
- Không xóa collection cũ cho đến khi mới ổn định ≥ 48 giờ.

---

## 4.8 System Rate Limiting, Throttling & Cost Control Strategy (Giới Hạn Tải & Kiểm Soát Chi Phí)

Để bảo vệ tài nguyên hệ thống, chống cạn kiệt ngân sách Token LLM và đảm bảo tính công bằng (Fair Share), hệ thống áp dụng cơ chế giới hạn truy cập đa tầng.

### 1. Thuật Toán & Hạ Tầng Rate Limiting
- **Thuật toán:** **Sliding Window Counter** kết hợp **Leaky Bucket** triển khai trên **Redis** (`redis-py` + Lua Script) đảm bảo tính nguyên tố (atomicity) trên distributed environments.
- **Tầng thực thi:** FastAPI Middleware (`src/api/middleware/rate_limit.py`) hoặc API Gateway (Kong / Traefik).

### 2. Định Ngạch Rate Limit Theo Endpoint & Tier

| Endpoint API | Phân Loại User / Tier | Max Requests / Phút | Daily Token Quota | HTTP Status khi vi phạm |
|---|---|---|---|---|
| `POST /api/v1/query` (1-pass non-agentic) | Standard User | 60 req/min | 500,000 tokens/ngày | `429 Too Many Requests` |
| `POST /api/v1/query` (1-pass non-agentic) | Premium / Enterprise | 300 req/min | 5,000,000 tokens/ngày | `429 Too Many Requests` |
| `POST /api/v1/chat` (Agentic stateful) | Standard User | 15 req/min | 200,000 tokens/ngày | `429 Too Many Requests` |
| `POST /api/v1/chat` (Agentic stateful) | Premium / Enterprise | 60 req/min | 2,000,000 tokens/ngày | `429 Too Many Requests` |
| `POST /api/v1/ingest` (Ingestion Pipeline) | Admin / Data Engineer | 10 req/min | Unlimited | `429 Too Many Requests` |
| Anonymous / Unauthenticated | All Endpoints | 5 req/min | 20,000 tokens/ngày | `401 Unauthorized` / `429` |

### 3. Throttling & Queue Management (Giới Hạn Đồng Thời)
- **Max Concurrent LLM Calls:** Giới hạn tối đa **20 requests đồng thời** tới LLM Provider tại cùng một thời điểm qua `asyncio.Semaphore(20)`.
- **Queue Buffering:** Request thứ 21+ sẽ vào hàng đợi (Queue Wait Time $\le 200\text{ms}$). Nếu Queue vượt quá 50 requests → Trả về `503 Service Unavailable` ngay lập tức để bảo vệ server.

### 4. Cost Guardrails & Alerting
- **Daily Budget Cap:** Cấu hình trần chi phí $N$ USD/ngày cho các API Key external (Gemini/OpenAI).
- **Soft Limit (80% Budget):** Gửi cảnh báo Telegram / Slack Alert tới Team AI khi mức tiêu thụ chạm 80% daily quota.
- **Hard Limit (100% Budget):** Tự động chuyển đổi sang **vLLM Local Serving** hoặc kích hoạt **Abstention Mode** (chỉ trả về cached answers/từ chối sinh câu trả lời mới).

### 5. Response Headers Standard
Tất cả API response đều kèm theo headers chuẩn RFC 6585:
```http
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 42
X-RateLimit-Reset: 1722883600
Retry-After: 18
```

---

## 5. Kết Luận & Đề Xuất Ưu Tiên Triển Khai

### Dependency Chain (bắt buộc tuân theo):
```
Level 1 (Reranker) ──► Level 3 (Self-RAG cần Reranker score)
Level 1 (Chunking) ──► Level 2 (Graph nodes chất lượng hơn)
Level 3 (Agent) ──── Level 4 (Safety bao quanh toàn pipeline Agent)
```

### KPI Baseline Hiện Tại & Mục Tiêu:
| Metric | Baseline (cần đo) | Target Level 1 | Target Level 3 | Target Level 4 |
| --- | --- | --- | --- | --- |
| `Faithfulness` | Đo bằng `company-rag-evaluate` | ≥ +5% | ≥ +10% (Self-RAG) | Ổn định, không regression |
| `Context Recall` | Đo bằng `company-rag-evaluate` | ≥ +15% (Reranker) | ≥ +20% (CRAG) | Ổn định |
| `Precision@5` | Đo bằng `company-rag-evaluate` | ≥ +15% | ≥ +20% | Ổn định |
| `TTFT P95` | Đo bằng Langfuse | - | ≤ +150ms (acceptable) | < 100ms (vLLM) |

### Thứ Tự Ưu Tiên:

1. **Ưu tiên 1 (Ngắn hạn - 1 đến 2 tuần):**
   - Triển khai **Semantic Chunking** + **Parent-Child Chunking** (`src/ingestion/chunker.py`).
   - Triển khai **Cross-Encoder Reranker** + **MMR** (`src/retrieval/hybrid.py`).
   - Thêm **HyDE + Multi-Query Expansion** (`src/retrieval/query_transform.py`).
   - **Đo ngay sau:** `company-rag-evaluate` để có baseline KPI cụ thể trước khi lên Level 3.

2. **Ưu tiên 2 (Trung hạn - 3 đến 4 tuần, sau Level 1):**
   - Xây dựng **LangGraph Agentic RAG** (`src/agent/graph.py`) với Self-RAG + CRAG + Memory.
   - Tích hợp **FastAPI Bridge** (`src/api/routes.py`) — giữ backward compatibility.
   - Đồng thời: Triển khai **Defense-in-Depth L1 & L2** (Spotlighting + PII) cho Level 4.

3. **Ưu tiên 3 (Dài hạn - song song / tùy chọn):**
   - Mở rộng **GraphRAG với Neo4j** (Level 2) khi có câu hỏi multi-hop thực tế.
   - Triển khai **vLLM + Redis Semantic Cache + CI/CD Eval Gate** (Level 4 hoàn chỉnh).
   - Xem xét **Fine-tuning** (Level 5) khi `Context Recall < 0.75` sau Level 1.

---

## 6. Danh Sách Tài Liệu Tham Khảo (References)

Tài liệu lộ trình này được tổng hợp và đối chiếu từ các nguồn thông tin bài giảng trong hệ thống:

### Phase 1: Foundational RAG & Safety
- `day08-rag-pipeline-v3.pdf` - RAG Pipeline & Hybrid Search
- `day11-guardrails-ai-safety.pdf` - Guardrails & AI Safety
- `day13-monitoring-logging-observability_v2.pdf` - Observability Stack
- `day14-ai-evaluation-benchmarking_E403.pdf` - Benchmarking & Evals

### Phase 2 Track 3: Advanced Application & Agentic RAG
- `Day18-production-rag.pdf` - Production RAG & Reranking
- `Day19 GraphRAG and Knowledge Graphs.pdf` - GraphRAG & Knowledge Graphs
- `day20-multi-agent-systems-student.pdf` - Multi-Agent Systems
- `day23_langgraph_student.pdf` - LangGraph Framework
- `day24-ragas-guardrails.pdf` - RAGAS & Guardrails

### Phase 2 Track 2: Infrastructure & Serving
- `Day 19 - Track 2 - Vector store and Feature store_v2.pdf` - Vector & Feature Stores
- `Day 20-model-serving-inference-optimization.pdf` - Model Serving & Inference Optimization
