# Company Knowledge RAG

Dịch vụ Retrieval-Augmented Generation (RAG) chuẩn sản xuất (production-oriented) dành cho tài liệu nội bộ công ty được xây dựng bằng **FastAPI**, **Qdrant**, **Gemini / OpenRouter / OpenAI**, **Instructor**, và **Langfuse**.

Hoạt động như một **trợ lý RAG không gian làm việc mở / đơn người dùng (single-user / open workspace RAG assistant)**, hệ thống cho phép nạp tài liệu tức thì và trả lời câu hỏi dựa trên nguồn trích dẫn với **Tìm kiếm kết hợp (Hybrid Search: Dense Vector + BM25 Lexical)**, **Xoay vòng khóa Gemini (Gemini Key Rotation)**, **Chuyển đổi dự phòng đa nhà cung cấp (Multi-Provider Failover)**, và **Từ chối trả lời khi thiếu trích dẫn (Citation-Gated Abstention)**.

---

## 📌 Tính năng chính

- **Nạp tài liệu đa định dạng (Multi-Format Document Ingestion)**: Phân tích các tệp `.md`, `.txt`, `.pdf`, và `.docx` với chiến lược chia nhỏ (chunking) nhận biết theo mục và tùy chọn làm phong phú ngữ cảnh bằng LLM (LLM contextual enrichment).
- **Động cơ truy xuất kết hợp (Hybrid Retrieval Engine)**: Kết hợp tìm kiếm vector dày đặc Qdrant (Gemini Matryoshka embeddings) với tìm kiếm từ vựng BM25 nội tiến trình (in-process) sử dụng Hợp nhất thứ hạng nghịch đảo (Reciprocal Rank Fusion - RRF).
- **Câu trả lời có căn cứ & Kiểm soát trích dẫn (Grounded Answers & Citation Gating)**: Sử dụng các Pydantic schema của `instructor` (`GroundedAnswer`) kết hợp với xác thực trích dẫn sau khi sinh để bắt buộc từ chối trả lời đối với các tuyên bố không có căn cứ.
- **Động cơ LLM đa nhà cung cấp linh hoạt (Resilient Multi-Provider LLM Engine)**: Bộ định tuyến chuyển đổi dự phòng tự động (`Gemini` → `OpenRouter` → `OpenAI`) với nhóm xoay vòng khóa vòng tròn (round-robin key rotation pool: `GEMINI_API_KEY`, `GEMINI_API_FALLBACK_KEY...`) để xử lý hạn ngạch (quota).
- **Đo đạc từ xa ưu tiên quyền riêng tư (Privacy-First Telemetry)**: Tích hợp khả năng quan sát của Langfuse với chế độ vết `metadata-only`, mặc định loại bỏ nội dung tài liệu thô và câu truy vấn khỏi dữ liệu telemetry.
- **Đánh giá chất lượng tích hợp sẵn (Built-in Quality Benchmarking)**: Bộ công cụ CLI để đánh giá bộ dữ liệu chuẩn (golden-set) đo lường tỷ lệ tìm thấy (hit rate), chỉ số căn cứ (groundedness proxy), độ bao phủ trích dẫn (citation coverage), và độ trễ (latency).

---

## 🏗️ Tổng quan kiến trúc

### Quy trình dòng dữ liệu (Data Flow Pipeline)

```text
Upload / CLI → Parse (md/txt/pdf/docx) → Section Chunks → Gemini Embeddings → Qdrant Vector DB
                                                                                  ↓ status=ready
Client → FastAPI → Dense + BM25 Search → RRF Fusion → Grounded Answer → Provider Router (Gemini/OpenRouter/OpenAI)
                                └───────── Langfuse Tracing ──────────┘
```

### Cấu trúc mô-đun (Module Layout)

| Phân hệ | Vị trí | Trách nhiệm chính |
| :--- | :--- | :--- |
| **API** | [`src/api/`](src/api/) | Các điểm truy cập web FastAPI (`/v1/chat`, `/v1/documents`, `/health`, `/ready`) |
| **Nạp dữ liệu (Ingestion)** | [`src/ingestion/`](src/ingestion/) | Phân tích tài liệu, làm sạch NFC, chia nhỏ theo mục, và làm phong phú bằng LLM |
| **Truy xuất (Retrieval)** | [`src/retrieval/`](src/retrieval/) | Tích hợp cơ sở dữ liệu vector Qdrant, bộ đánh chỉ mục từ vựng BM25, và hợp nhất thứ hạng RRF |
| **Nhà cung cấp (Providers)** | [`src/providers/`](src/providers/) | Nhóm xoay vòng khóa Gemini, bộ định tuyến chuyển đổi dự phòng nhà cung cấp OpenRouter/OpenAI |
| **Sinh câu trả lời (Generation)** | [`src/generation/`](src/generation/) | Sinh đầu ra có cấu trúc với Instructor & xác thực trích dẫn sau khi sinh |
| **Khả năng quan sát (Observability)** | [`src/observability/`](src/observability/) | Truy vết span Langfuse & ẩn danh dữ liệu từ xa bảo vệ quyền riêng tư |
| **Đánh giá (Evaluation)** | [`src/evaluation/`](src/evaluation/) | Trình chạy đánh giá bộ dữ liệu chuẩn (golden-set) & các chỉ số chất lượng RAG |
| **Lưu trữ (Storage)** | [`src/storage/`](src/storage/) | Lưu trữ tệp tải lên (`data/uploads/`) & đăng ký danh mục metadata dạng JSON (`data/registry.json`) |

> 📖 **Tài liệu chi tiết**: Để xem các thông số kỹ thuật kiến trúc sâu hơn và lý do thiết kế, tham khảo [`RAG-ARCHITECTURE.md`](RAG-ARCHITECTURE.md) và [`docs/architectures/`](docs/architectures/).

---

## 🚀 Hướng dẫn khởi động nhanh

### Yêu cầu tiên quyết

- **Python**: `>= 3.11`
- **Quản lý gói**: [`uv`](https://docs.astral.sh/uv/)
- **Qdrant**: Quyền truy cập vào một thể hiện cơ sở dữ liệu vector Qdrant (cloud hoặc endpoint tự host)

### Các bước cài đặt

1. **Clone & Cấu hình môi trường**
   ```bash
   cp .env.example .env
   ```
   Mở `.env` và cấu hình các khóa API và điểm truy cập dịch vụ của bạn:
   - **`GEMINI_API_KEY`**: *(Bắt buộc)* Khóa API cho nhúng (embedding) và sinh câu trả lời với Gemini.
   - **`QDRANT_URL` & `QDRANT_API_KEY`**: *(Bắt buộc)* URL endpoint (ví dụ `http://localhost:6333` hoặc Qdrant Cloud URL) và khóa API cho cơ sở dữ liệu vector Qdrant của bạn.
   - **`MAIN_PROVIDER`**: Thiết lập nhà cung cấp LLM chính (`gemini`, `openrouter`, hoặc `openai`).
   - **`OPENROUTER_API_KEY` / `OPENAI_API_KEY`**: (Các) khóa API nếu sử dụng OpenRouter hoặc OpenAI làm nhà cung cấp chính hoặc dự phòng.
   - **`JINA_API_KEY`**: Khóa API nếu sử dụng mô hình embedding/reranker của Jina.

2. **Cài đặt các gói phụ thuộc**
   ```bash
   uv sync --locked --group dev
   ```

3. **Khởi chạy API Server**
   ```bash
   uv run company-rag-serve --reload
   ```

4. **Khám phá Tài liệu tương tác (Interactive Docs)**
   Mở Swagger UI tại [`http://localhost:8000/docs`](http://localhost:8000/docs).

---

## 💻 Hướng dẫn sử dụng & CLI

### Các lệnh CLI

- **Khởi chạy API Server**:
  ```bash
  uv run company-rag-serve --host 0.0.0.0 --port 8000
  ```
- **Nạp thư mục tài liệu**:
  ```bash
  uv run company-rag-ingest ./data/seed
  ```
- **Chạy đánh giá trên Bộ dữ liệu chuẩn (Golden-Set Evaluation)**:
  ```bash
  uv run company-rag-evaluate --dataset evaluation/golden_set.json
  ```

### Ví dụ API

#### 1. Nạp một Tài liệu (`POST /v1/documents`)
```bash
curl -X POST http://localhost:8000/v1/documents \
  -F "file=@policy.md;type=text/markdown" \
  -F 'metadata={"department":"hr"}'
```

#### 2. Truy vấn Trò chuyện RAG (`POST /v1/chat`)
```bash
curl -X POST http://localhost:8000/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"question":"Nhân viên được nghỉ phép bao nhiêu ngày?"}'
```

#### 3. Kiểm tra Sức khỏe & Trạng thái Sẵn sàng (Health & Readiness Probes)
```bash
# Kiểm tra tiến trình
curl http://localhost:8000/health

# Kiểm tra kết nối đầu-cuối tới nhà cung cấp LLM & Qdrant
curl http://localhost:8000/ready
```

---

## ⚙️ Bảng cấu hình

| Biến môi trường | Mặc định | Mô tả |
| :--- | :--- | :--- |
| `MAIN_PROVIDER` | `gemini` | Nhà cung cấp LLM sinh câu trả lời chính (`gemini`, `openrouter`, `openai`) |
| `GEMINI_API_KEY` | *Bắt buộc* | Khóa API cho nhúng (embeddings) & sinh câu trả lời LLM Gemini |
| `GEMINI_API_FALLBACK_KEY` | `None` | Khóa API phụ cho nhóm xoay vòng khóa Gemini (xử lý lỗi 429) |
| `QDRANT_URL` | `http://localhost:6333` | URL endpoint của cơ sở dữ liệu vector Qdrant |
| `QDRANT_API_KEY` | `None` | Khóa API xác thực với cơ sở dữ liệu vector Qdrant |
| `OPENROUTER_API_KEY` | `None` | Khóa API bắt buộc khi `MAIN_PROVIDER=openrouter` hoặc dùng dự phòng |
| `OPENAI_API_KEY` | `None` | Khóa API bắt buộc khi `MAIN_PROVIDER=openai` hoặc dùng dự phòng |
| `JINA_API_KEY` | `None` | Khóa API bắt buộc khi sử dụng mô hình embedding/reranker Jina |
| `EMBEDDING_MODEL` | `jina-embeddings-v5-omni-small` | Mô hình được sử dụng để tạo vector embedding cho tài liệu |
| `EMBEDDING_DIMENSIONS` | `1024` | Kích thước vector (phải khớp với schema collection của Qdrant) |
| `TRACE_MODE` | `metadata-only` | Chế độ đạc từ xa (`metadata-only`, `full`, `disabled`) |
| `ENABLE_ENRICHMENT` | `false` | Bật tính năng tóm tắt chunk & sinh câu truy vấn giả định bằng LLM |

---

## 🔭 Khả năng quan sát với Langfuse

Cấu hình các giá trị này trong tệp `.env`; không bao giờ commit các khóa thực tế.

```dotenv
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_BASE_URL=https://cloud.langfuse.com
ENVIRONMENT=development
TRACE_MODE=metadata-only
```

`LANGFUSE_HOST` cũng được chấp nhận. `TRACE_MODE=metadata-only` được khuyến nghị cho các dự án dùng chung vì nó loại bỏ văn bản tài liệu thô và câu truy vấn khỏi nội dung vết (trace); chỉ sử dụng `full` khi có sự phê duyệt rõ ràng.

Chạy một tệp được hỗ trợ để tạo quan sát nạp tài liệu (ingestion observation). CLI sẽ đẩy toàn bộ dữ liệu (flush) lên Langfuse trước khi thoát.

```powershell
uv run company-rag-ingest .\data\seed\01_2021_ND-CP_283247.docx
```

Để kiểm tra lại sau đó, mở project trên Langfuse, sau đó mở mục **Observations**. Lọc theo môi trường (`development`), tên (`ingestion`), và thời gian chạy; mở quan sát gốc (root observation), sau đó mở vết được liên kết (linked trace) để xem dạng thác nước (waterfall). Các quan sát con đối với quá trình nạp không trùng lặp (non-idempotent ingest) bao gồm `parse`, `chunking`, `indexing`, và `registry`.

Nếu bộ lọc `development` trống, hãy thử lại với `default` và ghi nhận sự bất đồng bộ trước khi tin cậy hoàn toàn vào bộ lọc dựa trên môi trường. Kho lưu trữ này hiện có một quan sát thực tế đã được xác minh dưới `default`; cài đặt ứng dụng vẫn giải quyết thành `development`, do đó điều này cần được theo dõi thêm thay vì tự đưa ra giả định ngầm.

Đối với việc kiểm tra chỉ đọc qua CLI, trước tiên hãy export `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, và `LANGFUSE_BASE_URL` vào shell hiện tại (CLI không tự động đọc tệp `.env`). Sau đó bỏ qua các trường IO/metadata:

```powershell
npx langfuse-cli api observations list --environment development --name ingestion --limit 10 --fields basic,time,metrics,trace_context --json
```

---

## 🧪 Kiểm thử & Chất lượng mã nguồn

Chạy các kiểm thử và phân tích tĩnh trước khi gửi thay đổi:

```bash
# Chạy bộ kiểm thử pytest
uv run pytest

# Chạy Ruff linter
uv run ruff check .

# Chạy kiểm tra kiểu tĩnh MyPy
uv run mypy
```

---

## ❓ Xử lý sự cố & Câu hỏi thường gặp

- **`/ready` trả về `503 Service Unavailable`**: Kiểm tra nội dung `detail` trong phản hồi để xem thông báo lỗi của nhà cung cấp. Xác minh `GEMINI_API_KEY`, khóa của nhà cung cấp chính, trạng thái dịch vụ Qdrant, và kích thước vector tương thích.
- **Lỗi không khớp kích thước vector Qdrant (Vector Dimension Mismatch)**: Nếu Qdrant báo lỗi `vector size is N; expected M`, collection của Qdrant đã được tạo với một giá trị `EMBEDDING_DIMENSIONS` khác. Hãy xóa collection và đánh chỉ mục lại.
- **Trò chuyện luôn trả về Từ chối trả lời (Abstention)**: Xảy ra khi không có kết quả nào vượt qua điểm số `MIN_DENSE_SCORE` hoặc trích dẫn mô hình không qua được xác thực sau khi sinh. Kiểm tra span `retrieval` trong các vết Langfuse.
- **Tải lên tài liệu trả về `needs_ocr`**: Tệp PDF được tải lên chứa hình ảnh quét không có văn bản có thể chọn. Hãy thực hiện tiền xử lý OCR trước khi đánh chỉ mục lại.
- **Nạp tài liệu bị chậm / Giới hạn tần suất (Rate Limits)**: Gemini API vượt quá giới hạn tần suất. Thêm các khóa dự phòng bổ sung (`GEMINI_API_FALLBACK_KEY2...`) vào nhóm xoay vòng để tăng lưu lượng xử lý.
