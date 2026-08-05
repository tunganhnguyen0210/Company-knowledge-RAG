# Quy Chuẩn Đặc Tả Golden Set (Golden Set Specification)

Tài liệu này định nghĩa chuẩn hóa cấu trúc dữ liệu, tiêu chuẩn phân loại, quy trình đánh giá chất lượng đối với tập dữ liệu vàng (**Golden Dataset**) dùng trong việc kiểm thử và đo lường chất lượng hệ thống RAG (Retrieval-Augmented Generation). 

Tất cả các quy trình tạo Golden Set (thủ công hoặc tự động bằng LLM/Agent) **bắt buộc phải tuân thủ nghiêm ngặt đặc tả này**.

---

## 1. Cấu trúc JSON Schema

Mỗi test case trong Golden Set được đại diện bởi một JSON Object có cấu trúc chuẩn như sau:

```json
{
  "id": 1,
  "type": "direct_lookup",
  "question": "Khi đăng ký thành lập doanh nghiệp thì có thể thực hiện liên thông những thủ tục hành chính nào cùng lúc?",
  "expected_answer": "Khi đăng ký thành lập doanh nghiệp, chi nhánh hoặc văn phòng đại diện, doanh nghiệp có thể thực hiện liên thông các thủ tục hành chính gồm: khai trình việc sử dụng lao động, cấp mã số đơn vị tham gia bảo hiểm xã hội và đăng ký sử dụng hóa đơn.",
  "ground_truth_context": "Điều 1. Phạm vi điều chỉnh\n\n1. Nghị định này quy định chi tiết về hồ sơ, trình tự, thủ tục đăng ký doanh nghiệp; đăng ký hộ kinh doanh...\n2. Việc liên thông thủ tục đăng ký thành lập doanh nghiệp, chi nhánh, văn phòng đại diện, khai trình việc sử dụng lao động, cấp mã số đơn vị tham gia bảo hiểm xã hội, đăng ký sử dụng hóa đơn của doanh nghiệp...",
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
| `id` | `integer` | Số nguyên tăng dần (`1, 2, 3...`) | Định danh duy nhất cho từng test case trong tập Golden Set. |
| `type` | `string` | Enum: `direct_lookup`, `multi_hop`, `unanswerable`, `ambiguous`, `adversarial` | Phân loại loại hình câu hỏi để phục vụ đánh giá phân đoạn (segmented evaluation). |
| `question` | `string` | Văn bản tiếng Việt tự nhiên | Câu hỏi đóng vai người dùng cuối có ý định nghiệp vụ rõ ràng, sắc bén, không hỏi chung chung, không nêu số Điều/Khoản. |
| `expected_answer` | `string` | Khác rỗng (trừ trường hợp từ chối) | Câu trả lời chuẩn (Ground Truth Answer), diễn giải tự nhiên, đi thẳng vào trọng tâm, không ghi mã mục cứng. |
| `ground_truth_context` | `string` | Chuỗi văn bản gốc trích xuất | Đoạn văn bản trích trực tiếp từ tài liệu nguồn dùng làm bằng chứng đối soát (Ground Truth Context). |
| `gold_metadata` | `object` | Tọa độ pháp lý & Định danh tài liệu | Cấu trúc định vị vị trí câu hỏi trong tài liệu (`doc_id`, `chapter`, `article`). |
| `difficulty` | `string` | Enum: `easy`, `medium`, `hard` | Tiêu chí đánh giá độ khó của câu hỏi đối với hệ thống RAG. |

---

## 3. Quy Định Phân Loại 5 Dạng Câu Hỏi (`type`)

1. **`direct_lookup`**: Tra cứu trực tiếp thông tin đơn điểm nhắm vào tình huống nghiệp vụ cụ thể.
2. **`multi_hop`**: Tổng hợp suy luận thông tin từ nhiều điều khoản/đoạn văn bản khác nhau.
3. **`unanswerable`**: Câu hỏi ngoài phạm vi/không có dữ liệu nhằm kiểm thử khả năng từ chối trả lời (chống ảo giác).
4. **`ambiguous`**: Câu hỏi mơ hồ/thiếu bối cảnh nhằm kiểm thử khả năng xử lý kịch bản tổng quan.
5. **`adversarial`**: Câu hỏi gài bẫy/chứa giả định sai sự thật nhằm kiểm thử khả năng đính chính và chống tiêm nhiễm (Prompt Injection).

---

## 4. Quy Trình Đánh Giá & Kiểm Soát Chất Lượng (Evaluation Workflow)

### 4.1. Quy Trình Review Chất Lượng Bằng LLM Reviewer Agent
Để đảm bảo tính đúng đắn của dữ liệu trước khi đưa vào kiểm thử hệ thống, tập dữ liệu vàng được phân chia thành **5 phần (5 Part Partition Strategy)** lưu tại thư mục [evaluation/parts/](file:///e:/VIN-INTERNSHIP/Cowork-RAG/evaluation/parts) để thẩm định song song với toàn bộ tài liệu nguồn [01_2021_ND-CP_283247.md](file:///e:/VIN-INTERNSHIP/Cowork-RAG/data/extracted/01_2021_ND-CP_283247.md).

* **Đặc tả Prompt & Cấu hình Reviewer Agent**: Chi tiết tại [GOLDEN_SET_REVIEWER_PROMPT.md](file:///e:/VIN-INTERNSHIP/Cowork-RAG/docs/references/GOLDEN_SET_REVIEWER_PROMPT.md).
* **Kiểm tra 5 Checkpoints**: Schema Integrity, Question Realism, Answer Faithfulness, Type Compliance, Context Accuracy.

### 4.2. Đo Lường Chỉ Số Đánh Giá Tự Động (Automatic Metrics Evaluation)
Công cụ đánh giá tự động [scripts/evaluate_golden_set.py](file:///e:/VIN-INTERNSHIP/Cowork-RAG/scripts/evaluate_golden_set.py) thực hiện đo lường chất lượng tập Golden Set dựa trên 3 nhóm chỉ số đa kịch bản (Type-Aware Metrics):

1. **`Faithfulness`**: Độ trung thực của `expected_answer` dựa trên `ground_truth_context` (đặc biệt xử lý riêng cho câu `unanswerable` và `adversarial`).
2. **`Answer Relevancy`**: Mức độ trả lời đúng trọng tâm của câu hỏi `question`.
3. **`Question Quality`**: Độ sắc bén, rõ ràng và tự nhiên của `question`.

### Nguyên Tắc Kiểm Xử Lý Mẫu Dưới Ngưỡng (Threshold Control):
* **Ngưỡng chất lượng tối thiểu**: `Threshold = 0.85 / 1.0`.
* **KHÔNG tự động loại bỏ / xóa bớt mẫu**: Công cụ đánh giá **bảo toàn 100% các sample**, tuyệt đối không tự động xóa mẫu dữ liệu trong Golden Set.
* **Xuất danh sách ID cần cải thiện**: Công cụ tự động liệt kê cụ thể **danh sách các `id` sample bị dưới ngưỡng** trong báo cáo `reports/golden_eval_report.json` để người phát triển review và chỉnh sửa thủ công.
