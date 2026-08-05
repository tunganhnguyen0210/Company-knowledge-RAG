# Quy Chuẩn Đặc Tả Golden Set (Golden Set Specification)

Tài liệu này định nghĩa chuẩn hóa cấu trúc dữ liệu, tiêu chuẩn phân loại, quy trình kiểm soát chất lượng đối với tập dữ liệu vàng (**Golden Dataset**) dùng làm *Reference Dataset* cho việc kiểm thử hệ thống RAG (Retrieval-Augmented Generation).

Tất cả các quy trình tạo Golden Set (thủ công hoặc tự động bằng LLM/Agent) **bắt buộc phải tuân thủ nghiêm ngặt đặc tả này**.

---

## 0. Phạm Vi & Ranh Giới (Scope)

**Tài liệu này chỉ điều chỉnh chất lượng của BẢN THÂN TẬP DỮ LIỆU (Dataset QA), không điều chỉnh việc đánh giá hệ thống RAG (System Evaluation).**

| | Dataset QA (tài liệu này) | System Evaluation ([RAG_Evaluation_Guide.md](file:///e:/VIN-INTERNSHIP/Cowork-RAG/docs/evaluation/RAG_Evaluation_Guide.md)) |
| :--- | :--- | :--- |
| **Đối tượng đo** | `expected_answer` vs `ground_truth_context` (dữ liệu do người/LLM soạn) | Câu trả lời hệ thống sinh ra vs context hệ thống truy xuất được |
| **Câu hỏi trả lời** | "Dữ liệu vàng này có đúng và dùng được không?" | "Hệ thống RAG chạy tốt tới đâu?" |
| **Thời điểm chạy** | Trước khi đưa dataset vào kiểm thử | Mỗi lần thay đổi prompt/model/pipeline (CI/CD) |

Lưu ý quan trọng: các chỉ số ở **Mục 5** (`Faithfulness`, `Answer Relevancy`) **trùng tên** với metrics của Ragas trong `RAG_Evaluation_Guide.md` §8.2 nhưng **khác đối tượng đo**. Đạt ngưỡng ở tài liệu này **KHÔNG** đồng nghĩa với việc vượt qua Release Gate của hệ thống. Xem **Mục 6** cho danh sách hạng mục nằm ngoài phạm vi.

---

## 1. Cấu trúc JSON Schema

Mỗi test case trong Golden Set được đại diện bởi một JSON Object có cấu trúc chuẩn như sau:

```json
{
  "id": 1,
  "type": "direct_lookup",
  "question": "Khi đăng ký thành lập doanh nghiệp thì có thể thực hiện liên thông những thủ tục hành chính nào cùng lúc?",
  "expected_answer": "Doanh nghiệp có thể thực hiện liên thông các thủ tục: khai trình việc sử dụng lao động, cấp mã số đơn vị tham gia bảo hiểm xã hội và đăng ký sử dụng hóa đơn.",
  "ground_truth_context": "Điều 1. Phạm vi điều chỉnh\n\n2. Việc liên thông thủ tục đăng ký thành lập doanh nghiệp, chi nhánh, văn phòng đại diện, khai trình việc sử dụng lao động, cấp mã số đơn vị tham gia bảo hiểm xã hội, đăng ký sử dụng hóa đơn của doanh nghiệp thực hiện theo quy định tại Nghị định của Chính phủ.",
  "gold_metadata": {
    "doc_id": "01_2021_ND-CP_283247.md",
    "chapter": "Chương I",
    "article": "Điều 1"
  },
  "difficulty": "easy"
}
```

---

## 2. Chi Tiết Các Trường Dữ Liệu (Field Specifications)

| Trường (Field) | Kiểu dữ liệu | Ràng buộc / Giá trị cho phép | Mô tả chi tiết |
| :--- | :--- | :--- | :--- |
| `id` | `integer` | Duy nhất trên toàn bộ Golden Set. **Không bắt buộc liên tục** trong từng file sau khi tách theo `type`. | Định danh duy nhất cho từng test case. |
| `type` | `string` | Enum: `direct_lookup`, `multi_hop`, `unanswerable`, `ambiguous`, `adversarial` | Phân loại loại hình câu hỏi để phục vụ đánh giá phân đoạn (segmented evaluation). |
| `question` | `string` | Văn bản tiếng Việt tự nhiên | Câu hỏi đóng vai người dùng cuối có ý định nghiệp vụ rõ ràng, sắc bén, không hỏi chung chung, **không nêu số Điều/Khoản**. |
| `expected_answer` | `string` | Khác rỗng (kể cả trường hợp từ chối) | Câu trả lời chuẩn (Ground Truth Answer), diễn giải tự nhiên, đi thẳng vào trọng tâm, không ghi mã mục cứng. |
| `ground_truth_context` | `string` | Trích **verbatim / near-verbatim** từ tài liệu nguồn. Nhiều đoạn thì nối bằng `\n\n`. **Bắt buộc là `""`** đối với `unanswerable`. | Đoạn văn bản bằng chứng đối soát (Ground Truth Context). |
| `gold_metadata` | `object` | `{doc_id, chapter, article}`. Với `unanswerable`: `chapter` và `article` **bắt buộc là `null`** (xem 2.1). | Tọa độ pháp lý định vị bằng chứng trong tài liệu. |
| `difficulty` | `string` | Enum: `easy`, `medium`, `hard` | Độ khó ước lượng của câu hỏi đối với hệ thống RAG. |

### 2.1. Quy Tắc `gold_metadata` Cho `unanswerable`
`gold_metadata.chapter` và `gold_metadata.article` là **golden IDs** — chúng là đầu vào bắt buộc để đo Retrieval Accuracy ở giai đoạn System Evaluation (`RAG_Evaluation_Guide.md` §3).

Với câu `unanswerable`, thông tin **không tồn tại** trong tài liệu, nên **mọi giá trị `chapter`/`article` đều là sai sự thật** và sẽ làm sai lệch chỉ số `context_recall`. Bắt buộc:

```json
"gold_metadata": { "doc_id": "01_2021_ND-CP_283247.md", "chapter": null, "article": null }
```

> ⚠️ **Nợ dữ liệu cần xử lý**: 18 sample `unanswerable` hiện tại đang gán `article` tuỳ ý (ví dụ `"Điều 3"`) — vi phạm quy tắc này, cần chuẩn hoá về `null`.

---

## 3. Quy Định Phân Loại 5 Dạng Câu Hỏi (`type`)

| `type` | Mục đích kiểm thử | Ràng buộc riêng của `expected_answer` |
| :--- | :--- | :--- |
| `direct_lookup` | Tra cứu trực tiếp thông tin đơn điểm nhắm vào tình huống nghiệp vụ cụ thể. | Trả lời thẳng, bám sát context. |
| `multi_hop` | Tổng hợp suy luận thông tin từ **nhiều** điều khoản/chương khác nhau. | Phải thể hiện việc kết hợp thông tin; `ground_truth_context` nối nhiều đoạn bằng `\n\n`. |
| `unanswerable` | Câu hỏi ngoài phạm vi tài liệu, kiểm thử khả năng từ chối trả lời (chống ảo giác). | **Phải nêu rõ** thông tin không thuộc phạm vi tài liệu. `ground_truth_context = ""`. |
| `ambiguous` | Câu hỏi mơ hồ/thiếu bối cảnh. Kiểm thử việc **hỏi lại làm rõ (clarify) thay vì tự đoán bối cảnh**. | Phải hỏi lại làm rõ hoặc liệt kê các nhánh tình huống ("nếu…", "trường hợp…"), tuyệt đối không chọn bừa một giả định. |
| `adversarial` | Câu hỏi gài bẫy/chứa giả định sai sự thật. Kiểm thử khả năng đính chính và chống tiêm nhiễm (Prompt Injection). | **Phải đính chính** giả định sai một cách lịch sự, dựa trên căn cứ trong tài liệu. |

> ⚠️ **Khoảng trống phủ hiện tại (tính đến 2026-08-05)**: `golden_set_multi_hop.json` đang **rỗng (0 sample)**. Kịch bản *Multi-intent Integration* (`RAG_Evaluation_Guide.md` §5.3) hiện chưa được kiểm thử.

---

## 4. Tổ Chức File & Quy Trình Review Chất Lượng

### 4.1. Tổ chức file
Golden Set được tách thành **5 file theo `type`** tại thư mục [evaluation/golden_set/](file:///e:/VIN-INTERNSHIP/Cowork-RAG/evaluation/golden_set):

```
evaluation/golden_set/
├── golden_set_direct_lookup.json
├── golden_set_multi_hop.json
├── golden_set_unanswerable.json
├── golden_set_ambiguous.json
└── golden_set_adversarial.json
```

Mỗi file là một **JSON Array** các object theo schema ở Mục 1. Việc tách theo `type` vừa phục vụ review song song, vừa cho phép chạy đánh giá phân đoạn theo từng dạng câu hỏi.

### 4.2. Review bằng LLM Reviewer Agent
Mỗi đợt review gửi **một file** ở trên kèm **toàn bộ** tài liệu nguồn [01_2021_ND-CP_283247.md](file:///e:/VIN-INTERNSHIP/Cowork-RAG/data/extracted/01_2021_ND-CP_283247.md) cho Reviewer Agent.

* **Đặc tả Prompt & Cấu hình Reviewer Agent**: [GOLDEN_SET_REVIEWER_PROMPT.md](file:///e:/VIN-INTERNSHIP/Cowork-RAG/docs/references/GOLDEN_SET_REVIEWER_PROMPT.md).
* **Kiểm tra 5 Checkpoints**: Schema Integrity, Question Realism, Answer Faithfulness, Type Compliance, Context Accuracy.

---

## 5. Đo Lường Chỉ Số Tự Động (Automatic Dataset QA Metrics)

Công cụ [scripts/evaluate_golden_set.py](file:///e:/VIN-INTERNSHIP/Cowork-RAG/scripts/evaluate_golden_set.py) chấm điểm chất lượng dataset theo 3 chỉ số type-aware:

| Chỉ số | Trọng số | Đo cái gì |
| :--- | :--- | :--- |
| `Faithfulness` | 0.45 | Độ trung thực của `expected_answer` so với `ground_truth_context` (có nhánh xử lý riêng cho `unanswerable`, `adversarial`, `ambiguous`). |
| `Answer Relevancy` | 0.30 | Mức độ `expected_answer` bám đúng trọng tâm `question`. |
| `Question Quality` | 0.25 | Độ sắc bén, tự nhiên, không lộ mã Điều/Khoản của `question`. |

```bash
python scripts/evaluate_golden_set.py \
  --dataset evaluation/golden_set/golden_set_direct_lookup.json \
  --report reports/golden_eval_report.json
```

> Tham số `--dataset` **bắt buộc phải truyền tường minh**; giá trị mặc định trong script trỏ tới file gộp không tồn tại.

**Bản chất hiện tại**: cả 3 chỉ số đều được cài đặt bằng **heuristic xác định (regex + word-overlap)**, tương ứng **Lớp 1 – Codebase** trong ma trận `RAG_Evaluation_Guide.md` §3. Đây là bộ lọc rẻ và nhanh để bắt lỗi thô, **không thay thế** LLM Judge (Lớp 2) hay Human Review (Lớp 3).

### 5.1. Nguyên Tắc Xử Lý Mẫu Dưới Ngưỡng (Threshold Control)
* **Ngưỡng chất lượng tối thiểu**: `overall_score >= 0.85 / 1.0`.
* **KHÔNG tự động loại bỏ / xóa mẫu**: Công cụ **bảo toàn 100% sample**, tuyệt đối không tự xóa dữ liệu.
* **Xuất danh sách ID cần cải thiện**: Ghi `failed_item_ids` và `below_threshold_items` vào `reports/golden_eval_report.json` để người phát triển review và chỉnh sửa thủ công.
* Ngưỡng `0.85` này là **ngưỡng chất lượng dữ liệu**, hoàn toàn tách biệt với Release Gate của hệ thống (`groundedness ≥ 0.95`, `answer_relevance ≥ 0.90`, `citation_invalid_rate ≤ 0.01`, `p0_safety_failures = 0` — `RAG_Evaluation_Guide.md` §5.3).

---

## 6. Nằm Ngoài Phạm Vi (Out of Scope)

Các hạng mục sau **được yêu cầu bởi `RAG_Evaluation_Guide.md` nhưng KHÔNG do tài liệu này thực hiện**. Ghi nhận rõ ràng để tránh nhầm lẫn rằng Golden Set đã "đánh giá xong" hệ thống RAG:

| Hạng mục | Thuộc về | Trạng thái | Golden Set cung cấp gì làm đầu vào |
| :--- | :--- | :--- | :--- |
| **Retrieval Accuracy** (`context_precision`, `context_recall`) | Guide §2.1, §3, §8.2 | ❌ Chưa triển khai | `gold_metadata` (golden IDs) — hiện **chưa có công cụ nào tiêu thụ** |
| **Citation Accuracy** (`Citation Match Rate`) | Guide §1.4, §4.1, §6.1 | ❌ Chưa triển khai | `gold_metadata` làm ground truth cho trích dẫn. Lưu ý xung đột thiết kế: `expected_answer` bị cấm ghi mã mục cứng, nên citation phải được đối soát qua `gold_metadata`, không phải qua văn bản câu trả lời. |
| **LLM Judge Groundedness + Calibration** | Guide §3, §6.2, §7 | ❌ Chưa triển khai | Cặp `question` / `ground_truth_context` / `expected_answer` |
| **Release Gate & Production Monitoring** | Guide §1, §5.3 | ❌ Chưa triển khai | — |
| **Kịch bản `Source Conflicts` (mâu thuẫn nguồn / data freshness)** | Guide §5.5 | ❌ Không có `type` tương ứng | — (dataset hiện chỉ có 1 văn bản nguồn nên chưa áp dụng được) |

### 6.1. Quy Tắc Bổ Sung Case Mới (Regression Intake)
Theo vòng đời đánh giá (`RAG_Evaluation_Guide.md` §1 bước 9), mọi lỗi bắt được ở production phải được chuyển thành test case mới bổ sung ngược vào Golden Set:

1. Xác định `type` phù hợp → thêm vào đúng file trong `evaluation/golden_set/`.
2. Cấp `id` mới = `max(id)` toàn bộ dataset `+ 1` (không tái sử dụng id đã xóa).
3. Chạy lại `evaluate_golden_set.py` trên file vừa sửa; sample mới phải đạt ngưỡng `0.85` trước khi commit.
