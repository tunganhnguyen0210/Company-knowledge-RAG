import argparse
import json
import os
import re
from pathlib import Path

HIGH_THRESHOLD = 0.85

def evaluate_question_quality(question, item_type):
    score = 1.0
    if re.search(r'\b(Điều|Khoản|Mục|Nghị định)\s+\d+', question, re.IGNORECASE):
        score -= 0.3
    if re.search(r'nghị định này (nói gì|quy định gì|là gì)', question, re.IGNORECASE):
        score -= 0.4
    if len(question.strip()) < 8:
        score -= 0.3
    return max(0.0, score)

def evaluate_faithfulness(answer, context, item_type):
    if item_type == "unanswerable":
        if any(keyword in answer.lower() for keyword in ["không có trong", "không được quy định", "chưa có thông tin", "không cụ thể"]):
            return 1.0
        return 0.4

    if item_type == "adversarial":
        if any(keyword in answer.lower() for keyword in ["không chính xác", "sai sự thật", "không đúng", "vẫn được áp dụng"]):
            return 1.0
        return 0.5

    if item_type == "ambiguous":
        if "tùy thuộc" in answer.lower() or "tổng quan" in answer.lower() or len(answer) > 20:
            return 1.0

    if not context:
        return 0.0

    ans_words = set(re.findall(r'\w+', answer.lower()))
    ctx_words = set(re.findall(r'\w+', context.lower()))

    if not ans_words:
        return 0.0

    overlap = ans_words.intersection(ctx_words)
    overlap_ratio = len(overlap) / len(ans_words)

    return min(1.0, max(0.0, overlap_ratio))

def evaluate_answer_relevancy(question, answer, item_type):
    if not answer or len(answer.strip()) < 5:
        return 0.0

    if item_type in ["unanswerable", "adversarial", "ambiguous"]:
        return 1.0

    q_words = set(re.findall(r'\w+', question.lower()))
    ans_words = set(re.findall(r'\w+', answer.lower()))

    stopwords = {"là", "gì", "như", "thế", "nào", "có", "được", "không", "những", "cho", "tôi", "hỏi", "quy", "định", "về"}
    q_keywords = q_words - stopwords

    if not q_keywords:
        return 1.0

    overlap = q_keywords.intersection(ans_words)
    ratio = len(overlap) / len(q_keywords)

    return min(1.0, max(0.5, ratio + 0.3))

def evaluate_item(item):
    q = item.get("question", "")
    ans = item.get("expected_answer", "")
    ctx = item.get("ground_truth_context", "")
    item_type = item.get("type", "direct_lookup")

    q_quality = evaluate_question_quality(q, item_type)
    faithfulness = evaluate_faithfulness(ans, ctx, item_type)
    answer_rel = evaluate_answer_relevancy(q, ans, item_type)

    overall = round((q_quality * 0.25) + (faithfulness * 0.45) + (answer_rel * 0.30), 4)

    return {
        "id": item.get("id"),
        "type": item_type,
        "question": q,
        "metrics": {
            "question_quality": round(q_quality, 4),
            "faithfulness": round(faithfulness, 4),
            "answer_relevancy": round(answer_rel, 4),
            "overall_score": overall
        }
    }

def run_evaluation(dataset_file, threshold, report_file):
    with open(dataset_file, encoding="utf-8") as f:
        items = json.load(f)

    results = []
    passed_items = []
    failed_items = []
    total_score = 0.0

    type_stats = {}

    for item in items:
        res = evaluate_item(item)
        score = res["metrics"]["overall_score"]
        total_score += score
        item_type = res["type"]

        if item_type not in type_stats:
            type_stats[item_type] = {"total": 0, "passed": 0, "failed": 0}
        type_stats[item_type]["total"] += 1

        if score >= threshold:
            res["status"] = "PASS"
            passed_items.append(res)
            type_stats[item_type]["passed"] += 1
        else:
            res["status"] = "FAIL"
            failed_items.append(res)
            type_stats[item_type]["failed"] += 1

        results.append(res)

    avg_score = round(total_score / len(items), 4) if items else 0.0
    pass_rate = round((len(passed_items) / len(items)) * 100, 2) if items else 0.0
    failed_ids = [item["id"] for item in failed_items]

    summary = {
        "dataset": str(dataset_file),
        "threshold": threshold,
        "total_test_cases": len(items),
        "passed": len(passed_items),
        "failed": len(failed_items),
        "pass_rate_percentage": pass_rate,
        "average_overall_score": avg_score,
        "type_breakdown": type_stats,
        "failed_item_ids": failed_ids
    }

    report_data = {
        "summary": summary,
        "below_threshold_items": failed_items,
        "details": results
    }

    os.makedirs(os.path.dirname(report_file), exist_ok=True)
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report_data, f, ensure_ascii=False, indent=2)

    print("=" * 65)
    print("TYPE-AWARE RAG GOLDEN SET EVALUATION REPORT")
    print("=" * 65)
    print(f"Dataset File            : {dataset_file}")
    print(f"Quality Threshold       : {threshold}")
    print(f"Total Samples Preserved : {summary['total_test_cases']}")
    print(f"Passed Samples          : {summary['passed']} ({pass_rate}%)")
    print(f"Below Threshold Samples : {summary['failed']}")
    print(f"Average Overall Score   : {avg_score} / 1.0")
    print("-" * 65)
    print(f"BELOW THRESHOLD SAMPLE IDs: {failed_ids if failed_ids else 'None (All samples passed)'}")
    print("=" * 65)

def main():
    parser = argparse.ArgumentParser(description="Evaluate Golden Set Quality & List Below-Threshold Sample IDs")
    parser.add_argument("--dataset", type=Path, default=Path("evaluation/golden_set.json"), help="Path to golden set json")
    parser.add_argument("--threshold", type=float, default=HIGH_THRESHOLD, help="Quality score threshold (default: 0.85)")
    parser.add_argument("--report", type=Path, default=Path("reports/golden_eval_report.json"), help="Path to output report json")
    args = parser.parse_args()

    run_evaluation(args.dataset, args.threshold, args.report)

if __name__ == "__main__":
    main()
