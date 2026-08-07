# Level 1 — Chunking Strategy & Enrichment: Handoff Note

> ⚠️ **MỘT PHẦN TÀI LIỆU NÀY ĐÃ LỖI THỜI (2026-08-07).** Xem [`HIERARCHICAL-RETRIEVAL-REPORT.md`](./HIERARCHICAL-RETRIEVAL-REPORT.md).
>
> - **Mục "1. `Chunk.parent_text`" đã bị BÁC BỎ và **đã gỡ khỏi code (2026-08-07)**.** Nó khuyến nghị generation dùng `chunk.parent_text or chunk.text`. Cách đó **không hoạt động**: `score_retrieval_case` chỉ đọc `text` của các SearchHit *được trả về*, nên nhét `parent_text` vào prompt không cải thiện được metric nào. Cách đã triển khai là **trả về sibling chunk** từ trong `store.search()`. `Chunk.parent_text`, `ChunkingConfig.parent_child_enabled/parent_max_chars` và hai biến `CHUNK_PARENT_CHILD_ENABLED`/`CHUNK_PARENT_MAX_CHARS` **đã bị xóa hẳn**.
> - **Mục "Vì sao không có số đo KPI" đã sai.** KPI đã đo đầy đủ: evidence_recall 71.1% → 84.4% trên production. Xem báo cáo mới.
> - Phần **Semantic Chunking, RAPTOR, MRL, Contextual Embeddings** trong tài liệu này vẫn còn hiệu lực — chúng độc lập với hierarchical retrieval và vẫn mặc định TẮT.

> Phạm vi: `src/ingestion/chunker.py`, `src/ingestion/raptor.py` (mới), `src/ingestion/enrichment.py`, `src/ingestion/service.py` (orchestration), additive fields trong `src/domain/schemas.py` và `src/settings.py`.
> Không đụng: `src/retrieval/hybrid.py`, `src/retrieval/qdrant_store.py`, `src/retrieval/query_transform.py` (chưa tồn tại), `src/generation/service.py`.
> Tham chiếu kế hoạch gốc: `docs/references/RAG-ROADMAP-ADVANCED.md` Mục 3 (Cấp Độ 1).

## Những gì đã thay đổi

Tất cả tính năng mới **mặc định TẮT** — hành vi ingest hiện tại giữ nguyên 100% cho tới khi ai đó bật cờ tương ứng trong `.env`. Toàn bộ 211 test hiện có (unit + component) vẫn pass không sửa gì ngoài các test mới thêm cho code mới.

| Tính năng | Cờ bật (`.env`) | Mặc định | File |
|---|---|---|---|
| Semantic Chunking | `CHUNK_SEMANTIC_ENABLED` | `false` | `src/ingestion/chunker.py` |
| ~~Parent-Child Chunking~~ | ~~`CHUNK_PARENT_CHILD_ENABLED`~~ | **đã gỡ 2026-08-07** | — thay bằng sibling expansion trong `src/retrieval/hierarchical.py` |
| RAPTOR Summarization | `RAPTOR_ENABLED` | `false` | `src/ingestion/raptor.py` |
| MRL (truncated vector) | `ENRICH_MRL_ENABLED` | `false` | `src/ingestion/enrichment.py` |

Contextual Embeddings (đã có sẵn) được tăng cường thêm: nếu chunk có `section` (heading), câu context LLM sinh ra sẽ được dẫn bởi heading đó (`"<heading> — <context LLM>"`), không cần cờ riêng vì không thay đổi hành vi khi `section` rỗng (test cũ vẫn pass nguyên).

## Interface bàn giao cho #3 (Reranking/MMR) và #4 (Query Transformation)

### 1. ~~`Chunk.parent_text: str | None`~~ — ĐÃ GỠ (2026-08-07)
Field này, cùng `ChunkingConfig.parent_child_enabled`/`parent_max_chars` và hai biến `.env` `CHUNK_PARENT_CHILD_ENABLED`/`CHUNK_PARENT_MAX_CHARS`, **đã bị xóa khỏi code**. Lý do: không metric nào đọc nó — xem banner đầu tài liệu. Nhu cầu "nạp trọn section vào context" đã được giải quyết bằng **sibling expansion** (`src/retrieval/hierarchical.py`), trả về chunk thật có toạ độ thật nên citable hợp lệ. Payload Qdrant cũ còn key `parent_text` vẫn load được (pydantic bỏ qua field thừa), không cần re-index.

### 2. `Chunk.mrl_vector_128: list[float] | None` — dành cho ai làm two-stage retrieval
Khi `ENRICH_MRL_ENABLED=true`, mỗi chunk có thêm 1 vector rút gọn (mặc định 128-d, đổi qua `ENRICH_MRL_DIMENSIONS`) embed từ `retrieval_text`, dùng cùng model/pool với embedding chính (Jina hỗ trợ `dimensions` param native; Gemini có Matryoshka truncation sẵn — xem `src/api/app.py::_build_embedding_provider`).

**Chưa ai tiêu thụ field này** trong `search()`. Payload đã có sẵn (Qdrant lưu full `Chunk.model_dump()`), chỉ cần: (a) lưu `mrl_vector_128` thành 1 named vector riêng trong Qdrant collection (`vectors_config` dạng dict thay vì single `VectorParams`), (b) ở `QdrantChunkStore.search()`, lọc thô bằng vector 128-d trước, sau đó rerank bằng vector đầy đủ hoặc cross-encoder. Việc này đổi schema Qdrant collection nên nên làm cùng lúc với đợt reranker tuning, không phải việc lặt vặt.

### 3. RAPTOR summary nodes — chunk giả, không phải đoạn tài liệu gốc
RAPTOR tạo thêm `Chunk` "tổng hợp" (không map tới vị trí thật trong tài liệu), nhận diện qua:
```python
from ingestion.raptor import is_raptor_node
is_raptor_node(chunk)  # True nếu chunk.section bắt đầu bằng "__raptor_summary_L"
```
Các node này **có đi qua Qdrant/BM25/reranker bình thường** (không có xử lý đặc biệt ở tầng retrieval) vì chúng vẫn là `Chunk` hợp lệ với `retrieval_text` set. Điều #3/#4 nên biết:
- Nếu #3 (reranker/MMR) thấy candidate có `section` dạng `__raptor_summary_L*`, đó là summary tổng hợp nhiều điều khoản — không có `coordinates.article` cụ thể đáng tin cậy (dùng tọa độ của chunk đầu cụm, chỉ mang tính tham khảo). Có thể cân nhắc trọng số khác cho loại node này khi tune MMR.
- Nếu #4 (query transform) làm Multi-Query/HyDE cho câu hỏi tổng hợp/toàn cục, RAPTOR node chính là mục tiêu nhắm tới — không cần code gì thêm, chỉ cần biết field này tồn tại khi debug kết quả retrieval.
- Citation ở `generation/service.py` hiện dùng `chunk.text[:300]` làm excerpt — với RAPTOR node, `chunk.text` là văn bản tóm tắt (không phải trích dẫn nguyên văn); nếu thấy citation "lạ" khi review, đây là nguyên nhân khả dĩ.

## Vì sao không có số đo KPI đính kèm ở đây

Theo kế hoạch, toàn bộ dev/test phải chạy trên **collection Qdrant riêng** (Blue-Green), không đụng `company_knowledge` đang phục vụ #3/#4. Trong phiên làm việc này, môi trường sandbox không có Docker/Qdrant chạy sẵn (`docker ps` báo daemon không truy cập được) và cũng không có API key thật để gọi Jina/Gemini — nên **không thể tạo báo cáo `report.json` thật** để so với baseline `reports/rag_evaluation/2026-08-06_golden100_clean-baseline/`. Toàn bộ code đã được xác minh qua 211 unit/component test (mock/stub, không cần hạ tầng thật) + ruff + mypy sạch.

### Cách đo thật (chạy trong môi trường có Qdrant + API key)

```bash
# 1. Bật các cờ muốn thử nghiệm trong .env, ví dụ:
#    CHUNK_SEMANTIC_ENABLED=true
#    RAPTOR_ENABLED=true
#    ENRICH_MRL_ENABLED=true
#    ENABLE_ENRICHMENT=true   (bắt buộc để enrichment chạy)

# 2. Trỏ sang collection dev riêng (không đụng company_knowledge)
export QDRANT_COLLECTION=company_rag_chunking_dev   # PowerShell: $env:QDRANT_COLLECTION="company_rag_chunking_dev"

# 3. Re-ingest toàn bộ corpus vào collection dev
company-rag-ingest data/corpus/   # hoặc thư mục chứa golden-set source documents

# 4. Chạy lại golden set eval, so với baseline gốc
rag-eval e2e --output-root reports/rag_evaluation
# so sánh report.json mới với reports/rag_evaluation/2026-08-06_golden100_clean-baseline/report.json
```

Lặp lại bước 1–4 cho từng tổ hợp cờ (semantic riêng, +parent-child, +raptor, +MRL) để tách bạch đóng góp của từng phần, theo đúng trình tự Phase 1 (Chunking) → Phase 2 (Enrichment) đã chốt. Chỉ khi số liệu trên collection dev đạt DoD (Precision@5 proxy tăng, latency P95 không tăng quá 150ms) mới đề xuất switch `QDRANT_COLLECTION`/`ACTIVE_COLLECTION` sang bản mới — và cần báo trước cho #3/#4 để họ re-tune trên chunk boundary mới, theo quy trình Blue-Green ở Mục 4.7 roadmap.
