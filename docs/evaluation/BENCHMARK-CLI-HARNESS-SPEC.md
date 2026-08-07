# Chuẩn Kiến Trúc & Quy Trình Benchmark Các Phương Pháp Cải Tiến RAG

> **Mã tài liệu:** `SPEC-BENCHMARK-HARNESS`  
> **Trạng thái:** 🟢 Draft / Standard Specification  
> **Áp dụng cho:** Tất cả các Phase nâng cấp RAG (Ingestion, Enrichment, Retrieval, Query Transform, Generation)  
> **Vị trí:** `docs/evaluation/BENCHMARK-CLI-HARNESS-SPEC.md`

---

## 1. Mục Tiêu & Phạm Vi

Tài liệu này quy định **Chuẩn Kiến Trúc Tự Động Hóa Kiểm Thử (CLI Test Harness Standard)** để thử nghiệm, đo đạc và so sánh các phương pháp cải tiến RAG theo từng Phase.

Mục tiêu chính:
1. Đảm bảo mọi phương pháp cải tiến đều có **Baseline chuẩn** làm đối chứng.
2. Đóng gói các phương pháp thành các Strategy độc lập, có giao diện (Interface) thống nhất trong `src/`.
3. Cung cấp **CLI Interface** tập trung để chạy thử nghiệm từng phương pháp trên **Golden Set**.
4. Tự động hóa việc xuất **Báo cáo Chênh lệch ($\Delta$ Report)** giữa Baseline và Phương pháp Cải tiến.

---

## 2. Nguyên Tắc Kiến Trúc Cốt Lõi (Core Architectural Principles)

```
                       ┌────────────────────────────────────────┐
                       │           Golden Set Dataset           │
                       └──────────────────┬─────────────────────┘
                                          │
                                          ▼
                       ┌────────────────────────────────────────┐
                       │       CLI Test Harness Interface       │
                       └──┬──────────────────────────────────┬──┘
                          │                                  │
                          ▼                                  ▼
               ┌──────────────────────┐           ┌──────────────────────┐
               │   Baseline Strategy  │           │  Candidate Strategy  │
               └──────────┬───────────┘           └──────────┬───────────┘
                          │                                  │
                          ▼                                  ▼
               ┌──────────────────────┐           ┌──────────────────────┐
               │   Baseline Report    │           │   Candidate Report   │
               └──────────┬───────────┘           └──────────┬───────────┘
                          │                                  │
                          └─────────────────┬────────────────┘
                                            │
                                            ▼
                               ┌────────────────────────┐
                               │  Delta Comparison Report│
                               └────────────────────────┘
```

1. **Modular Strategy Isolation:** Mỗi phương pháp (kể cả Baseline) phải được hiện thực thành một class/module riêng biệt, kế thừa từ một Interface chung duy nhất của Domain đó.
2. **Zero Side-Effect Switching:** Việc chuyển đổi qua lại giữa Baseline và các Candidate Strategy chỉ dựa vào tham số CLI hoặc biến cấu hình, không sửa đổi logic lõi của hệ thống đang chạy.
3. **Single Ground Truth Standard:** Tất cả các thử nghiệm so sánh điểm số đều phải thực thi trên cùng một phiên bản Golden Set cố định.
4. **Reproducibility:** Mọi lần chạy thử nghiệm đều lưu log, cấu hình thực thi và báo cáo chi tiết theo dạng file JSON có timestamp/versioning.

---

## 3. Chuẩn Tổ Chức Code Module Trong `src/` (Generic Code Structure)

Với mỗi Domain thành phần trong RAG (ví dụ: `retrieval`, `ingestion`, `query_transform`, `enrichment`), cấu trúc thư mục phải tuân theo chuẩn sau:

```text
src/<domain_name>/
├── __init__.py
├── base.py                   # Định nghĩa Abstract Base Class (Interface chung)
├── registry.py               # Registry quản lý & lookup các Strategy theo Key tên
├── baseline.py               # Implementation của Phương pháp Baseline gốc
└── strategies/               # Thư mục chứa các phương pháp cải tiến
    ├── __init__.py
    ├── strategy_a.py         # Phương pháp cải tiến A
    └── strategy_b.py         # Phương pháp cải tiến B
```

### 3.1 Quy Tắc Interface (`base.py`)
- Định nghĩa rõ các input/output schema chuẩn bằng Pydantic hoặc Type Hints.
- Phương thức chính của Strategy bắt buộc phải `async` hoặc thread-safe.

### 3.2 Quy Tắc Registry (`registry.py`)
- Cung cấp cơ chế đăng ký (`register`) và khởi tạo (`get`) Strategy theo tên đại diện dạng chuỗi (`str`).
- Mặc định key `"baseline"` luôn trỏ về `BaselineStrategy`.

---

## 4. Chuẩn Quy Trình Chạy Test & Benchmark Qua CLI Interface

### 4.1 Khởi Tạo Baseline Score
Trước khi thực hiện đánh giá bất kỳ phương pháp cải tiến nào thuộc một Phase:
1. Đảm bảo cấu hình hệ thống ở trạng thái Baseline gốc.
2. Thực thi CLI Benchmark trên Golden Set:
   ```bash
   rag-eval --domain <domain_name> --strategy baseline --out-report reports/eval/<phase_id>_baseline.json
   ```
3. Lưu trữ `baseline.json` làm mốc so sánh cố định.

### 4.2 Thực Thi Benchmark Candidate Strategy
Khi thử nghiệm một phương pháp cải tiến mới:
1. Hiện thực Strategy mới dưới dạng module kế thừa `base.py` và đăng ký vào `registry.py`.
2. Thực thi CLI Benchmark với Strategy tương ứng:
   ```bash
   rag-eval --domain <domain_name> --strategy <candidate_key> --out-report reports/eval/<phase_id>_<candidate_key>.json
   ```

### 4.3 Xuất Báo Cáo Đối Chiếu ($\Delta$ Comparison Report)
Thực thi lệnh so sánh tự động 2 file kết quả:
```bash
rag-eval compare --baseline reports/eval/<phase_id>_baseline.json --candidate reports/eval/<phase_id>_<candidate_key>.json
```

---

## 5. Chuẩn Báo Cáo Đầu Ra ($\Delta$ Metric Matrix Standard)

Báo cáo so sánh giữa Baseline và Candidate Strategy phải hiển thị đầy đủ các nhóm chỉ số sau:

| Nhóm Chỉ Số | Tên Metric Trực Tiếp | Ý Nghĩa / Mục Tiêu | Ngưỡng Chấp Nhận ($\Delta$) |
|---|---|---|---|
| **Retrieval Accuracy** | `coordinate_recall`<br>`evidence_recall` | Tỷ lệ tìm đúng đoạn văn bản chứa đáp án chuẩn trong Golden Set. | Tăng $\ge 5\%$ so với Baseline |
| **Generation Quality** | `faithfulness`<br>`answer_relevancy` | Độ trung thực chống hallucination và độ khớp với câu hỏi. | Không suy giảm ($\ge 0\%$) |
| **Citation Adherence** | `citation_coverage`<br>`citation_validity` | Tỷ lệ gắn thẻ nguồn trích dẫn inline và tính chính xác của nguồn. | Tăng hoặc giữ nguyên |
| **Performance SLA** | `latency_p95`<br>`latency_mean` | Độ trễ xử lý ở bách phân vị 95 và trung bình. | Overhead không vượt quá SLA Budget |
| **Efficiency** | `total_tokens`<br>`estimated_cost` | Tổng lượng token tiêu thụ và chi phí ước tính. | Tối ưu trong ngân sách cho phép |

### Định Dạng Output Mẫu Của CLI Compare:
```text
================================================================================
                    BENCHMARK DELTA COMPARISON REPORT
================================================================================
Domain: retrieval | Phase: Phase 3 | Candidate Strategy: mmr_diversification
Golden Set Size: 100 cases | Timestamp: 2026-08-07T00:40:00Z

METRIC                      BASELINE        CANDIDATE       DELTA           STATUS
--------------------------------------------------------------------------------
coordinate_recall (overall)  81.6%           88.2%           +6.6%           🟢 PASSED
coordinate_recall (hard)     56.4%           69.2%           +12.8%          🟢 PASSED
evidence_recall (ambiguous) 59.2%           68.5%           +9.3%           🟢 PASSED
citation_coverage           91.8%           94.0%           +2.2%           🟢 PASSED
latency_p95                 11.50s          11.62s          +120ms          🟢 WITHIN SLA
--------------------------------------------------------------------------------
OVERALL DECISION: ACCEPT CANDIDATE STRATEGY (Satisfies Phase Definition of Done)
================================================================================
```

---

## 6. Tiêu Chí Nghiệm Thu Một Strategy Mới (Definition of Done)

Một phương pháp cải tiến chỉ được coi là hoàn tất và đủ điều kiện merge vào nhánh chính khi:
- [ ] Implement đầy đủ interface theo `base.py` và có unit test riêng cho logic nội tại (coverage $\ge 80\%$).
- [ ] Chạy thành công CLI Benchmark trên 100% test cases của Golden Set không phát sinh lỗi runtime.
- [ ] Báo cáo $\Delta$ Compare đạt đủ các chỉ số kỳ vọng (Target Metrics) đặt ra trong Plan mà không vi phạm vi phạm SLA Latency/Cost.
- [ ] Phương pháp Baseline vẫn hoạt động bình thường khi chuyển đổi ngược lại (`--strategy baseline`).
