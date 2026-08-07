# Kế Hoạch Triển Khai: Level 1 — Advanced Retrieval & Context Engineering

> **Nguồn gốc:** `docs/references/RAG-ROADMAP-ADVANCED.md` — Cấp Độ 1
> **Thời gian ước tính:** 1–2 tuần
> **Baseline:** `reports/rag_evaluation/2026-08-06_golden100_clean-baseline/report.json`
> **Metric yếu nhất:** `hard` coordinate_recall 56.4% | `ambiguous` evidence_recall 59.2%

---

## Phân Công & Dependency

```
Phase 1 (Chunking)          ← Người khác
  └─► [Coordination Point: thông báo khi re-index v2 xong]
        └─► Phase 2 (Enrichment)   ← Bạn — làm trước
              └─► [Re-index Blue-Green nếu Phase 1 chưa xong, hoặc gộp chung]
                    └─► Phase 3 (Reranker + MMR)   ← Bạn
                          └─► Phase 4 (Query Transform)   ← Bạn
```

**Thứ tự thực tế của bạn:** Phase 2 → Phase 3 → Phase 4 (Phase 1 không chặn Phase 3 & 4)

> **Lưu ý quan trọng:** Phase 3 & 4 **không cần re-index** → có thể bắt đầu ngay trên
> collection hiện tại (`company_knowledge`) trong khi Phase 1 & 2 đang chạy song song.

---

## Ràng Buộc Kiến Trúc Thực Tế (từ code analysis)

| File | Hiện trạng cần biết |
|---|---|
| [`src/api/app.py:47`](../../src/api/app.py#L47) | `ChatService` khởi tạo: `ChatService(store, provider, tracer, settings.retrieval_limit)` |
| [`src/api/app.py:204`](../../src/api/app.py#L204) | `_build_qdrant_store()` — nơi thêm `enable_mmr`, `mmr_lambda` khi khởi tạo store |
| [`src/api/app.py:44`](../../src/api/app.py#L44) | `enricher = LLMChunkEnricher(provider) if settings.enable_enrichment else None` |
| [`src/ingestion/service.py:19`](../../src/ingestion/service.py#L19) | `CHUNK_MAX_CHARS = 1200` hardcode — cần move vào settings cho Phase 1 |
| [`src/providers/base.py:42`](../../src/providers/base.py#L42) | `GenerationProvider.generate(request) -> GenerationResult` có `.text: str` — dùng cho QueryTransformer |
| [`src/domain/schemas.py:51`](../../src/domain/schemas.py#L51) | `SearchHit` chỉ có `chunk: Chunk` + `score: float` — không có embedding vector |
| [`src/retrieval/qdrant_store.py:180`](../../src/retrieval/qdrant_store.py#L180) | Reranker đã có sẵn, activate bằng `RERANKER_MODEL=jina-reranker-v3.5` trong `.env` |

**Dependencies chưa có trong `pyproject.toml`:**
```
numpy       ← cần cho MMR cosine similarity (Task 3.2)
scikit-learn ← cần cho RAPTOR KMeans clustering (Task 1.3, người khác làm)
```

**Corpus hiện tại:** 1 docx + 5 md files trong `data/raw`. Nhỏ → RAPTOR ít cần thiết ngay;
LLM call cho enrichment không tốn kém nhưng vẫn mặc định tắt theo nguyên tắc tiết kiệm.

---

## Phase 1 — Nâng Cấp Chunking Strategies (Người khác thực hiện)

> **Owner:** Không phải bạn. Ghi lại để tracking coordination.

### Task 1.1 — Semantic Chunking (`src/ingestion/chunker.py`)

**⚠️ Vấn đề kiến trúc phải giải quyết (thông báo cho người thực hiện):**
`IngestionService` hiện không có `embedder` — chỉ `QdrantChunkStore` mới có.
Semantic Chunking cần embed từng câu để tính Cosine Similarity.

Hai cách giải quyết:
- **Cách A (đơn giản hơn):** Truyền `embedder` vào `IngestionService.__init__()` và `_build_qdrant_store()` return embedder riêng cho ingestion pipeline.
- **Cách B:** Dùng sentence-transformers local (không cần API call, không tốn key Jina).

Settings cần thêm:
```python
chunk_strategy: str = "fixed"           # "fixed" | "semantic" | "parent_child"
semantic_similarity_threshold: float = 0.85
```

### Task 1.2 — Parent-Child Chunking (`src/ingestion/chunker.py`)

Thêm vào `Chunk` schema (`domain/schemas.py`):
```python
parent_id: str | None = None
chunk_type: str = "standalone"    # "standalone" | "child" | "parent"
```

Settings cần thêm:
```python
child_chunk_chars: int = 400
parent_chunk_chars: int = 1500
```

### Task 1.3 — RAPTOR (`src/ingestion/raptor.py`)

**Độ ưu tiên thấp** cho corpus hiện tại (1 docx + 5 md). Enable khi corpus > 50 tài liệu.

Dependencies phải thêm trước: `uv add scikit-learn`

Settings:
```python
enable_raptor: bool = False    # Giữ tắt với corpus nhỏ hiện tại
raptor_depth: int = 1
raptor_cluster_size: int = 5
```

### Coordination Point — Phase 1 → Phase 2

Khi Phase 1 xong:
1. Thông báo schema `Chunk` có thay đổi không (`parent_id`, `chunk_type`).
2. Xác nhận collection name mới (ví dụ `company_knowledge_v2`) để Phase 2 re-index cùng.
3. Nếu Phase 2 xong trước Phase 1: re-index riêng lên `company_knowledge_v2`, sau khi Phase 1 xong thì re-index lại lần nữa (gộp cả hai) lên `company_knowledge_v3`.

---

## Phase 2 — Nâng Cấp Enrichment (Bạn thực hiện — Ưu tiên cao nhất)

**Mục tiêu:** Tăng `evidence_recall` nhóm `ambiguous` (hiện 59.2%) bằng cách enrichment
thêm ngữ cảnh định vị chunk trong toàn bộ tài liệu trước khi embed.

**File chính:** `src/ingestion/enrichment.py`

**Yêu cầu re-index:** Có — `retrieval_text` thay đổi → vector khác.

**LLM budget:** Tiết kiệm — mặc định `enable_enrichment=False`. Chỉ bật khi ingest tài liệu mới.
Với corpus hiện tại (6 tài liệu nhỏ), chi phí không đáng kể.

---

### Task 2.1 — Contextual Embeddings (Anthropic Pattern)
**Ước tính:** 4 giờ

**Hiện trạng `enrichment.py` dòng 61:**
```python
retrieval_text = f"{enrichment.context}\n\n{chunk.text}" if enrichment.context else chunk.text
```
`context` hiện là mô tả chung của chunk, chưa định vị chunk trong toàn bộ document.

**Thêm field `situational_context` vào `ChunkEnrichment` Pydantic schema:**
```python
situational_context: str = Field(
    description=(
        "1-2 câu định vị chunk trong toàn bộ tài liệu: "
        "tên văn bản, số hiệu văn bản (nếu có), chương/điều/mục, "
        "chủ đề chính của đoạn này trong bối cảnh toàn tài liệu."
    )
)
```

**Sửa `LLMChunkEnricher.enrich()` dòng 61:**
```python
retrieval_text = (
    f"{enrichment.situational_context}\n\n"
    f"{enrichment.context}\n\n"
    f"{chunk.text}"
)
```

**Kỳ vọng:** Giảm vocab gap cho query ngắn/mơ hồ (nhóm `ambiguous`) vì vector của chunk
mang thêm thông tin "đây là Điều X của Nghị định Y về chủ đề Z".

**Unit tests** (`tests/unit/test_enrichment_contextual.py`):

| Test | Assert | Mark |
|---|---|---|
| `test_situational_context_prepended` | `retrieval_text` bắt đầu bằng `situational_context` | `@pytest.mark.unit` |
| `test_enrichment_idempotent` | Enrich 2 lần → output giống nhau | `@pytest.mark.unit` |
| `test_retrieval_text_contains_all_parts` | `retrieval_text` có đủ: situational + context + chunk.text | `@pytest.mark.unit` |

---

### Task 2.2 — MRL (Matryoshka Representation Learning)
**Ước tính:** 4 giờ

**Ngữ cảnh:** `jina-embeddings-v5-omni-small` hỗ trợ MRL natively qua tham số `dimensions`.
Qdrant hiện dùng 1024-d (`vector_size=1024` trong `settings.py:73`).

**Thiết kế (không cần thay đổi index):**
- Stage 1 Dense Search: request Jina embed ở 128-d → search nhanh → Top 200.
- Stage 2 Re-score: request Jina embed ở 1024-d → cosine re-score Top 200 → Top 50 cho Reranker.

**Thay đổi `JinaEmbeddingProvider` trong `src/providers/jina.py`:**
Thêm optional param `output_dimension` (đã có trong khởi tạo tại `app.py:210`) →
kiểm tra xem JinaEmbeddingProvider đã hỗ trợ truncated dimension chưa, nếu chưa thì thêm.

**Thay đổi `QdrantChunkStore.search()` trong `qdrant_store.py`:**
```python
if self.enable_mrl:
    # Stage 1: fast filter với 128-d
    fast_embedding = self.embedder.embed_query_dim(query, dim=128)
    fast_candidates = self.client.query_points(..., query=fast_embedding, limit=mrl_fast_candidate_limit)
    # Stage 2: precise re-score với 1024-d
    full_embedding = self.embedder.embed_query(query)  # full dim
    # cosine re-score fast_candidates với full_embedding
    # → Top rerank_candidate_limit → tiếp tục RRF + Reranker
```

**Settings mới:**
```python
enable_mrl: bool = False
mrl_fast_dim: int = 128
mrl_full_dim: int = 1024          # = vector_size
mrl_fast_candidate_limit: int = 200
```

**Thêm vào `_build_qdrant_store()` trong `app.py`:**
```python
return QdrantChunkStore(
    ...
    enable_mrl=settings.enable_mrl,
    mrl_fast_dim=settings.mrl_fast_dim,
    mrl_fast_candidate_limit=settings.mrl_fast_candidate_limit,
)
```

**Unit tests** (`tests/unit/test_mrl.py`):

| Test | Assert | Mark |
|---|---|---|
| `test_mrl_fast_dim_is_prefix` | 128-d vector = 128 phần tử đầu của 1024-d | `@pytest.mark.unit` |
| `test_mrl_expands_candidate_pool` | Khi `enable_mrl=True`, pool trước Reranker lớn hơn | `@pytest.mark.unit` |

---

### Checkpoint Phase 2 — Re-index & Eval

**Lệnh re-index thực tế** (từ `cli.py:27`):
```bash
# Re-index từng tài liệu trong thư mục data
QDRANT_COLLECTION=company_knowledge_v2 company-rag-ingest data/raw

# Eval trên collection mới
QDRANT_COLLECTION=company_knowledge_v2 rag-eval e2e
```
→ **Delta Checkpoint #1** (Contextual Embeddings + MRL)

Nếu `coordinate_recall` nhóm `ambiguous` chưa cải thiện → kiểm tra `situational_context`
có được generated đúng không bằng cách in `chunk.retrieval_text` của 1 chunk bất kỳ.

---

## Phase 3 — Two-Stage Retrieval & MMR (Bạn thực hiện)

**Không yêu cầu re-index.** Có thể bắt đầu ngay, song song với Phase 1 & 2.

---

### Task 3.1 — Bật Cross-Encoder Reranker
**Loại:** Config only, zero code
**Ước tính:** 15 phút

```bash
# .env
RERANKER_MODEL=jina-reranker-v3.5
```

Reranker code đã có sẵn, được activate tại [`app.py:221-227`](../../src/api/app.py#L221):
```python
reranker = None
if jina_pool.key_count > 0 and settings.reranker_model:
    reranker = JinaReranker(api_key=jina_pool, model=settings.reranker_model, ...)
```

```bash
rag-eval e2e
```
→ **Delta Checkpoint #2** (Reranker ON)

**Rollback:** Latency overhead > 200ms P95 → xóa `RERANKER_MODEL` khỏi `.env`.

---

### Task 3.2 — Implement MMR trong `src/retrieval/hybrid.py`
**Ước tính:** 3 giờ

**Dependency mới cần thêm trước:**
```bash
uv add numpy
```

**Vấn đề thiết kế:**
`SearchHit` không có vector (chỉ `score: float`) → nhận thêm `chunk_vectors: dict[str, list[float]]` từ caller.
`QdrantChunkStore` cung cấp bằng cách request `with_vectors=True` trong Dense search step.
Fallback khi không có vector: dùng `max(score của selected)` làm proxy cho redundancy.

**Function signature:**
```python
def maximal_marginal_relevance(
    hits: list[SearchHit],
    chunk_vectors: dict[str, list[float]],   # chunk.id -> dense vector từ Qdrant
    lambda_param: float = 0.7,
    top_n: int = 5,
) -> list[SearchHit]:
    """
    MMR = argmax_{d in R\S} [lambda * Sim1(d,q) - (1-lambda) * max_{dj in S} Sim2(d,dj)]
    Sim1 = hit.score (Reranker score nếu có, RRF score nếu không)
    Sim2 = cosine(chunk_vectors[d], chunk_vectors[dj])
    """
```

**Unit tests** (`tests/unit/test_hybrid_mmr.py`):

| Test | Assert | Mark |
|---|---|---|
| `test_mmr_removes_near_duplicate` | 2 chunk vector gần nhau (cosine > 0.95) → chỉ 1 được chọn | `@pytest.mark.unit` |
| `test_mmr_fallback_no_vectors` | `chunk_vectors={}` → không crash, trả về theo score | `@pytest.mark.unit` |
| `test_mmr_returns_exact_top_n` | Không trả về nhiều hơn `top_n` | `@pytest.mark.unit` |
| `test_mmr_lambda_0_max_diversity` | `lambda=0` → chọn các chunk khác nhau nhất | `@pytest.mark.unit` |
| `test_mmr_lambda_1_max_relevance` | `lambda=1` → tương đương sort by score descending | `@pytest.mark.unit` |

---

### Task 3.3 — Tích hợp MMR vào `QdrantChunkStore.search()`
**Ước tính:** 2 giờ
**File thay đổi:** `src/retrieval/qdrant_store.py`, `src/settings.py`, `src/api/app.py`

**Thay đổi `qdrant_store.py`:**

1. Thêm vào `__init__()`:
```python
enable_mmr: bool = False
mmr_lambda: float = 0.7
```

2. Sửa `client.query_points()` trong `search()`: thêm `with_vectors=True`.

3. Build `chunk_vectors` map sau Dense search:
```python
# chunk.id là str lưu trong payload field "id"
# Kiểm tra _chunk_payload() — field "id" = chunk.id
chunk_vectors: dict[str, list[float]] = {
    point.payload.get("id", ""): list(point.vector)
    for point in dense_response.points
    if point.vector is not None
}
```

4. Sau Reranker hoặc RRF:
```python
if self.enable_mmr and len(candidates) > limit:
    from retrieval.hybrid import maximal_marginal_relevance
    return maximal_marginal_relevance(
        candidates, chunk_vectors,
        lambda_param=self.mmr_lambda,
        top_n=limit,
    )
```

**Thêm vào `src/settings.py`:**
```python
enable_mmr: bool = False
mmr_lambda: float = 0.7
```

**Sửa `_build_qdrant_store()` trong `src/api/app.py`** — thêm vào `QdrantChunkStore(...)`:
```python
enable_mmr=settings.enable_mmr,
mmr_lambda=settings.mmr_lambda,
```

```bash
# Bật và đo
# .env: ENABLE_MMR=true
rag-eval e2e
```
→ **Delta Checkpoint #3** (Reranker + MMR)

---

## Phase 4 — Query Transformation Layer (Bạn thực hiện)

**Không yêu cầu re-index.**

---

### Quyết Định Kiến Trúc

**Vấn đề HyDE:** `store.search(query: str)` là black-box nhận 1 string cho cả Dense + BM25.
HyDE cần tách: Dense embed hypothetical doc, BM25 vẫn dùng raw query.

**Giải pháp: Transform tại `ChatService.retrieve()` trong `service.py`**

- `self.provider` (có `.generate()`) đã có → không inject thêm.
- `store.search()` không đổi interface → backward compatible.
- HyDE: 2 lần `store.search()` (raw + HyDE doc) → merge RRF.
- Multi-Query: N lần `store.search()` → de-duplicate → sort.

**Benchmark cả 2 mode** trước khi quyết định mặc định nào tốt hơn cho corpus pháp lý.

---

### Task 4.1 — Tạo `src/retrieval/query_transform.py`
**Ước tính:** 3 giờ

```python
from __future__ import annotations
from providers.base import GenerationProvider, GenerationRequest


HYDE_SYSTEM = (
    "Bạn là chuyên gia pháp lý Việt Nam. "
    "Viết 1 đoạn văn ngắn (3-5 câu) trả lời trực tiếp câu hỏi sau "
    "như thể đang trích dẫn từ một văn bản pháp lý chính thức. "
    "Chỉ trả về đoạn văn, không giải thích thêm."
)

MULTI_QUERY_SYSTEM = (
    "Sinh {n} cách diễn đạt khác nhau cho câu hỏi pháp lý sau. "
    "Mỗi cách trên một dòng, không đánh số. "
    "Giữ nguyên ý định gốc, thay đổi từ ngữ và cấu trúc câu."
)


class QueryTransformer:
    """Stateless — không giữ state, thread-safe."""

    def hyde(self, query: str, provider: GenerationProvider) -> str:
        """
        Trả về hypothetical document text để embed cho Dense search.
        BM25 và Reranker vẫn dùng raw query — caller chịu trách nhiệm tách.
        Fallback: LLM fail hoặc trả chuỗi rỗng → trả về raw query.
        """
        try:
            result = provider.generate(
                GenerationRequest(
                    system_instruction=HYDE_SYSTEM,
                    user_prompt=query,
                    temperature=0.3,
                    max_output_tokens=300,
                )
            )
            return result.text.strip() or query
        except Exception:
            return query

    def expand(
        self,
        query: str,
        provider: GenerationProvider,
        n: int = 3,
    ) -> list[str]:
        """
        Trả về [raw_query] + n paraphrases.
        raw_query luôn ở index 0 — là fallback khi LLM fail.
        """
        try:
            result = provider.generate(
                GenerationRequest(
                    system_instruction=MULTI_QUERY_SYSTEM.format(n=n),
                    user_prompt=query,
                    temperature=0.5,
                    max_output_tokens=400,
                )
            )
            paraphrases = [
                line.strip()
                for line in result.text.strip().splitlines()
                if line.strip() and line.strip() != query
            ][:n]
            return [query] + paraphrases
        except Exception:
            return [query]
```

**Unit tests** (`tests/unit/test_query_transform.py`):

| Test | Assert | Mark |
|---|---|---|
| `test_expand_raw_query_always_first` | `result[0] == query` luôn luôn | `@pytest.mark.unit` |
| `test_expand_fallback_provider_error` | Provider raise → trả `[query]` | `@pytest.mark.unit` |
| `test_expand_max_n_items` | `len(result) <= n + 1` | `@pytest.mark.unit` |
| `test_hyde_fallback_empty_response` | LLM trả `""` → trả `query` | `@pytest.mark.unit` |
| `test_hyde_fallback_provider_error` | Provider raise → trả `query` | `@pytest.mark.unit` |

---

### Task 4.2 — Cập nhật `ChatService` trong `service.py`
**Ước tính:** 2 giờ

**Sửa `__init__()` — thêm 2 tham số:**
```python
from retrieval.query_transform import QueryTransformer

def __init__(
    self,
    store: ChunkStore,
    provider: GenerationProvider,
    tracer: Tracer,
    retrieval_limit: int = 5,
    query_transformer: QueryTransformer | None = None,   # NEW
    query_transform_mode: str = "none",                  # NEW
) -> None:
    ...
    self.query_transformer = query_transformer
    self.query_transform_mode = query_transform_mode
```

**Sửa `retrieve()` — thêm transform block TRƯỚC dòng 83 (`self.store.search`):**
```python
hits: list[SearchHit]
mode = self.query_transform_mode

if self.query_transformer and mode == "multi_query":
    queries = self.query_transformer.expand(question, self.provider, n=settings.multi_query_n)
    candidate_limit = self.retrieval_limit * len(queries) * 2
    all_hits: list[SearchHit] = []
    for q in queries:
        all_hits.extend(self.store.search(q, limit=candidate_limit))
    seen: dict[str, SearchHit] = {}
    for hit in all_hits:
        if hit.chunk.id not in seen or hit.score > seen[hit.chunk.id].score:
            seen[hit.chunk.id] = hit
    hits = sorted(seen.values(), key=lambda h: -h.score)[:self.retrieval_limit]

elif self.query_transformer and mode == "hyde":
    hyde_doc = self.query_transformer.hyde(question, self.provider)
    hits_raw  = self.store.search(question, limit=self.retrieval_limit * 2)
    hits_hyde = self.store.search(hyde_doc,  limit=self.retrieval_limit * 2)
    from retrieval.hybrid import reciprocal_rank_fusion
    hits = reciprocal_rank_fusion(hits_raw, hits_hyde, limit=self.retrieval_limit)

else:
    hits = self.store.search(question, limit=self.retrieval_limit)
```

**Thêm vào `src/settings.py`:**
```python
query_transform_mode: str = "none"   # "none" | "hyde" | "multi_query"
multi_query_n: int = 3
```

---

### Task 4.3 — Wire-up vào `src/api/app.py`
**Ước tính:** 30 phút
**File:** [`src/api/app.py:47`](../../src/api/app.py#L47)

**Sửa dòng 47** (khởi tạo `ChatService`):
```python
# Trước:
chat = ChatService(store, provider, tracer, settings.retrieval_limit)

# Sau:
from retrieval.query_transform import QueryTransformer

query_transformer = (
    QueryTransformer() if settings.query_transform_mode != "none" else None
)
chat = ChatService(
    store,
    provider,
    tracer,
    settings.retrieval_limit,
    query_transformer=query_transformer,
    query_transform_mode=settings.query_transform_mode,
)
```

**Benchmark cả 2 mode:**
```bash
# Benchmark Multi-Query
QUERY_TRANSFORM_MODE=multi_query rag-eval e2e
# → Delta Checkpoint #4-A

# Benchmark HyDE
QUERY_TRANSFORM_MODE=hyde rag-eval e2e
# → Delta Checkpoint #4-B

# So sánh #4-A vs #4-B → chọn mode tốt hơn làm mặc định
```

---

## Tổng Hợp Checkpoints & Thứ Tự Thực Hiện

```
[Có thể bắt đầu ngay]
Task 3.1  →  rag-eval e2e  →  Delta #2 (Reranker ON)
Task 3.2  →  unit tests  →  (chờ Task 3.3)
Task 3.3  →  rag-eval e2e  →  Delta #3 (Reranker + MMR)

[Song song hoặc trước]
Task 2.1  →  unit tests  →  re-index  →  rag-eval e2e  →  Delta #1 (Contextual Embed)
Task 2.2  →  unit tests  →  (bật sau khi có Delta #1)

[Sau Phase 3 ổn định]
Task 4.1  →  unit tests
Task 4.2-4.3  →  rag-eval e2e (multi_query)  →  Delta #4-A
              →  rag-eval e2e (hyde)         →  Delta #4-B
              →  chọn mode tốt hơn làm mặc định
```

| Delta | Sau task | Config | Metric kỳ vọng tăng |
|---|---|---|---|
| #1 | Task 2.1 | re-index với `situational_context` | `ambiguous` evidence_recall 59.2% → ≥68% |
| #2 | Task 3.1 | `RERANKER_MODEL=jina-reranker-v3.5` | `coordinate_recall` overall 81.6% → ≥88% |
| #3 | Task 3.3 | `ENABLE_MMR=true` | `adversarial` citation_coverage 72.5% → ≥80% |
| #4-A | Task 4.3 | `QUERY_TRANSFORM_MODE=multi_query` | `hard` coordinate_recall 56.4% → ≥65% |
| #4-B | Task 4.3 | `QUERY_TRANSFORM_MODE=hyde` | `ambiguous` groups (benchmark để so sánh) |

---

## Rollback Conditions

| Tình huống | Hành động |
|---|---|
| Reranker latency > 200ms P95 | Xóa `RERANKER_MODEL` khỏi `.env` |
| MMR latency > 50ms P95 | `ENABLE_MMR=false` |
| `with_vectors=True` gây memory spike | Tắt MMR, fetch vector on-demand thay thế |
| Multi-Query latency > 500ms P95 | Giảm `MULTI_QUERY_N=2` hoặc tắt `QUERY_TRANSFORM_MODE=none` |
| Delta #1 kém hơn baseline | Kiểm tra `retrieval_text` của chunk, debug prompt `situational_context` |

---

## Files Thay Đổi (Bạn phụ trách)

| File | Loại | Task |
|---|---|---|
| `src/ingestion/enrichment.py` | Thêm `situational_context` vào `ChunkEnrichment` | 2.1 |
| `src/retrieval/hybrid.py` | Thêm `maximal_marginal_relevance()` | 3.2 |
| `src/retrieval/qdrant_store.py` | `with_vectors=True`, `enable_mmr`, `mmr_lambda`, MRL | 2.2, 3.3 |
| `src/retrieval/query_transform.py` | **TẠO MỚI** — `QueryTransformer` | 4.1 |
| `src/generation/service.py` | Sửa `__init__` + `retrieve()` | 4.2 |
| `src/api/app.py` | Wire-up `QueryTransformer` (dòng 47), `enable_mmr` (dòng 229) | 3.3, 4.3 |
| `src/settings.py` | `enable_mmr`, `mmr_lambda`, `enable_mrl`, `query_transform_mode`, `multi_query_n` | Tất cả |
| `.env` | `RERANKER_MODEL=jina-reranker-v3.5` | 3.1 |
| `pyproject.toml` | `uv add numpy` | 3.2 |
| `tests/unit/test_enrichment_contextual.py` | **TẠO MỚI** — 3 tests | 2.1 |
| `tests/unit/test_mrl.py` | **TẠO MỚI** — 2 tests | 2.2 |
| `tests/unit/test_hybrid_mmr.py` | **TẠO MỚI** — 5 tests | 3.2 |
| `tests/unit/test_query_transform.py` | **TẠO MỚI** — 5 tests | 4.1 |

---

## Definition of Done — Level 1 (Phần của bạn)

- [ ] `uv add numpy` đã được thêm vào `pyproject.toml`
- [ ] Tất cả 15 unit tests (tasks 2.1, 2.2, 3.2, 4.1) pass với `pytest tests/unit/ -m unit`
- [ ] Delta #2 (Reranker): `coordinate_recall` overall ≥ 88% (hiện 81.6%)
- [ ] Delta #1 (Contextual Embed): `evidence_recall` nhóm `ambiguous` ≥ 68% (hiện 59.2%)
- [ ] Delta #3 (MMR): latency overhead ≤ 50ms P95, không regression trên metric khác
- [ ] Delta #4-A vs #4-B: benchmark xong, chọn được mode mặc định
- [ ] `POST /v1/chat` backward compatible khi tất cả flags = off/none
- [ ] `rag-eval e2e` Precision@5 tổng tăng ≥ 15% so với baseline gốc (SLA §4.5)
