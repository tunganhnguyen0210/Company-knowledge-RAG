# Company Knowledge RAG

Dịch vụ RAG cho tài liệu nội bộ, ưu tiên câu trả lời có nguồn và khả năng quan sát. Hệ thống chạy theo mô hình **single-user / open workspace**: API không yêu cầu authentication, mọi tài liệu đã ingest đều truy vấn được. `MAIN_PROVIDER` chọn LLM chính — Gemini, OpenRouter hoặc OpenAI; các provider khác có cấu hình hợp lệ sẽ xử lý lỗi tạm thời. Riêng embeddings luôn chạy trên Gemini, nên `GEMINI_API_KEY` là bắt buộc kể cả khi `MAIN_PROVIDER` không phải Gemini.

## Kiến trúc

```text
Upload/CLI → Parse (md/txt/pdf/docx) → Versioned chunks → Gemini embeddings → Qdrant
                                                                     ↓ status=ready
Client → FastAPI (open) → Dense + BM25 + RRF → Prompt answer → MAIN_PROVIDER
                            └──────── Langfuse trace ────────┘
```

Các ranh giới chính nằm trong `src/`: `api`, `domain`, `ingestion`, `retrieval`, `providers`, `generation`, `prompts`, `observability`, `evaluation` và `storage`. Chi tiết từng lớp xem [ARCHITECTURE.md](ARCHITECTURE.md) và [docs/architectures/](docs/architectures/).

## Chạy local bằng uv

Yêu cầu: Python 3.11+, [uv](https://docs.astral.sh/uv/) và Qdrant.

```powershell
Copy-Item .env.example .env
# Đặt MAIN_PROVIDER, điền GEMINI_API_KEY (bắt buộc, dùng cho embeddings) và API key của LLM đã chọn
uv sync --locked --group dev --no-group eval
uv run company-rag-serve --reload
```

`QDRANT_URL` quyết định cluster nào được dùng. Trỏ thẳng vào Qdrant Cloud (`https://<cluster>.cloud.qdrant.io:6333` kèm `QDRANT_API_KEY`) là mặc định nhẹ nhất vì máy dev không phải nuôi container nào. Nếu muốn chạy Qdrant local thì bật profile:

```powershell
docker compose --profile local-qdrant up -d qdrant
# rồi đặt QDRANT_URL=http://localhost:6333 trong .env
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

## Chunking

Chunker ([chunker.py](src/ingestion/chunker.py)) bám theo cấu trúc văn bản pháp quy Việt Nam: **Phần → Chương → Mục → Điều**, nhận diện bằng regex trên đầu dòng chứ không dựa vào Heading style của Word — file .docx tải từ nguồn công báo thường để toàn bộ đoạn ở style `Normal`, không có heading nào để bám. Heading markdown `#` vẫn được tôn trọng cho tài liệu nội bộ thường. Tiêu đề kiểu hai dòng (`Chương I` rồi `NHỮNG QUY ĐỊNH CHUNG` ở dòng sau) được ghép lại thành một tiêu đề.

Mỗi Điều là một segment. Điều dài hơn `max_chars` (mặc định 2500) được cắt theo thang ưu tiên, chỉ xuống mức mịn hơn khi mức thô còn để lại mảnh quá trần: **khoản (`1.`) → điểm (`a)`) → dòng trống → dòng → hết câu → cắt cứng**. Trên bộ 17 văn bản trong `data/seed/`, mức cắt cứng thực tế là 0%.

Hai trường tách bạch:

- `text` — nguyên văn tài liệu, dùng cho citation. Không chèn thêm gì.
- `retrieval_text` — cái thực sự được embed và đưa vào BM25: `"<tên file> — Chương I. … > Điều 5. …\n\n<text>"`. Không có nó, một chunk cắt ra từ giữa một Điều không mang dấu vết nào về việc nó thuộc điều nào, trong khi đó lại chính là thứ câu hỏi pháp lý hay hỏi.

`section` (tiêu đề Điều) cũng được đưa vào prompt trả lời và vào `Citation`, để model gọi đúng tên điều thay vì chỉ tên file.

## Soi chunk và retrieval trên Swagger

Nhóm `inspection` trong `/docs` mở ba cửa sổ vào pipeline, không endpoint nào gọi LLM:

| Endpoint | Dùng khi |
| --- | --- |
| `POST /v1/documents/preview-chunks` | Chạy khô parse + chunk cho một file: trả về từng chunk kèm `section`, `position`, `text`, và `stats`. Không embed, không index, không ghi registry — đổi `max_chars` trong form để thử ngưỡng khác. |
| `GET /v1/documents/{document_id}/chunks` | Đọc lại chunk **đang nằm trong Qdrant** theo `position`, phân trang bằng `offset`/`limit`. Đây là nội dung thật mà retrieval nhìn thấy. |
| `POST /v1/search` | Chạy đúng đường retrieval của `/v1/chat` (dense + BM25 + RRF + rerank) rồi dừng lại: trả `rank`, `score` và toàn văn chunk. Kiểm tra chunk lấy về có đúng không trước khi đổ lỗi cho câu trả lời. |

`GET /v1/documents` liệt kê mọi tài liệu trong registry để lấy `document_id`.

`stats` trong preview đọc như sau: `chunks_at_max_chars` là số chunk bị cắt vì chạm trần ký tự chứ không phải vì hết cấu trúc — tỉ lệ này cao nghĩa là chunker đang cắt giữa câu; `chunks_without_section` cao nghĩa là tài liệu không có heading nào để bám vào.

`allowed_roles` vẫn được form upload nhận, lưu trong registry và trong payload Qdrant, nhưng **không còn được dùng để lọc khi truy vấn** — retrieval chỉ lọc `status == "ready"`. Đây là metadata phân loại, không phải ranh giới bảo mật. Bối cảnh và lộ trình quay lại RBAC: [docs/research/authentication-removal-analysis.md](docs/research/authentication-removal-analysis.md).

Đặt `ENABLE_ENRICHMENT=true` để tạo summary, câu hỏi giả định, contextual prefix và metadata bằng một structured call cho mỗi chunk. Mặc định tắt để tránh chi phí ingest ngoài ý muốn; nội dung gốc luôn được giữ riêng cho citation, phần enrich chỉ đi vào `retrieval_text`.

## Embeddings

Embeddings chạy trên Gemini (`EMBEDDING_MODEL`, mặc định `gemini-embedding-2`) và dùng chung key pool với generation. Passage và query dùng hai task type khác nhau (`RETRIEVAL_DOCUMENT` / `RETRIEVAL_QUERY`). `EMBEDDING_DIMENSIONS` mặc định 3072 — đúng độ rộng native của model; mọi giá trị nhỏ hơn là một lát cắt Matryoshka, được chuẩn hóa lại trước khi đưa vào cosine search. Giá trị này phải khớp với collection Qdrant, đổi một trong hai là phải reindex từ đầu.

Mỗi text phải được bọc trong một `types.Content` riêng. Nếu truyền thẳng list string, model gộp cả list thành **một** vector duy nhất thay vì một vector mỗi chunk.

Ingest hàng loạt đụng rate limit theo phút và không có router để failover như bên generation, nên embedding provider gửi theo batch 100 text và tự retry tối đa 5 lần. Lỗi transient dùng backoff lũy thừa (1s → 30s); riêng khi mọi key đều đang cooldown vì quota thì nó ngủ đúng bằng `GEMINI_KEY_COOLDOWN_SECONDS` — ngủ ngắn hơn chỉ phí lượt thử vào một pool chưa thể trả lời.

## Provider và xoay vòng Gemini key

`MAIN_PROVIDER` luôn là primary. `ProviderRouter` thử lại primary `PROVIDER_MAX_ATTEMPTS` lần (mặc định 2, backoff 0.1s × 2^n) khi gặp lỗi transient, sau đó mới chuyển sang provider phụ đầu tiên có cấu hình hợp lệ. Lỗi không transient được raise ngay, không phí lượt fallback. `usage` của mỗi response ghi lại `primary_attempts` và `fallback_used`.

Gemini còn có key pool riêng (`providers/gemini_key_pool.py`) dùng chung cho cả generation lẫn embeddings: khai báo `GEMINI_API_KEY`, `GEMINI_API_FALLBACK_KEY`, rồi `GEMINI_API_FALLBACK_KEY2`, `GEMINI_API_FALLBACK_KEY3`… Tên phải khớp đúng pattern đó, sai một chữ là key bị bỏ qua lặng lẽ. Pool chọn key theo round-robin, và khi một key trả lỗi quota/429 thì key đó bị đặt cooldown `GEMINI_KEY_COOLDOWN_SECONDS` (mặc định 60s) trong khi các key còn lại tiếp tục phục vụ.

Quota embedding của free tier tính **theo Google Cloud project mỗi ngày**, không theo key: nhiều key cùng một project vẫn dùng chung một túi 1000 request/ngày. Chỉ key thuộc các project khác nhau mới thực sự nhân được hạn mức. Key không bao giờ xuất hiện trong log — `GeminiKeyLease` che giá trị trong cả `__repr__` và `__str__`. Xem thêm [docs/references/gemini-key-rotation-pattern.md](docs/references/gemini-key-rotation-pattern.md).

Nếu muốn dùng pool này trong LCEL/LangGraph, `GeminiRotatingRunnable` ([llm_rotation.py](src/providers/llm_rotation.py)) là một `Runnable` thật: pipe được bằng `|`, kế thừa `batch`/`ainvoke`/`with_retry`, và nhận thêm `fallback_factory` cho trường hợp mọi key đều hết quota. Pipeline hiện tại **không** đi qua nó — chat dùng `GeminiProvider` + `ProviderRouter`.

## Structured output

Mọi lời gọi LLM đi qua [instructor](https://github.com/567-labs/instructor): provider trả về Pydantic model đã validate (`GroundedAnswer`, `ChunkEnrichment`, `ProbeResult`) thay vì text tự do, không còn parse JSON bằng regex. instructor chọn cơ chế mạnh nhất cho từng provider — `responseSchema` native của Gemini, tool calling của OpenAI, JSON schema trong prompt cho các backend hỗn hợp của OpenRouter — và reask kèm lỗi validation khi payload sai. `STRUCTURED_MAX_RETRIES` (mặc định `2`) giới hạn số lần reask; hết lượt sẽ raise `ProviderError`, và lỗi này chỉ được đánh dấu transient nếu nguyên nhân gốc là rate limit hay lỗi mạng, còn schema mà model không thỏa được thì coi là vĩnh viễn.

## Hỏi đáp

```bash
curl -X POST http://localhost:8000/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"question":"Nhân viên được nghỉ phép bao nhiêu ngày?"}'
```

Response gồm `answer`, `citations`, thống kê retrieval, `request_id` và cặp `provider`/`model` đã thực sự trả lời. Prompt `answer` (định nghĩa trong [src/prompts/answer.yaml](src/prompts/answer.yaml)) coi context là dữ liệu không tin cậy và yêu cầu mỗi nhận định kèm marker `[C<n>]`.

Citation là cổng chặn cuối cùng: chỉ số nào model trả về mà nằm ngoài khoảng context thực tế sẽ bị loại, và nếu không còn citation hợp lệ nào thì câu trả lời bị thay bằng câu abstention chuẩn — model không thể tự khẳng định điều gì mà không trỏ về đoạn đã được đưa vào prompt.

Retrieval là hybrid: dense search trên Qdrant (lọc bỏ hit dưới `MIN_DENSE_SCORE`) hợp nhất với BM25 in-process bằng Reciprocal Rank Fusion (`k=60`).

`MIN_DENSE_SCORE` trên thực tế là **cổng chặn ở mức câu hỏi**, không phải bộ lọc từng chunk: nhánh dense chỉ lấy `limit * 4` ứng viên, và với một câu hỏi đúng chủ đề thì cả nhóm đó đều vượt ngưỡng, còn câu lạc đề thì cả nhóm đều rớt và truy vấn chỉ còn BM25. Vì vậy score RRF cuối cùng cho biết luôn nhánh nào đã đóng góp: `≈0.033` là cả hai nhánh cùng đồng ý, `≈0.016` là chỉ còn BM25 — dấu hiệu câu hỏi nằm ngoài phạm vi tài liệu. Ngưỡng phải hiệu chỉnh theo embedding model và corpus; đo trên Jina + bộ nghị định này, top-1 của câu đúng chủ đề rơi vào 0.70–0.86 còn câu lạc đề chỉ 0.26–0.33, nên `0.50` nằm giữa vùng an toàn.

BM25 index cả âm tiết lẫn cặp âm tiết liền kề ([hybrid.py](src/retrieval/hybrid.py)). Tiếng Việt viết mỗi từ thành nhiều âm tiết rời, nên tokenizer chỉ-âm-tiết biến "liên thông" thành hai token tầm thường và BM25 mất khả năng phân biệt chunk định nghĩa thuật ngữ đó với mọi chunk khác trong cùng nghị định. Đây không phải chuyện lý thuyết: với câu hỏi về liên thông thủ tục, chunk đúng đứng **hạng 15** theo BM25 unigram và **hạng 1** theo bigram — vì `k=60` làm phẳng chênh lệch giữa các hạng đầu, xếp hạng nhiễu của BM25 đủ sức đá chunk đó ra khỏi top-5 dù dense đã xếp nó hạng 1.

## Langfuse và quyền riêng tư

`TRACE_MODE=metadata-only` là mặc định: các trường nội dung (`question`, `answer`, `context`, `parsed_text`, `text`, `system_instruction`, `user_prompt`, `response`) bị lọc đệ quy khỏi payload, chỉ còn request ID, model, latency, số lượng và metadata kỹ thuật. Chế độ `full` bị từ chối ngay khi khởi tạo Settings nếu chưa đặt `ALLOW_SENSITIVE_TRACING=true`.

Pipeline được trace theo span lồng nhau: `ingestion` → `parse` / `chunking` / `enrichment` / `indexing` / `registry` phía nạp tài liệu, và `rag-request` → `retrieval` / `generation` phía hỏi đáp. Span `retrieval` ghi lại top-k kèm score, `chunk_id`, `document_id`, version và section; span `generation` ghi provider, model, token usage và danh sách citation.

Điểm đến do `LANGFUSE_HOST` quyết định: một region của Langfuse Cloud (`https://cloud.langfuse.com`, `https://jp.cloud.langfuse.com`…) hoặc [instance self-host](https://langfuse.com/self-hosting) của bạn. Tracing chỉ bật khi có đủ cả `LANGFUSE_PUBLIC_KEY` và `LANGFUSE_SECRET_KEY`; thiếu một trong hai thì `Tracer` im lặng bỏ qua mọi span thay vì báo lỗi ([tracing.py:13-24](src/observability/tracing.py#L13-L24)).

Kiểm tra credential trước khi tin vào dashboard trống:

```powershell
uv run python -c "from langfuse import Langfuse; from settings import Settings; s = Settings(); print(Langfuse(public_key=s.langfuse_public_key, secret_key=s.langfuse_secret_key, host=s.langfuse_host).auth_check())"
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

Service `api` đọc `QDRANT_URL` từ `.env`, nên compose chạy được với cả Qdrant Cloud lẫn local. Container Qdrant local nằm sau profile `local-qdrant` và chỉ bind vào `127.0.0.1`; đừng expose ra mạng công cộng ở production. API hiện không có lớp authentication nào, nên nếu triển khai ngoài máy local thì phải đặt sau reverse proxy hoặc mạng nội bộ có kiểm soát. `Principal` và `allowed_roles` vẫn còn trong domain model để lắp lại OIDC/JWT + RBAC khi cần.

## Sự cố thường gặp

- `/ready` trả 503: đọc `detail` trong response — nó chứa nguyên văn lỗi từ provider. Kiểm tra `GEMINI_API_KEY`, API key của `MAIN_PROVIDER`, kết nối Qdrant và `EMBEDDING_DIMENSIONS` khớp với collection.
- Qdrant báo `vector size is N; expected M`: collection đã tạo với số chiều khác `EMBEDDING_DIMENSIONS`. Phải xóa collection và reindex, không sửa được tại chỗ.
- Chat luôn trả câu abstention: hoặc không hit nào vượt `MIN_DENSE_SCORE`, hoặc model không trả citation hợp lệ. Span `retrieval` trong Langfuse cho biết đó là vấn đề nào.
- Upload PDF trả `needs_ocr`: tài liệu là bản scan, cần OCR trước khi reindex.
- Ingest dừng với `429 ... EmbedContentRequestsPerDayPerProjectPerModel`: cạn quota ngày của project đó, không phải rate limit theo phút — chờ tới khi reset hoặc thêm key từ project khác. Kiểm tra pool có thật sự nhận đủ key bằng `python -c "from settings import Settings; print(Settings().build_gemini_key_pool().key_count)"`.
- OpenRouter không chạy: model phải có trong `OPENROUTER_ALLOWED_MODELS`. Nếu lỗi tạm thời, hệ thống thử provider khác đã được cấu hình.
