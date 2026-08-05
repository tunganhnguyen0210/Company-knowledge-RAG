# Quy Chuẩn Đặc Tả Golden Set (Golden Set Specification)

Tài liệu này định nghĩa cấu trúc, quy mô, quy tắc định danh và quy trình kiểm chứng nguồn cho Golden Dataset dùng để đánh giá hệ thống RAG trên Nghị định 01/2021/NĐ-CP.

## 1. JSON Schema chuẩn

```json
{
  "id": "<TYPE_PREFIX>-<3-digit sequence>",
  "type": "<direct_lookup|multi_hop|unanswerable|ambiguous|adversarial>",
  "question": "<string>",
  "expected_answer": "<string>",
  "golden_truth_contexts": [
    {
      "golden_truth_context": "<exact source excerpt>",
      "golden_metadata": {
        "doc_id": "01_2021_ND-CP_283247.md",
        "chapter": "<Chương I..IX>",
        "article": "<Điều 1..101>"
      }
    }
  ],
  "difficulty": "<easy|medium|hard>"
}
```

## 2. Quy tắc trường dữ liệu

| Trường | Kiểu | Ràng buộc |
|---|---|---|
| `id` | string | Khớp regex `^(DL|MH|UA|AMB|ADV)-\d{3}$`; duy nhất toàn bộ tập |
| `type` | string | Một trong 5 loại đã định nghĩa |
| `question` | string | Câu hỏi tiếng Việt tự nhiên, có mục tiêu đánh giá rõ |
| `expected_answer` | string | Câu trả lời chuẩn, không vượt quá bằng chứng của nguồn |
| `golden_truth_contexts` | array | Tối thiểu 1 phần tử với câu trả lời được; bắt buộc `[]` với `unanswerable` |
| `golden_truth_context` | string | Đoạn trích nguyên văn, liên tục, truy vết được trong nguồn |
| `golden_metadata` | object | Chỉ gồm `doc_id`, `chapter`, `article` và phải khớp vị trí thật |
| `difficulty` | string | `easy`, `medium`, hoặc `hard` |

## 3. Năm loại câu hỏi

1. `direct_lookup`: tra cứu trực tiếp một quy định hoặc tình huống đơn điểm.
2. `multi_hop`: phải kết hợp tối thiểu hai quy định/đoạn bằng chứng có vai trò độc lập trong lập luận.
3. `unanswerable`: thông tin không tồn tại trong toàn bộ nguồn; `golden_truth_contexts` bắt buộc rỗng.
4. `ambiguous`: câu hỏi thiếu chủ thể, loại thủ tục hoặc điều kiện cần thiết; đáp án phải nêu điểm cần làm rõ và các nhánh được nguồn hỗ trợ.
5. `adversarial`: chứa giả định sai hoặc gài bẫy; đáp án phải bác bỏ giả định và đưa quy định đúng.

## 4. Quy mô bắt buộc

Mỗi file phải có đúng 20 samples; tổng cộng 100 samples.

| File | Type | Số lượng | Dải ID |
|---|---|---:|---|
| `golden_set_direct_lookup.json` | `direct_lookup` | 20 | `DL-001..DL-020` |
| `golden_set_multi_hop.json` | `multi_hop` | 20 | `MH-001..MH-020` |
| `golden_set_unanswerable.json` | `unanswerable` | 20 | `UA-001..UA-020` |
| `golden_set_ambiguous.json` | `ambiguous` | 20 | `AMB-001..AMB-020` |
| `golden_set_adversarial.json` | `adversarial` | 20 | `ADV-001..ADV-020` |

## 5. Quy ước ID độc lập theo loại

- Mỗi loại có namespace riêng và bắt đầu từ `001`.
- Prefix: `DL` = direct lookup, `MH` = multi-hop, `UA` = unanswerable, `AMB` = ambiguous, `ADV` = adversarial.
- ID đã phát hành không được tái sử dụng cho nội dung khác. Khi loại một sample, ID đó được ghi nhận là retired trong lịch sử/migration report.
- Không dùng lại hệ thống số nguyên xen kẽ giữa các file.
- `id_migration_map.json` lưu ánh xạ ID cũ sang ID mới cho lần chuyển đổi này.

## 6. Quy tắc grounding bắt buộc

Nguồn chuẩn duy nhất cho bộ dữ liệu này là `01_2021_ND-CP_283247.md`.

1. `golden_truth_context` phải là đoạn trích nguyên văn có thể tìm thấy trong đúng Điều đã khai báo.
2. Không được diễn giải, viết lại, ghép các đoạn không liên tục như thể chúng liền nhau, hoặc dùng dấu `...`/`…` để che phần bị lược bỏ. Nếu cần nhiều đoạn không liên tục, tạo nhiều phần tử context riêng.
3. `chapter` và `article` phải được kiểm tra từ cấu trúc thật của nguồn, không suy đoán.
4. `doc_id` phải dùng tên canonical `01_2021_ND-CP_283247.md`.
5. `unanswerable` chỉ được gán khi đã kiểm tra toàn bộ tài liệu và không tìm thấy thông tin trả lời; context phải là `[]`.
6. `expected_answer` không được bổ sung chi tiết chỉ có ở luật/văn bản được dẫn chiếu nhưng không xuất hiện trong nguồn, trừ khi sample chủ đích đánh giá khả năng nhận biết giới hạn nguồn và diễn đạt rõ việc dẫn chiếu.

## 7. Reviewer workflow

Reviewer thực hiện hai lớp kiểm tra:

### 7.1. Schema và phân loại
- Đúng schema, type, difficulty, ID pattern.
- Đúng 20 samples mỗi file và không trùng ID.
- `multi_hop` thực sự cần nhiều bằng chứng; `ambiguous` có nhánh làm rõ; `adversarial` bác bỏ giả định sai.

### 7.2. Grounding và metadata
- Mỗi context là exact substring của nguồn canonical.
- Context nằm trong đúng Điều khai báo.
- Chương được suy ra đúng từ vị trí Điều.
- Không có dấu lược bỏ hoặc văn bản do LLM tự tạo trong context.
- Kết quả review được lưu tại `golden_set_grounding_review.json`.

## 8. Ngưỡng chất lượng

Các chỉ số đánh giá tự động gồm Faithfulness, Answer Relevancy và Question Quality. Ngưỡng tối thiểu là `0.85`. Công cụ không tự động xóa sample dưới ngưỡng; sample phải được sửa và review lại. Việc thay đổi quy mô hoặc loại sample cần có migration record và lý do rõ ràng.

## 9. Trạng thái sau cập nhật ngày 2026-08-05

- 5 file × 20 samples = 100 samples.
- ID đã chuyển sang namespace độc lập theo type.
- 100/100 samples đã vượt qua kiểm tra grounding context và metadata bằng exact-source validation.
- Legacy direct sample ID `65` đã được retire vì không khớp tốt với dạng `direct_lookup`: câu hỏi yêu cầu số ngày trong khi Điều 35 quy định sự kiện tại thời điểm nộp hồ sơ.
