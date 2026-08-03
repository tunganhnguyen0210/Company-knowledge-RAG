# Company Knowledge RAG

Dịch vụ RAG cho tài liệu nội bộ công ty, ưu tiên kiểm soát truy cập, câu trả lời có nguồn và khả năng quan sát. Gemini là provider chính; OpenRouter chỉ được dùng làm fallback cho lỗi tạm thời.

## Kiến trúc

```text
Upload/CLI → Parse → Versioned chunks → Gemini embeddings → Qdrant
                                                     ↓ ACL filter
Client → FastAPI/API key → Dense + BM25 + RRF → Prompt answer_v1 → Gemini/OpenRouter
                            └──────── Langfuse trace ────────┘
```

Các ranh giới chính nằm trong `src/company_knowledge_rag`: `api`, `domain`, `ingestion`, `retrieval`, `providers`, `generation`, `prompts`, `observability`, `evaluation` và `storage`.

## Chạy local bằng uv

Yêu cầu: Python 3.11+, [uv](https://docs.astral.sh/uv/) và Qdrant.

```powershell
Copy-Item .env.example .env
# Điền RAG_GEMINI_API_KEY và thay API key mẫu trong .env
uv sync --locked --group dev --no-group eval
docker compose up -d qdrant
uv run company-rag-serve --reload
```

Swagger: `http://localhost:8000/docs`. Health chỉ kiểm tra process; readiness kiểm tra provider đã được cấu hình và kết nối Qdrant. Readiness không gọi model trả phí nên không xác thực credential Gemini bằng network request.

## Nạp tài liệu

Qua CLI:

```powershell
uv run company-rag-ingest .\data\seed --roles employee,hr
```

Qua API:

```bash
curl -X POST http://localhost:8000/v1/documents \
  -H "X-API-Key: dev-secret-change-me" \
  -F "file=@policy.md;type=text/markdown" \
  -F "allowed_roles=employee,hr" \
  -F 'metadata={"department":"hr"}'
```

Hỗ trợ UTF-8 Markdown, text và PDF. PDF scan không có text được ghi nhận với trạng thái `needs_ocr`; OCR chưa thuộc phạm vi v1. Upload cùng nội dung là idempotent; nội dung mới của cùng tên nguồn tạo version mới và thay chunks active.

Đặt `RAG_ENABLE_ENRICHMENT=true` để tạo summary, câu hỏi giả định, contextual prefix và metadata bằng một structured JSON call cho mỗi chunk. Mặc định tắt để tránh chi phí ingest ngoài ý muốn; nội dung gốc luôn được giữ riêng để citation.

## Hỏi đáp

```bash
curl -X POST http://localhost:8000/v1/chat \
  -H "X-API-Key: dev-secret-change-me" \
  -H "Content-Type: application/json" \
  -d '{"question":"Nhân viên được nghỉ phép bao nhiêu ngày?"}'
```

Response gồm `answer`, `citations`, thống kê retrieval và `request_id`. ACL được áp dụng trong Qdrant trước khi trả candidates. Prompt `answer_v1` coi context là dữ liệu không tin cậy, yêu cầu citation và từ chối khi không đủ bằng chứng.

## Langfuse và quyền riêng tư

`RAG_TRACE_MODE=metadata-only` là mặc định: chỉ gửi request ID, roles, model, latency và metadata kỹ thuật. Chế độ `full` bị từ chối nếu chưa đặt `RAG_ALLOW_SENSITIVE_TRACING=true`.

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

Golden-set đo retrieval hit, groundedness proxy, citation coverage, abstention accuracy và latency. Nhóm `eval` chứa RAGAS cho đánh giá offline mở rộng: `uv sync --group dev --group eval`.

Metadata v1 dùng JSON registry với khóa đồng bộ trong một process; vì vậy mỗi volume chỉ chạy một API replica. Khi cần nhiều replica hoặc ingest song song qua nhiều service, chuyển registry sang PostgreSQL trước khi scale-out. Nhánh lexical BM25 xét tối đa `RAG_LEXICAL_CANDIDATE_LIMIT` tài liệu ACL-eligible; tăng giới hạn hoặc chuyển sang sparse index native khi corpus lớn.

## Docker Compose

```bash
cp .env.example .env
docker compose up --build -d
curl http://localhost:8000/health
curl http://localhost:8000/ready
```

Không expose Qdrant ra mạng công cộng ở production. API key v1 là bước đệm; metadata `allowed_roles` và `Principal` đã tách riêng để thay bằng OIDC/JWT + RBAC.

## Sự cố thường gặp

- `/ready` trả 503: kiểm tra `RAG_GEMINI_API_KEY`, kết nối Qdrant và dimension của embedding model.
- Chat trả 401: thiếu hoặc sai `X-API-Key`; key phải tồn tại trong JSON `RAG_API_KEYS`.
- Upload PDF trả `needs_ocr`: tài liệu là bản scan, cần OCR trước khi reindex.
- OpenRouter không chạy: model phải có trong `RAG_OPENROUTER_ALLOWED_MODELS`; fallback chỉ xảy ra với timeout, rate limit hoặc lỗi 5xx.
