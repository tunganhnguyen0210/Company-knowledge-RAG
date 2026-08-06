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
        "doc_id": "01_2021_ND-CP_283247.docx",
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
| `golden_metadata` | object | Định nghĩa chi tiết vị trí nguồn (gồm `doc_id`, `chapter`, `article`) |
| `difficulty` | string | `easy`, `medium`, hoặc `hard` |

### 2.1. Định nghĩa các giá trị trong `golden_metadata`

Đối tượng `golden_metadata` chứa vị trí chính xác của đoạn trích ngữ cảnh trong tài liệu nguồn:

* **`doc_id` (string):** Mã định danh file tài liệu chuẩn.
  - *Giá trị hợp lệ:* `01_2021_ND-CP_283247.docx` (file nạp hệ thống) hoặc `01_2021_ND-CP_283247.md` (bản văn bản quy chuẩn).
  - *Quy tắc:* Phải khớp chính xác với mã định danh file được đăng ký trong Document Registry (`data/registry.json`).
* **`chapter` (string):** Tên Chương chứa đoạn trích dẫn.
  - *Định dạng:* `"Chương <Số La Mã>"` (Ví dụ: `"Chương I"`, `"Chương II"`, ..., `"Chương IX"`).
  - *Giá trị:* Phải khớp với Chương thực tế chứa Điều tương ứng trong Nghị định.
* **`article` (string):** Tên Điều cụ thể chứa trích dẫn.
  - *Định dạng:* `"Điều <Số tự nhiên>"` (Ví dụ: `"Điều 1"`, `"Điều 6"`, ..., `"Điều 101"`).
  - *Giá trị:* Phải ghi đúng số Điều cụ thể mà ngữ cảnh được trích xuất.

### 2.2. Định nghĩa các mức độ khó (`difficulty`)

Trường `difficulty` xác định mức độ phức tạp truy xuất và suy luận của câu hỏi:

* **`easy` (Dễ):**
  - Câu hỏi tra cứu đơn điểm (`direct_lookup`), từ khóa rõ ràng, tường minh.
  - Đáp án nằm trọn vẹn trong 1 đoạn văn hoặc 1 Điều duy nhất. Không yêu cầu suy luận phức tạp hay biến đổi từ vựng.
* **`medium` (Trung bình):**
  - Câu hỏi yêu cầu kết hợp thông tin từ 2–3 Điều/Đoạn văn khác nhau (`multi_hop`).
  - Sử dụng từ ngữ diễn đạt khác (paraphrasing), từ đồng nghĩa hoặc câu hỏi tình huống thực tế cấp độ cơ bản.
* **`hard` (Khó):**
  - Câu hỏi chứa bẫy giả định sai (`adversarial`), câu hỏi mơ hồ thiếu điều kiện (`ambiguous`), hoặc câu hỏi nằm ngoài phạm vi tri thức (`unanswerable`).
  - Yêu cầu suy luận nhiều bước, phân tích điều kiện ngoại lệ hoặc tổng hợp kiến thức liên Chương/Điều phức tạp.

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

### 5.1. Schema `id_migration_map.json`

| Trường | Kiểu | Ràng buộc |
|---|---|---|
| `schema_version` | integer | Phiên bản schema của artifact; hiện tại là `1` |
| `migration_commit` | string | SHA (rút gọn) của commit chứa ID lịch sử trước khi chuyển đổi |
| `old_to_new` | object | Ánh xạ ID số cũ (string key) sang ID mới đã phát hành, hoặc `null` nếu ID đó bị retire; mỗi giá trị không phải `null` phải là một ID `DL-*` duy nhất đã phát hành trong bộ dữ liệu |
| `retired` | array | Danh sách các bản ghi retire; mỗi phần tử có `old_id` (string, khớp một key có giá trị `null` trong `old_to_new`), `status` (`"retired"`), và `reason` (string giải thích lý do loại bỏ) |

Mỗi key trong `old_to_new` có giá trị `null` bắt buộc phải có đúng một bản ghi tương ứng trong `retired` với `old_id` khớp key đó.

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

#### Schema `golden_set_grounding_review.json`

| Trường | Kiểu | Ràng buộc |
|---|---|---|
| `schema_version` | integer | Phiên bản schema của artifact; hiện tại là `1` |
| `canonical_doc_id` | string | Tên file nguồn canonical, `01_2021_ND-CP_283247.md` |
| `canonical_sha256` | string | SHA-256 hex digest của nội dung file canonical tại thời điểm review (đọc bằng `read_text(encoding="utf-8")`) |
| `dataset_sha256` | string | SHA-256 hex digest của toàn bộ 100 case đã gộp, tuần tự hóa bằng `json.dumps(cases, ensure_ascii=False, sort_keys=True, separators=(",", ":"))` |
| `validated_cases` | integer | Số case đã kiểm tra; phải bằng `100` khi review đạt |
| `validated_contexts` | integer | Tổng số context đã kiểm tra trên toàn bộ case; phải bằng `130` khi review đạt |
| `cases` | array | Danh sách bản ghi kết quả kiểm tra theo từng case |
| `cases[].case_id` | string | ID case đã kiểm tra, ví dụ `AMB-014` |
| `cases[].status` | string | `"passed"` nếu mọi context của case đều `exact_source=true` và `coordinate_match=true`; ngược lại `"failed"` |
| `cases[].contexts` | array | Danh sách bản ghi kết quả kiểm tra theo từng context của case |
| `cases[].contexts[].context_index` | integer | Vị trí (0-based) của context trong `golden_truth_contexts` |
| `cases[].contexts[].context_sha256` | string | SHA-256 hex digest của `golden_truth_context` (UTF-8) |
| `cases[].contexts[].exact_source` | boolean | `true` nếu context là substring nguyên văn của toàn bộ nội dung canonical |
| `cases[].contexts[].coordinate_match` | boolean | `true` nếu context là substring nguyên văn của đúng slice Điều đã khai báo trong `golden_metadata` |

## 8. Ngưỡng chất lượng

Các chỉ số đánh giá tự động gồm Faithfulness, Answer Relevancy và Question Quality. Ngưỡng tối thiểu là `0.85`. Công cụ không tự động xóa sample dưới ngưỡng; sample phải được sửa và review lại. Việc thay đổi quy mô hoặc loại sample cần có migration record và lý do rõ ràng.

## 9. Trạng thái sau cập nhật ngày 2026-08-05

- 5 file × 20 samples = 100 samples.
- ID đã chuyển sang namespace độc lập theo type; xem `id_migration_map.json` cho ánh xạ đầy đủ.
- Legacy direct sample ID `65` đã được retire vì không khớp tốt với dạng `direct_lookup`: câu hỏi yêu cầu số ngày trong khi Điều 35 quy định sự kiện tại thời điểm nộp hồ sơ.
- Cùng ngày 2026-08-05, bộ dữ liệu đã được tái phát hành theo phương án đã duyệt, với hai điểm trim tại `AMB-014` context index `1` và `AMB-019` context index `1`. Cả hai context nêu trên đã bị cắt đúng tại ranh giới Điều đã khai báo (điểm cắt là nhãn `# Chương IX` cho `AMB-014` và `# Chương IV` cho `AMB-019`, đánh dấu nơi Điều được khai báo trong `golden_metadata` kết thúc và Điều/Chương kế tiếp bắt đầu); không có ID hay metadata nào khác bị thay đổi.
- Bản review grounding tái tạo sau lần phát hành này (`golden_set_grounding_review.json`) chứng minh 100/100 case và 130/130 context đều đạt `exact_source=true` và `coordinate_match=true` bằng exact-source validation.
