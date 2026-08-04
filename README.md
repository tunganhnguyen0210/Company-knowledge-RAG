# Company Knowledge RAG

Dịch vụ RAG cho tài liệu nội bộ, ưu tiên câu trả lời có nguồn và khả năng quan sát. Hệ thống chạy theo mô hình **single-user / open workspace**: API không yêu cầu authentication, mọi tài liệu đã ingest đều truy vấn được. `MAIN_PROVIDER` chọn LLM chính — Gemini, OpenRouter hoặc OpenAI; các provider khác có cấu hình hợp lệ sẽ xử lý lỗi tạm thời. Riêng embeddings luôn chạy trên Gemini, nên `GEMINI_API_KEY` là bắt buộc kể cả khi `MAIN_PROVIDER` không phải Gemini.

## Kiến trúc

```text
Upload/CLI → Parse (md/txt/pdf/docx) → Versioned chunks → Gemini embeddings → Qdrant
                                                                     ↓ status=ready
Client → FastAPI (open) → Dense + BM25 + RRF → Prompt answer_v2 → MAIN_PROVIDER
                            └──────── Langfuse trace ────────┘
```

Các ranh giới chính nằm trong `src/`: `api`, `domain`, `ingestion`, `retrieval`, `providers`, `generation`, `prompts`, `observability`, `evaluation` và `storage`. Chi tiết từng lớp xem [ARCHITECTURE.md](ARCHITECTURE.md) và [docs/architectures/](docs/architectures/).

## Chạy local bằng uv

Yêu cầu: Python 3.11+, [uv](https://docs.astral.sh/uv/) và Qdrant.

```powershell
Copy-Item .env.example .env
# Đặt MAIN_PROVIDER, điền GEMINI_API_KEY (bắt buộc, dùng cho embeddings) và API key của LLM đã chọn
uv sync --locked --group dev --no-group eval
docker compose up -d qdrant
uv run company-rag-serve --reload
```

Swagger: `http://localhost:8000/docs`. `/health` chỉ kiểm tra process và trả về `active_model`; `/ready` kiểm tra kết nối Qdrant rồi gọi model thật bằng một prompt ngắn (`providers/probe.py`), nên nó bắt được cả lỗi credential lẫn lỗi routing model — đổi lại mỗi lần gọi `/ready` tốn một request LLM.

## Nạp tài liệu

Qua CLI:

```powershell
uv run company-rag-ingest .\data\seed
```

CLI chỉ nhận `.md`, `.txt`, `.pdf`, `.docx`; file khác trong thư mục bị bỏ qua. Tài liệu nạp qua CLI luôn mang `allowed_roles={"*"}`.

Qua API:

```bash
curl -X POST http://localhost:8000/v1/documents \
  -F "file=@policy.md;type=text/markdown" \
  -F "allowed_roles=employee,hr" \
  -F 'metadata={"department":"hr"}'
```

Hỗ trợ UTF-8 Markdown, text, PDF và DOCX. DOCX được chuyển sang dạng markdown nhẹ: heading style thành `#`, bảng thành hàng ngăn bằng `|`, để chunker vẫn nhìn thấy section. PDF scan không có text được ghi nhận với trạng thái `needs_ocr`; OCR chưa thuộc phạm vi v1. Upload cùng nội dung là idempotent; nội dung mới của cùng tên nguồn tạo version mới và thay chunks active.

Các endpoint tài liệu khác: `GET /v1/documents/{document_id}` đọc metadata trong registry, `POST /v1/documents/{document_id}/reindex` ingest lại từ file gốc đã lưu trong `data/uploads/` (trả 409 nếu file gốc không còn).

`allowed_roles` vẫn được form upload nhận, lưu trong registry và trong payload Qdrant, nhưng **không còn được dùng để lọc khi truy vấn** — retrieval chỉ lọc `status == "ready"`. Đây là metadata phân loại, không phải ranh giới bảo mật. Bối cảnh và lộ trình quay lại RBAC: [docs/research/authentication-removal-analysis.md](docs/research/authentication-removal-analysis.md).

Đặt `ENABLE_ENRICHMENT=true` để tạo summary, câu hỏi giả định, contextual prefix và metadata bằng một structured call cho mỗi chunk. Mặc định tắt để tránh chi phí ingest ngoài ý muốn; nội dung gốc luôn được giữ riêng cho citation, phần enrich chỉ đi vào `retrieval_text`.

## Embeddings

Embeddings chạy trên Gemini (`EMBEDDING_MODEL`, mặc định `gemini-embedding-001`) và dùng chung key pool với generation. Passage và query dùng hai task type khác nhau (`RETRIEVAL_DOCUMENT` / `RETRIEVAL_QUERY`). Vector Matryoshka bị cắt xuống `EMBEDDING_DIMENSIONS` rồi chuẩn hóa lại trước khi đưa vào cosine search — giá trị này phải khớp với collection Qdrant, đổi một trong hai là phải reindex từ đầu.

Ingest hàng loạt đụng rate limit theo phút và không có router để failover như bên generation, nên embedding provider gửi theo batch 100 text và tự retry tối đa 5 lần. Lỗi transient dùng backoff lũy thừa (1s → 30s); riêng khi mọi key đều đang cooldown vì quota thì nó ngủ đúng bằng `GEMINI_KEY_COOLDOWN_SECONDS` — ngủ ngắn hơn chỉ phí lượt thử vào một pool chưa thể trả lời.

## Provider và xoay vòng Gemini key

`MAIN_PROVIDER` luôn là primary. `ProviderRouter` thử lại primary `PROVIDER_MAX_ATTEMPTS` lần (mặc định 2, backoff 0.1s × 2^n) khi gặp lỗi transient, sau đó mới chuyển sang provider phụ đầu tiên có cấu hình hợp lệ. Lỗi không transient được raise ngay, không phí lượt fallback. `usage` của mỗi response ghi lại `primary_attempts` và `fallback_used`.

Gemini còn có key pool riêng (`providers/gemini_key_pool.py`) dùng chung cho cả generation lẫn embeddings: khai báo `GEMINI_API_KEY`, `GEMINI_API_FALLBACK_KEY`, rồi `GEMINI_API_FALLBACK_KEY2`, `GEMINI_API_FALLBACK_KEY3`… Pool chọn key theo round-robin, và khi một key trả lỗi quota/429 thì key đó bị đặt cooldown `GEMINI_KEY_COOLDOWN_SECONDS` (mặc định 60s) trong khi các key còn lại tiếp tục phục vụ. Key không bao giờ xuất hiện trong log — `GeminiKeyLease` che giá trị trong cả `__repr__` và `__str__`. Xem thêm [docs/references/gemini-key-rotation-pattern.md](docs/references/gemini-key-rotation-pattern.md).

Nếu muốn dùng pool này trong LCEL/LangGraph, `GeminiRotatingRunnable` ([llm_rotation.py](src/providers/llm_rotation.py)) là một `Runnable` thật: pipe được bằng `|`, kế thừa `batch`/`ainvoke`/`with_retry`, và nhận thêm `fallback_factory` cho trường hợp mọi key đều hết quota. Pipeline hiện tại **không** đi qua nó — chat dùng `GeminiProvider` + `ProviderRouter`.

## Structured output

Mọi lời gọi LLM đi qua [instructor](https://github.com/567-labs/instructor): provider trả về Pydantic model đã validate (`GroundedAnswer`, `ChunkEnrichment`, `ProbeResult`) thay vì text tự do, không còn parse JSON bằng regex. instructor chọn cơ chế mạnh nhất cho từng provider — `responseSchema` native của Gemini, tool calling của OpenAI, JSON schema trong prompt cho các backend hỗn hợp của OpenRouter — và reask kèm lỗi validation khi payload sai. `STRUCTURED_MAX_RETRIES` (mặc định `2`) giới hạn số lần reask; hết lượt sẽ raise `ProviderError`, và lỗi này chỉ được đánh dấu transient nếu nguyên nhân gốc là rate limit hay lỗi mạng, còn schema mà model không thỏa được thì coi là vĩnh viễn.

## Hỏi đáp

```bash
curl -X POST http://localhost:8000/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"question":"Nhân viên được nghỉ phép bao nhiêu ngày?"}'
```

Response gồm `answer`, `citations`, thống kê retrieval, `request_id` và cặp `provider`/`model` đã thực sự trả lời. Prompt `answer_v2` (định nghĩa trong [src/prompts/answer_v2.yaml](src/prompts/answer_v2.yaml)) coi context là dữ liệu không tin cậy và yêu cầu mỗi nhận định kèm marker `[C<n>]`.

Citation là cổng chặn cuối cùng: chỉ số nào model trả về mà nằm ngoài khoảng context thực tế sẽ bị loại, và nếu không còn citation hợp lệ nào thì câu trả lời bị thay bằng câu abstention chuẩn — model không thể tự khẳng định điều gì mà không trỏ về đoạn đã được đưa vào prompt.

Retrieval là hybrid: dense search trên Qdrant (lọc bỏ hit dưới `MIN_DENSE_SCORE`) hợp nhất với BM25 in-process bằng Reciprocal Rank Fusion (`k=60`).

## Langfuse và quyền riêng tư

`TRACE_MODE=metadata-only` là mặc định: các trường nội dung (`question`, `answer`, `context`, `parsed_text`, `text`, `system_instruction`, `user_prompt`, `response`) bị lọc đệ quy khỏi payload, chỉ còn request ID, model, latency, số lượng và metadata kỹ thuật. Chế độ `full` bị từ chối ngay khi khởi tạo Settings nếu chưa đặt `ALLOW_SENSITIVE_TRACING=true`.

Pipeline được trace theo span lồng nhau: `ingestion` → `parse` / `chunking` / `enrichment` / `indexing` / `registry` phía nạp tài liệu, và `rag-request` → `retrieval` / `generation` phía hỏi đáp. Span `retrieval` ghi lại top-k kèm score, `chunk_id`, `document_id`, version và section; span `generation` ghi provider, model, token usage và danh sách citation.

Có thể dùng Langfuse Cloud hoặc [self-host Langfuse](https://langfuse.com/self-hosting). Với instance self-host chạy ở cổng 3000:

```bash
docker compose -f docker-compose.yml -f docker-compose.langfuse.yml up -d
```

## Evaluation và chất lượng

```powershell
uv run company-rag-evaluate --dataset evaluation/golden_set.json
uv run pytest
uv run ruff check .
uv run mypy
```

Golden-set đo retrieval hit, groundedness proxy, citation coverage, abstention accuracy và latency; báo cáo chi tiết ghi ra `reports/golden_report.json`. Nhóm `eval` chứa RAGAS cho đánh giá offline mở rộng: `uv sync --group dev --group eval`. Hướng dẫn phương pháp nằm trong [docs/evaluation/](docs/evaluation/).

Metadata v1 dùng JSON registry với khóa đồng bộ trong một process; vì vậy mỗi volume chỉ chạy một API replica. Khi cần nhiều replica hoặc ingest song song qua nhiều service, chuyển registry sang PostgreSQL trước khi scale-out. Nhánh lexical BM25 quét tối đa `LEXICAL_CANDIDATE_LIMIT` chunk từ Qdrant và dựng lại index trong bộ nhớ cho mỗi truy vấn; tăng giới hạn hoặc chuyển sang sparse index native khi corpus lớn.

## Docker Compose

```bash
cp .env.example .env
docker compose up --build -d
curl http://localhost:8000/health
curl http://localhost:8000/ready
```

Compose chỉ bind Qdrant vào `127.0.0.1`; đừng expose ra mạng công cộng ở production. API hiện không có lớp authentication nào, nên nếu triển khai ngoài máy local thì phải đặt sau reverse proxy hoặc mạng nội bộ có kiểm soát. `Principal` và `allowed_roles` vẫn còn trong domain model để lắp lại OIDC/JWT + RBAC khi cần.

## Sự cố thường gặp

- `/ready` trả 503: đọc `detail` trong response — nó chứa nguyên văn lỗi từ provider. Kiểm tra `GEMINI_API_KEY`, API key của `MAIN_PROVIDER`, kết nối Qdrant và `EMBEDDING_DIMENSIONS` khớp với collection.
- Qdrant báo `vector size is N; expected M`: collection đã tạo với số chiều khác `EMBEDDING_DIMENSIONS`. Phải xóa collection và reindex, không sửa được tại chỗ.
- Chat luôn trả câu abstention: hoặc không hit nào vượt `MIN_DENSE_SCORE`, hoặc model không trả citation hợp lệ. Span `retrieval` trong Langfuse cho biết đó là vấn đề nào.
- Upload PDF trả `needs_ocr`: tài liệu là bản scan, cần OCR trước khi reindex.
- Ingest chậm hoặc dừng giữa chừng: Gemini đang rate-limit và embedding provider đang backoff — thêm key vào pool (`GEMINI_API_FALLBACK_KEY…`) là cách rút ngắn hiệu quả nhất.
- OpenRouter không chạy: model phải có trong `OPENROUTER_ALLOWED_MODELS`. Nếu lỗi tạm thời, hệ thống thử provider khác đã được cấu hình.
