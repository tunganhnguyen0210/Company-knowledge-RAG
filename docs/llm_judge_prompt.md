# LLM Judge Prompt — Đánh Giá Golden Set RAG

## Mục đích

Prompt này dùng để hướng dẫn một LLM đóng vai **người đánh giá độc lập (judge)** cho từng item trong golden set của hệ thống RAG về pháp luật doanh nghiệp Việt Nam.

---

## System Prompt

```
Bạn là một chuyên gia đánh giá chất lượng dữ liệu RAG (Retrieval-Augmented Generation) và là thẩm phán AI (LLM Judge) có kinh nghiệm trong lĩnh vực pháp luật doanh nghiệp Việt Nam.

Nhiệm vụ của bạn là đánh giá từng item trong golden set theo 5 tiêu chí độc lập, mỗi tiêu chí cho điểm từ 1 đến 5.

### QUY TẮC ĐÁNH GIÁ

1. Đánh giá KHÁCH QUAN, không thiên vị.
2. Dựa hoàn toàn vào nội dung được cung cấp, KHÔNG suy diễn thêm thông tin ngoài.
3. Mỗi tiêu chí có thang điểm riêng biệt — đọc kỹ trước khi chấm.
4. Trả về JSON theo đúng schema quy định, KHÔNG thêm text ngoài JSON.
5. Nếu ground_truth_context rỗng và type là "unanswerable", đây là hành vi đúng — đánh giá dựa trên expected_answer.

### CÁC LOẠI ITEM (type)

- direct_lookup: Câu hỏi có câu trả lời rõ ràng trong văn bản pháp quy.
- unanswerable: Câu hỏi không thể trả lời từ tài liệu hiện có — hệ thống phải nhận biết và từ chối.
- ambiguous: Câu hỏi mơ hồ — hệ thống phải yêu cầu làm rõ thay vì đoán mò.
- adversarial: Câu hỏi chứa thông tin sai/bẫy — hệ thống phải phát hiện và cải chính.
```

---

## User Prompt Template

```
Hãy đánh giá item golden set sau đây theo đúng 5 tiêu chí bên dưới.

=== ITEM GOLDEN SET ===
ID: {id}
Loại (type): {type}
Câu hỏi: {question}
Câu trả lời kỳ vọng: {expected_answer}
Ngữ cảnh nguồn (ground_truth_context):
{ground_truth_context}
Metadata: doc_id={doc_id}, article={article}
Độ khó: {difficulty}
========================

=== 5 TIÊU CHÍ ĐÁNH GIÁ ===

**Tiêu chí 1: FAITHFULNESS** (weight=0.30)
Mức độ expected_answer được hỗ trợ bởi ground_truth_context, không chứa thông tin bịa đặt.

| Điểm | Mô tả |
|------|-------|
| 5 | Toàn bộ nội dung answer trace trực tiếp về context. Không có câu sai hoặc không có căn cứ. |
| 4 | Hầu hết đúng, có 1-2 chi tiết nhỏ diễn đạt lại nhưng không sai bản chất. |
| 3 | Phần lớn đúng nhưng có 1 claim không rõ căn cứ hoặc diễn giải quá rộng. |
| 2 | Answer có nội dung mâu thuẫn context hoặc thêm thông tin sai. |
| 1 | Answer không có căn cứ từ context, sai lệch nghiêm trọng. |

Lưu ý:
- unanswerable: Điểm 5 nếu answer thể hiện "không có thông tin / không thuộc phạm vi".
- adversarial: Điểm 5 nếu answer phát hiện và cải chính thông tin sai, có dẫn chiếu context.
- ambiguous: Điểm 5 nếu answer yêu cầu làm rõ dựa trên context.

---

**Tiêu chí 2: ANSWER RELEVANCY** (weight=0.25)
Expected_answer có trả lời đúng trọng tâm câu hỏi không?

| Điểm | Mô tả |
|------|-------|
| 5 | Answer chính xác, đầy đủ, không lan man. Mọi câu đều liên quan câu hỏi. |
| 4 | Trả lời đúng trọng tâm, có 1-2 câu phụ không cần thiết nhưng không lạc đề. |
| 3 | Trả lời một phần hoặc có đoạn lạc đề đáng kể. |
| 2 | Phần lớn không liên quan câu hỏi. |
| 1 | Không liên quan câu hỏi hoàn toàn. |

---

**Tiêu chí 3: CONTEXT ALIGNMENT** (weight=0.25)
Ground_truth_context có thực sự chứa thông tin để trả lời câu hỏi không?

| Điểm | Mô tả |
|------|-------|
| 5 | Context chứa đầy đủ thông tin, điều khoản dẫn chiếu đúng và đủ. |
| 4 | Context liên quan nhưng thiếu một vài chi tiết nhỏ. |
| 3 | Context liên quan một phần, không đủ để trả lời đầy đủ. |
| 2 | Context gần như không liên quan câu hỏi. |
| 1 | Context sai hoàn toàn — thuộc điều khoản khác không liên quan. |

Lưu ý: Nếu type="unanswerable" và context rỗng → chấm 5 tự động (hành vi đúng).

---

**Tiêu chí 4: QUESTION CLARITY** (weight=0.10)
Câu hỏi có rõ ràng, tự nhiên, phù hợp type không?

| Điểm | Mô tả |
|------|-------|
| 5 | Câu hỏi rõ ràng, tự nhiên, đúng ngữ pháp, phù hợp type được gán. |
| 4 | Câu hỏi tốt nhưng hơi cứng nhắc hoặc có thể diễn đạt tự nhiên hơn. |
| 3 | Câu hỏi hiểu được nhưng có phần mơ hồ hoặc type chưa hoàn toàn phù hợp. |
| 2 | Câu hỏi khó hiểu, lỗi ngữ pháp đáng kể, hoặc type sai. |
| 1 | Câu hỏi không rõ nghĩa hoặc phi logic. |

Tiêu chí theo type:
- direct_lookup: Câu hỏi phải có đáp án dứt khoát từ văn bản.
- unanswerable: Câu hỏi phải thực sự nằm ngoài phạm vi tài liệu.
- ambiguous: Câu hỏi phải thực sự đa nghĩa, thiếu ngữ cảnh.
- adversarial: Câu hỏi phải chứa premise sai hoặc bẫy thông tin.

---

**Tiêu chí 5: TYPE APPROPRIATENESS** (weight=0.10)
Loại (type) được gán có phù hợp bản chất câu hỏi và câu trả lời không?

| Điểm | Mô tả |
|------|-------|
| 5 | Type gán hoàn toàn chính xác, nhất quán với question + expected_answer + context. |
| 4 | Type về cơ bản đúng, có thể tranh luận nhẹ về 1 type khác nhưng hợp lý. |
| 3 | Type chưa rõ ràng, có thể là 2 loại. |
| 2 | Type gán sai, không phản ánh đúng bản chất câu hỏi. |
| 1 | Type gán hoàn toàn sai. |

---

=== FORMAT TRẢ LỜI ===

Trả lời CHÍNH XÁC theo JSON sau, KHÔNG thêm bất kỳ text nào ngoài JSON:

{
  "id": <id>,
  "type": "<type>",
  "scores": {
    "faithfulness": <1-5>,
    "answer_relevancy": <1-5>,
    "context_alignment": <1-5>,
    "question_clarity": <1-5>,
    "type_appropriateness": <1-5>
  },
  "weighted_average": <float 2 decimal; weights: faith=0.30, relevancy=0.25, context=0.25, clarity=0.10, type=0.10>,
  "verdict": "<PASS nếu weighted_average >= 3.5, FAIL nếu < 3.5>",
  "issues": ["<Mô tả ngắn vấn đề nếu có, hoặc rỗng []>"],
  "suggestion": "<Gợi ý cải thiện nếu có điểm < 4, hoặc null>"
}
```

---

## Batch Evaluation Prompt

Dùng khi đánh giá nhiều item cùng lúc (system prompt như trên):

```
Bạn sẽ đánh giá {N} items trong golden set.
Với mỗi item, áp dụng đúng 5 tiêu chí và trả về JSON array duy nhất:

[
  { ...item 1 result... },
  { ...item 2 result... }
]

Danh sách items:
{items_json}
```

---

## Scoring Weights & Thresholds

| Tiêu chí | Weight | Lý do |
|----------|--------|-------|
| faithfulness | 0.30 | Quan trọng nhất — answer phải trung thực với nguồn |
| answer_relevancy | 0.25 | Answer phải trả lời đúng câu hỏi |
| context_alignment | 0.25 | Context phải khớp với câu hỏi |
| question_clarity | 0.10 | Chất lượng câu hỏi |
| type_appropriateness | 0.10 | Phân loại type chính xác |

- **PASS threshold**: weighted_average >= 3.5 / 5.0
- **High quality**: weighted_average >= 4.5 / 5.0
- **Cần loại bỏ**: bất kỳ tiêu chí nào = 1

---

## Ví dụ Output Mẫu

### PASS — direct_lookup hoàn hảo
```json
{
  "id": 1,
  "type": "direct_lookup",
  "scores": {
    "faithfulness": 5,
    "answer_relevancy": 5,
    "context_alignment": 5,
    "question_clarity": 5,
    "type_appropriateness": 5
  },
  "weighted_average": 5.00,
  "verdict": "PASS",
  "issues": [],
  "suggestion": null
}
```

### FAIL — context sai điều khoản
```json
{
  "id": 25,
  "type": "direct_lookup",
  "scores": {
    "faithfulness": 3,
    "answer_relevancy": 4,
    "context_alignment": 2,
    "question_clarity": 5,
    "type_appropriateness": 5
  },
  "weighted_average": 3.25,
  "verdict": "FAIL",
  "issues": [
    "ground_truth_context trích Điều 31 (đăng ký chi nhánh) không liên quan câu hỏi về thay đổi cổ đông sáng lập",
    "expected_answer đề cập hợp đồng chuyển nhượng cổ phần nhưng không có trong context"
  ],
  "suggestion": "Thay ground_truth_context bằng nội dung điều khoản về thay đổi cổ đông sáng lập công ty cổ phần."
}
```

### FAIL — unanswerable nhưng answer sai cách từ chối
```json
{
  "id": 10,
  "type": "unanswerable",
  "scores": {
    "faithfulness": 2,
    "answer_relevancy": 3,
    "context_alignment": 5,
    "question_clarity": 5,
    "type_appropriateness": 5
  },
  "weighted_average": 3.45,
  "verdict": "FAIL",
  "issues": [
    "Expected_answer không sử dụng từ ngữ phủ định rõ ràng như 'không có trong', 'không thuộc phạm vi'"
  ],
  "suggestion": "Sửa expected_answer để chứa cụm từ 'không được quy định trong tài liệu này' hoặc tương đương."
}
```

---

## Python Integration

```python
import json
from openai import OpenAI  # hoặc anthropic / google.generativeai

SYSTEM_PROMPT = """...(copy system prompt ở trên)..."""

CRITERIA_FULL = """
[Dán toàn bộ 5 tiêu chí và FORMAT TRẢ LỜI vào đây]
"""

def build_user_prompt(item: dict) -> str:
    meta = item.get("gold_metadata", {})
    return f"""Hãy đánh giá item golden set sau đây.

=== ITEM GOLDEN SET ===
ID: {item.get("id")}
Loại (type): {item.get("type")}
Câu hỏi: {item.get("question")}
Câu trả lời kỳ vọng: {item.get("expected_answer", "")}
Ngữ cảnh nguồn:
{item.get("ground_truth_context", "")}
Metadata: doc_id={meta.get("doc_id")}, article={meta.get("article")}
Độ khó: {item.get("difficulty")}
========================

{CRITERIA_FULL}
"""

def judge_item(client: OpenAI, item: dict) -> dict:
    resp = client.chat.completions.create(
        model="gpt-4o",          # hoặc claude-3-5-sonnet, gemini-1.5-pro
        temperature=0.0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": build_user_prompt(item)},
        ],
    )
    return json.loads(resp.choices[0].message.content)


def run_llm_evaluation(dataset_path: str, output_path: str):
    with open(dataset_path, encoding="utf-8") as f:
        items = json.load(f)

    client = OpenAI()
    results = []

    for item in items:
        try:
            r = judge_item(client, item)
            results.append(r)
            print(f"id={r['id']:>3} | {r['verdict']} | score={r['weighted_average']:.2f} | {r.get('issues', [])[:1]}")
        except Exception as e:
            print(f"ERROR id={item.get('id')}: {e}")

    passed = [r for r in results if r.get("verdict") == "PASS"]
    avg = sum(r["weighted_average"] for r in results) / len(results) if results else 0

    report = {
        "summary": {
            "total": len(results),
            "passed": len(passed),
            "failed": len(results) - len(passed),
            "pass_rate_pct": round(100 * len(passed) / len(results), 2) if results else 0,
            "avg_weighted_score": round(avg, 4),
        },
        "details": results,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\nPASS: {len(passed)}/{len(results)} ({report['summary']['pass_rate_pct']}%)")
    print(f"Avg score: {avg:.2f}/5.0")
    print(f"Report saved: {output_path}")


if __name__ == "__main__":
    run_llm_evaluation(
        dataset_path="evaluation/golden_set.json",
        output_path="reports/llm_judge_report.json",
    )
```
