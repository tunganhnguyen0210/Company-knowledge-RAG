# Tổng Hợp Kiến Thức RAG & AI Systems (RAG Knowledge Handbook)

Tài liệu này tổng hợp toàn bộ kiến thức chuyên sâu về **Retrieval-Augmented Generation (RAG)** và **AI Infrastructure** dựa trên 11 tài liệu tham khảo chính thuộc chương trình đào tạo:

- `day08-rag-pipeline-v3.pdf`
- `day11-guardrails-ai-safety.pdf`
- `day13-monitoring-logging-observability_v2.pdf`
- `day14-ai-evaluation-benchmarking_E403.pdf`
- `Day18-production-rag.pdf`
- `Day19 GraphRAG and Knowledge Graphs.pdf`
- `day20-multi-agent-systems-student.pdf`
- `day23_langgraph_student.pdf`
- `day24-ragas-guardrails.pdf`
- `Day 19 - Track 2 - Vector store and Feature store_v2.pdf`
- `Day 20-model-serving-inference-optimization.pdf`

---

## 1. RAG Architecture & Advanced Chunking Strategies

### 1.1 Baseline RAG Pipeline
* **Offline Ingestion:** `Parse` $\rightarrow$ `Chunk` $\rightarrow$ `Enrich` $\rightarrow$ `Embed` $\rightarrow$ `Index` (Tạo Vector index & Metadata store).
* **Runtime Retrieval:** `Query PreRAG` $\rightarrow$ `Retrieve` $\rightarrow$ `Rerank` $\rightarrow$ `Augment` $\rightarrow$ `Generate` $\rightarrow$ `PostRAG`.

### 1.2 Chunking Strategies từ Cơ Bản Đến Nâng Cao
* **Fixed-size Chunking:** Baseline 512 tokens (overlap 64). Nhược điểm: Dễ cắt ngang câu/ý làm mất ranh giới ngữ cảnh (*lost context boundary*).
* **Semantic Chunking:** Cắt theo ranh giới thay đổi chủ đề bằng cách đo Cosine Similarity giữa câu liên tiếp (ngưỡng $\approx 0.85$).
* **Hierarchical (Parent-Child) Chunking:** Index các đoạn nhỏ (**Child** 256 tokens) để Vector Search đạt Precision cao, nhưng khi sinh câu trả lời thì inject đoạn lớn hơn chứa nó (**Parent** 1024–2048 tokens) vào Prompt để giữ đầy đủ ngữ cảnh.
* **Late Chunking:** Dùng encoder context rộng (như Jina-v3, Nomic) để embed toàn bộ document trước, sau đó mới mean-pool theo ranh giới chunk $\rightarrow$ Vector từng chunk mang đậm ngữ cảnh toàn cục (*global context*).
* **RAPTOR (Recursive Abstractive Processing for Tree-Organized Retrieval):** Gom cụm chunk $\rightarrow$ LLM tóm tắt đệ quy thành cây tri thức. Retrieve linh hoạt theo cấp độ: câu hỏi chi tiết ở nút lá, câu hỏi tổng hợp (*global summary*) ở nút cấp cao.
* **Contextual Embeddings (Anthropic):** Dùng LLM bổ sung 1 câu ngữ cảnh toàn văn bản vào đầu mỗi chunk trước khi embed/BM25 $\rightarrow$ Giảm lỗi retrieval từ 49% đến 67%.
* **Hypothetical Q&A (HyQA):** Sinh các câu hỏi giả định mà chunk có thể trả lời $\rightarrow$ Embed câu hỏi cạnh chunk để thu hẹp khoảng cách từ vựng (*vocab gap*) giữa Query (dạng câu hỏi) và Document (dạng câu khẳng định).
* **Matryoshka Representation Learning (MRL):** Embedding vector lồng nhau (128-d $\rightarrow$ 1536-d). Dùng 128-d lọc thô cực nhanh, dùng full dimension để rerank.

---

## 2. Hybrid Search, Rank Fusion & Reranking

### 2.1 Dense vs Sparse Search
* **Dense Vector (Semantic):** Bi-Encoder (768–1536 dims). Bắt từ đồng nghĩa, ý định ngữ nghĩa. Nhược điểm: Bỏ lỡ từ khóa chính xác (*exact match*) như mã lỗi, tên riêng, số CCCD/ID.
* **Sparse Vector (BM25 / Lexical):** Đếm tần suất từ (TF-IDF / BM25). Match chính xác từ khóa, code, mã tài liệu. Nhược điểm: Vocab mismatch, không hiểu đồng nghĩa.

### 2.2 Rank Fusion Algorithms
* **Reciprocal Rank Fusion (RRF):** Gộp rank độc lập không phụ thuộc vào scale của điểm số:
  $$RRF(d) = \sum_{r \in \text{retrievers}} \frac{1}{k + \text{rank}_r(d)} \quad (k \approx 60)$$
* **Score Fusion (Alpha Weighting):** Normal score về cùng scale $[0, 1]$:
  $$\text{score}(d) = \alpha \cdot s_{\text{dense}} + (1 - \alpha) \cdot s_{\text{sparse}}$$
  * *FAQ / Chatbot chung:* $\alpha = 0.7 - 0.9$
  * *Tài liệu kỹ thuật / Code / Log / Pháp lý:* $\alpha = 0.2 - 0.4$

### 2.3 Advanced Search & Reranking SOTA
* **ColBERT (Late Interaction):** Giữ 1 vector/token. Dùng toán tử `MaxSim` tìm match token-by-token giữa query và doc $\rightarrow$ Giữ được chi tiết token-level exact matching mà tốc độ nhanh hơn Cross-encoder.
* **SPLADE (Learned Sparse):** Dùng Neural Network học trọng số từ và tự động mở rộng từ đồng nghĩa (*term expansion*) vào sparse vector $\rightarrow$ Chạy trên Inverted Index với tốc độ BM25 nhưng có khả năng semantic.
* **ColPali:** Embed trực tiếp ảnh trang document (PDF visual patch embeddings) + Late Interaction với Query text $\rightarrow$ Bỏ qua hoàn toàn pipeline OCR/parsing bị hỏng ở tài liệu phức tạp.
* **Two-Stage Retrieval (Retrieve & Rerank):**
  * *Stage 1:* Search rộng Top 50–100 bằng Bi-encoder/BM25 (nhanh, recall cao).
  * *Stage 2:* Đưa qua Cross-encoder (`bge-reranker-v2-m3`, `Cohere Rerank v3.5`) đọc đồng thời `(Query + Doc)` $\rightarrow$ Chọn Top 3–5 chính xác nhất cho LLM (tăng 15–25% precision, latency +30–50ms).
* **MMR (Maximum Marginal Relevance):** Lọc trùng lặp context, đảm bảo sự đa dạng thông tin:
  $$MMR = \arg\max_{d \in R \setminus S} \left[ \lambda \text{Sim}_1(d, q) - (1-\lambda) \max_{d_j \in S} \text{Sim}_2(d, d_j) \right]$$

---

## 3. GraphRAG & Knowledge Graphs (KG)

### 3.1 Ranh Giới Flat RAG vs GraphRAG
* **Flat RAG (Vector Search đơn thuần):** Thất bại với 3 dạng query:
  1. Multi-hop relational (*"A liên kết với B qua C như thế nào?"*).
  2. Global thematic (*"Tổng quan rủi ro/chủ đề X trong toàn bộ tập tài liệu?"*).
  3. Cross-document reasoning (*Kết nối dữ liệu nằm ở 2 văn bản khác nhau*).
* **GraphRAG:** Biểu diễn dữ liệu dạng Đồ thị tri thức (Knowledge Graph - Directed Labeled Graph): `Node` (Entity), `Edge` (Relation), `Triple` `(Subject, Predicate, Object)`.

### 3.2 Pipeline Xây Dựng Đồ Thị
* **NER & Relation Extraction (RE):** Trích xuất thực thể & mối quan hệ từ raw text bằng LLM/SLM.
* **Coreference Resolution:** Quy chiếu đại từ (*"Ông ấy"*, *"Công ty này"*) về đúng thực thể tên riêng $\rightarrow$ Tránh mất 30–40% liên kết đồ thị.
* **Entity Disambiguation & Deduplication:** Chuẩn hóa biến thể tên (*"OpenAI"*, *"Open AI"*, *"OAI"* $\rightarrow$ 1 Node duy nhất).

### 3.3 Thuật Toán Retrieve Tràn Đồ Thị
* **Standard Graph Traversal:** Query Processing (trích xuất seed entity) $\rightarrow$ Seed Node Matching $\rightarrow$ Traversal BFS (độ sâu $k=2$ hop; $k \ge 3$ gây nhiễu context) $\rightarrow$ Textualization (chuyển subgraph Triples thành prompt text).
* **Microsoft GraphRAG:** Dùng thuật toán **Leiden** phát hiện cộng đồng (*Community Detection*) $\rightarrow$ LLM tóm tắt phân cấp pre-compute $\rightarrow$ **Global Search** đọc báo cáo cộng đồng pre-computed để trả lời câu hỏi tổng quan toàn bộ corpus.
* **LightRAG:** Dual-level retrieval (vector embeddings cho cả Nodes lẫn Edges) $\rightarrow$ Vector search tìm cả nodes và relations cùng lúc, không cần pre-compute community report tốn kém.

---

## 4. Agentic RAG & LangGraph Architecture

### 4.1 5 Agentic Workflow Patterns (Anthropic)
1. **Prompt Chaining:** Chuỗi xử lý tuần tự, validate từng bước.
2. **Routing:** Classify input $\rightarrow$ Điều hướng tới handler chuyên biệt (Query dễ $\rightarrow$ Small model, Query khó $\rightarrow$ Large model $\rightarrow$ Giảm >50% chi phí).
3. **Parallelization:** Sectioning (Map-Reduce song song) hoặc Voting (nhiều LLM chạy rồi tổng hợp).
4. **Orchestrator-Workers (Supervisor):** LLM Supervisor nhận task, phân rã và điều phối các Worker agent qua Shared State.
5. **Evaluator-Optimizer:** Vòng lặp Generate $\rightarrow$ Critique $\rightarrow$ Refine.

### 4.2 Cross-Checking & Debate Agents
* **Debate Pattern (Adversarial Collaboration):** Nhiều agent thuộc các dòng model khác nhau (GPT-4o, Claude, Gemini) tự do trả lời $\rightarrow$ Critique lẫn nhau $\rightarrow$ Judge tổng hợp $\rightarrow$ Giảm hallucination 15–25%.

### 4.3 LangGraph Framework
* **State Machine Orchestration:** Khắc phục nhược điểm của LCEL chain 1 chiều (không loop được, không pause/resume, không crash recovery).
* **Core Components:** `StateGraph`, `TypedState` (TypedDict), `Node` (idempotent, return partial update), `Edge` & `Conditional Edges` (dynamic routing).
* **Reducers:** Quyết định luật merge state (`Overwrite` cho status/route; `Annotated[list, add]` cho append messages/tool_results).
* **Persistence & Checkpointing:** Snapshot state sau mỗi super-step qua `MemorySaver`, `SqliteSaver`, hoặc `PostgresSaver`. Gắn với `thread_id` để phân biệt session.
* **Human-in-the-Loop (HITL):** Dùng `interrupt({action, risk, evidence})` tạm dừng graph trước action nguy hiểm. Resume bằng `compiled.invoke(Command(resume={approved: True}), config)`.
* **Fault Tolerance:** 3 tầng error recovery: Retry (với exponential backoff) $\rightarrow$ Fallback model/tool $\rightarrow$ Dead-letter queue.

---

## 5. Guardrails & AI Safety

### 5.1 Vulnerabilities & OWASP Top 10 for LLM (2025 Updates)
* **Prompt Injection (Direct & Indirect):** Kẻ tấn công đưa lệnh độc hại vào câu hỏi hoặc chèn ngầm trong văn bản RAG.
* **The Lethal Trifecta (Simon Willison):** Sự kết hợp nguy hiểm của 3 yếu tố: **Private Data + Untrusted Content + External Comms** $\rightarrow$ Agent chắc chắn bị rò rỉ dữ liệu nếu không có guardrails tách biệt.

### 5.2 Các Kỹ Thuật Phòng Thủ Modern
* **Spotlighting (Microsoft):** Đánh dấu ranh giới Data vs Instruction bằng Delimiting/Datamarking/Encoding (giảm ASR từ >50% xuống <2%).
* **Instruction Hierarchy (OpenAI):** Quy định độ ưu tiên lệnh cứng: `System` > `User` > `Model` > `Tool`.
* **CaMeL (DeepMind):** Kiến trúc Dual-LLM: Privileged LLM (có tool access, xử lý lệnh tin cậy) vs Quarantined LLM (xử lý untrusted data, KHÔNG có tool access).

### 5.3 Defense-in-Depth Architecture (4 Tầng)
* **L1 Input Layer (<30ms):** Presidio PII redaction (Regex + NER), Prompt Guard (Meta 86M), Topic Scope Validator.
* **L2 LLM Layer (0ms):** System prompt hardening, Instruction hierarchy.
* **L3 Output Layer (<50ms):** Content Safety Classifier (Llama Guard 3 8B), NLI Grounding Check (DeBERTa-v3).
* **L4 Audit Layer (Async):** Log đầy đủ, redact PII, audit trail (Object Lock S3).
* **Latency Budget:** Tổng user-facing overhead $\le 80-100\text{ms}$ P95.

---

## 6. RAG Evaluation & RAGAS Framework

### 6.1 Eval-Driven Development (EDD)
* **Evals = Unit Tests mới cho Agent:** Grade outcomes (trạng thái cuối cùng của hệ thống), read trajectory (xem đường đi của agent để debug).
* **Eval Maturity:** L0 (Vibe-checks) $\rightarrow$ L1 (Error analysis + offline evals) $\rightarrow$ L2 (CI/CD Regression Release Gates).

### 6.2 RAGAS 4 Core Metrics
1. **Faithfulness (Generation):** Tỉ lệ factual claims trong Answer được hỗ trợ bởi Context $\rightarrow$ Đo Hallucination.
2. **Answer Relevancy (Generation):** Sinh ngược $n=3$ câu hỏi từ Answer, đo Cosine similarity với Original Question $\rightarrow$ Đo tính đúng trọng tâm.
3. **Context Precision (Retrieval):** NDCG cho thứ hạng chunk. Chunk chứa info đúng phải xếp ở top đầu.
4. **Context Recall (Retrieval):** Tỉ lệ claims trong Ground Truth được hỗ trợ bởi Retrieved Context $\rightarrow$ Đo độ đầy đủ evidence.

### 6.3 LLM-as-Judge & 4 Core Biases
1. **Position Bias:** Ưu tiên candidate đứng đầu/cuối $\rightarrow$ *Fix:* Swap-and-average `(A,B)` và `(B,A)`.
2. **Length Bias:** Ưu tiên câu trả lời dài $\rightarrow$ *Fix:* Length-controlled eval, length penalty.
3. **Self-Enhancement Bias:** Ưu tiên output cùng họ model $\rightarrow$ *Fix:* Cross-judge protocol.
4. **Style Bias:** Ưu tiên format đẹp $\rightarrow$ *Fix:* Strip formatting trước khi chấm.
* **Human Calibration:** Đo chỉ số **Cohen's Kappa ($\kappa$)** với human labels. Đạt $\kappa \ge 0.60$ mới đủ điều kiện chạy production.

### 6.4 Hallucination Detection
* **SelfCheckGPT:** Sampling $n=5$ responses ($\text{temp}=0.7$). Check tính nhất quán (consistency) giữa các sample.
* **NLI Entailment Check:** Premise (Context) $\leftrightarrow$ Hypothesis (Answer sentence). Contradiction/Neutral $\rightarrow$ Flag.
* **Semantic Entropy (Farquhar 2024 Nature):** Gom cụm các câu trả lời theo nghĩa tương đương (semantic equivalence) rồi tính entropy $\rightarrow$ High semantic entropy = High uncertainty = Hallucination.

---

## 7. Vector Store Indexing & Feature Store

### 7.1 Vector Indexing & Quantization (ANN)
* **HNSW (Hierarchical Navigable Small World):** Graph-based index, recall cao nhất, query nhanh, tốn RAM.
* **IVF (Inverted File Index):** Phân vùng không gian vector thành Voronoi cells qua $k$-means centroids.
* **PQ (Product Quantization):** Nén sub-vectors $\rightarrow$ Tiết kiệm RAM tới $32\times$.
* **IVF-PQ / SQ8:** Kết hợp phân vùng IVF và quantization (Scalar Quantization int8) cho đại quy mô.

### 7.2 Feature Store (MLOps vs LLMOps)
* **Online Store (Low Latency):** Key-Value DB (Redis, DynamoDB) phục vụ real-time inference lookup (<10ms).
* **Offline Store (High Throughput):** Data Lakehouse (Parquet, S3, Snowflake) phục vụ batch training.
* **Point-in-Time Join (As-of Join):** Tránh Data Leakage bằng cách join feature đúng mốc thời gian sự kiện xảy ra trong quá khứ.
* **Training-Serving Skew:** Lệch phân phối/logic tính toán feature giữa pipeline offline training và online serving.

---

## 8. Model Serving & Inference Optimization

### 8.1 Latency Taxonomy & SLA
* **TTFT (Time To First Token):** Thời gian prefill compute + queue wait.
* **TPOT (Time Per Output Token / ITL):** Thời gian sinh từng token tiếp theo.
* **Goodput@SLO:** Số req/s thỏa mãn đồng thời $\text{TTFT} < \text{SLO}_1$ và $\text{TPOT} < \text{SLO}_2$. Metric duy nhất phản ánh năng lực production thực tế.

### 8.2 Quantization Ecosystem
* **FP16/BF16 (16 BPW)** $\rightarrow$ **FP8 (8 BPW, Hopper/Blackwell native, loss <1%)** $\rightarrow$ **AWQ / GPTQ (4-bit, bảo vệ salient weights)** $\rightarrow$ **NVFP4 (4-bit Blackwell native)** $\rightarrow$ **GGUF (K-quants cho CPU/Edge)**.

### 8.3 Attention & Memory Breakthroughs
* **PagedAttention (vLLM):** Quản lý KV Cache theo các trang ký ức ảo (*virtual memory pages*) $\rightarrow$ Loại bỏ 60–80% lãng phí bộ nhớ do phân mảnh, tăng $24\times$ throughput.
* **Prefix Caching (RadixAttention / APC):** Lưu trữ và tái sử dụng cây KV Cache cho system prompt/RAG context $\rightarrow$ Giảm 70–90% TTFT.
* **Attention Evolution:** Multi-Head Attention (MHA) $\rightarrow$ Grouped-Query Attention (GQA) $\rightarrow$ Multi-head Latent Attention (**MLA** - DeepSeek-V3/R1 nén Q/K/V thành latent vector, giảm $10\times$ bộ nhớ KV Cache).
* **FlashAttention 1-4:** Tiling SRAM kernel fusion, giảm I/O bottleneck từ HBM.
* **Speculative Decoding:** Dùng Draft model nhỏ đoán $n$ tokens $\rightarrow$ Target model verify song song trong 1 forward pass.
* **Continuous Batching:** Ghép/nhả request ở mức token (*in-flight*) thay vì static batching.

### 8.4 Parallelism Strategies for Scale
* **Tensor Parallelism (TP):** Chia weights theo chiều ngang/dọc trong từng layer (trong 1 node qua NVLink).
* **Pipeline Parallelism (PP):** Chia layers qua nhiều nodes cho Ultra-Long context.
* **Expert Parallelism (EP):** Phân tán các Experts trong mô hình MoE (DeepSeek-V3 671B).
* **Disaggregated Prefill/Decode:** Tách riêng Cluster chuyên Prefill và Cluster chuyên Decode, truyền KV Cache qua RDMA/NVLink.
* **Multi-LoRA Serving:** Serves hàng trăm LoRA fine-tuned adapters trên 1 Base Model duy nhất.
