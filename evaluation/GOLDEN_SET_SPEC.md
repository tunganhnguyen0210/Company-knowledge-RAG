# Quy Chuẩn Đặc Tả Golden Set (Golden Set Specification)

Tài liệu này định nghĩa chuẩn hóa cấu trúc dữ liệu, tiêu chuẩn phân loại, quy trình đánh giá chất lượng đối với tập dữ liệu vàng (**Golden Dataset**) dùng trong việc kiểm thử và đo lường chất lượng hệ thống RAG (Retrieval-Augmented Generation). 

Tất cả các quy trình tạo Golden Set (thủ công hoặc tự động bằng LLM/Agent) **bắt buộc phải tuân thủ nghiêm ngặt đặc tả này**.

---

## 1. Cấu trúc JSON Schema (Định dạng chung)

Mỗi test case trong Golden Set được đại diện bởi một JSON Object có cấu trúc định dạng chung chuẩn như sau:

```json
{
  "id": "<integer>",
  "type": "<string>",
  "question": "<string>",
  "expected_answer": "<string>",
  "golden_truth_contexts": [
    {
      "golden_truth_context": "<string>",
      "golden_metadata": {
        "doc_id": "<string>",
        "chapter": "<string>",
        "article": "<string>"
      }
    },
    {
      "golden_truth_context": "<string>",
      "golden_metadata": {
        "doc_id": "<string>",
        "chapter": "<string>",
        "article": "<string>"
      }
    }
  ],
  "difficulty": "<string>"
}
```

---

## 2. Chi Tiết Các Trường Dữ Liệu (Field Specifications)

| Trường (Field) | Kiểu dữ liệu | Ràng buộc / Giá trị cho phép | Mô tả chi tiết |
| :--- | :--- | :--- | :--- |
| `id` | `integer` | Số nguyên tăng dần (`1, 2, 3...`) | Định danh duy nhất cho từng test case trong tập Golden Set. |
| `type` | `string` | Enum: `direct_lookup`, `multi_hop`, `unanswerable`, `ambiguous`, `adversarial` | Phân loại loại hình câu hỏi để phục vụ đánh giá phân đoạn (segmented evaluation). |
| `question` | `string` | Văn bản tiếng Việt tự nhiên | Câu hỏi đóng vai người dùng cuối có ý định nghiệp vụ rõ ràng, sắc bén. |
| `expected_answer` | `string` | Văn bản tiếng Việt tự nhiên | Câu trả lời chuẩn (Ground Truth Answer), diễn giải tự nhiên, đi thẳng vào trọng tâm. |
| `golden_truth_contexts` | `array of dict` | Danh sách các đối tượng bối cảnh (`array`) | Danh sách các đối tượng bối cảnh bằng chứng. Mỗi phần tử là một `dict` chứa `golden_truth_context` và `golden_metadata` tương ứng. |
| `golden_truth_contexts[].golden_truth_context` | `string` | Chuỗi văn bản gốc trích xuất | Đoạn văn bản trích trực tiếp từ tài liệu nguồn dùng làm bằng chứng đối soát. Rỗng đối với câu `unanswerable`. |
| `golden_truth_contexts[].golden_metadata` | `object` | Tọa độ pháp lý & Định danh tài liệu | Đối tượng định vị vị trí của đoạn `golden_truth_context` tương ứng chỉ gồm 3 trường: `doc_id`, `chapter`, `article`. |
| `difficulty` | `string` | Enum: `easy`, `medium`, `hard` | Tiêu chí đánh giá độ khó của câu hỏi đối với hệ thống RAG. |

---

## 3. Quy Định Phân Loại 5 Dạng Câu Hỏi (`type`)

1. **`direct_lookup`**: Tra cứu trực tiếp thông tin đơn điểm nhắm vào tình huống nghiệp vụ cụ thể.
2. **`multi_hop`**: Tổng hợp suy luận thông tin từ nhiều điều khoản/đoạn văn bản khác nhau (mảng `golden_truth_contexts` chứa nhiều phần tử dict).
3. **`unanswerable`**: Câu hỏi ngoài phạm vi/không có dữ liệu nhằm kiểm thử khả năng từ chối trả lời (chống ảo giác), `golden_truth_contexts: []`.
4. **`ambiguous`**: Câu hỏi mơ hồ/thiếu bối cảnh nhằm kiểm thử khả năng xử lý kịch bản tổng quan.
5. **`adversarial`**: Câu hỏi gài bẫy/chứa giả định sai sự thật nhằm kiểm thử khả năng đính chính và chống tiêm nhiễm (Prompt Injection).

---

## 4. Quy Trình Đánh Giá & Kiểm Soát Chất Lượng (Evaluation Workflow)

### 4.1. Quy Trình Review Chất Lượng Bằng LLM Reviewer Agent
Để đảm bảo tính đúng đắn của dữ liệu trước khi đưa vào kiểm thử hệ thống, tập dữ liệu vàng được phân chia thành các phần để thẩm định song song với tài liệu nguồn.

* **Kiểm tra 5 Checkpoints**: Schema Integrity, Question Realism, Answer Faithfulness, Type Compliance, Context Accuracy.

### 4.2. Đo Lường Chỉ Số Đánh Giá Tự Động (Automatic Metrics Evaluation)
Công cụ đánh giá tự động thực hiện đo lường chất lượng tập Golden Set dựa trên 3 nhóm chỉ số đa kịch bản (Type-Aware Metrics):

1. **`Faithfulness`**: Độ trung thực của `expected_answer` dựa trên danh sách `golden_truth_contexts`.
2. **`Answer Relevancy`**: Mức độ trả lời đúng trọng tâm của câu hỏi `question`.
3. **`Question Quality`**: Độ sắc bén, rõ ràng và tự nhiên của `question`.

### Nguyên Tắc Kiểm Xử Lý Mẫu Dưới Ngưỡng (Threshold Control):
* **Ngưỡng chất lượng tối thiểu**: `Threshold = 0.85 / 1.0`.
* **KHÔNG tự động loại bỏ / xóa bớt mẫu**: Công cụ đánh giá **bảo toàn 100% các sample**, tuyệt đối không tự động xóa mẫu dữ liệu trong Golden Set.
* **Xuất danh sách ID cần cải thiện**: Công cụ tự động liệt kê cụ thể **danh sách các `id` sample bị dưới ngưỡng** trong báo cáo đánh giá để người phát triển review và chỉnh sửa thủ công.
