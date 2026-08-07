# Hierarchical Retrieval (Sibling Expansion) — Báo cáo triển khai & đo lường

> **Ngày:** 2026-08-07 · **Trạng thái:** đã bật trên production (`company_knowledge_v2`) · **Rollback:** 1 biến môi trường
> Thay thế phần "Parent-Child → Generation" trong [`LEVEL1-CHUNKING-ENRICHMENT-HANDOFF.md`](./LEVEL1-CHUNKING-ENRICHMENT-HANDOFF.md) (hướng cũ đã bị bác bỏ, xem Mục 2).

> **Cơ chế hoạt động chi tiết từng bước:** [`CHUNKING-AND-RETRIEVAL-FLOW.md`](./CHUNKING-AND-RETRIEVAL-FLOW.md).
> Tài liệu này tập trung vào **tại sao chọn thiết kế này và đo được gì**, không giải thích lại cơ chế.

---

## 0. Đọc trước — từ viết tắt & cách đọc bảng

### 0.1 Hai chỉ số chính khác nhau chỗ nào

| Chỉ số | Đo cái gì | Đạt 100% nghĩa là |
|---|---|---|
| **`coordinate_recall`** | Retrieval có **tìm ra đúng Điều** không | Mọi Điều mà golden yêu cầu đều xuất hiện trong kết quả |
| **`evidence_recall`** | Đoạn văn bằng chứng có **tái tạo được nguyên văn** không | Ghép các chunk cùng toạ độ lại ra đúng đoạn golden |

**`coordinate_recall` luôn ≥ `evidence_recall`.** Khoảng cách giữa hai chỉ số chính là nhóm case **"tìm đúng Điều nhưng chỉ lấy được một mảnh của nó"** — và đó chính là thứ toàn bộ dự án này nhắm tới.

### 0.2 Tên các "arm" trong thí nghiệm A/B

Mỗi **arm** là một cấu hình chạy trên **cùng một index, cùng 100 câu hỏi**. Chỉ khác nhau ở hai nút vặn:
- **`RETRIEVAL_LIMIT`** — lấy bao nhiêu chunk sau khi trộn hạng (5, 9 hay 13)
- **Sibling expansion** — có bù thêm sibling cho trọn Điều hay không

| Arm | `RETRIEVAL_LIMIT` | Expansion | Đọc là | Vai trò trong thí nghiệm |
|---|---|---|---|---|
| **A** | 5 | ❌ tắt | *baseline* | Mốc so sánh — chính là hệ thống trước khi sửa |
| **B1** | 9 | ❌ tắt | *"flat-9"* | **Đối chứng giả thuyết rẻ tiền**: chỉ cần lấy nhiều chunk hơn thì có tốt lên không? |
| **B2** | 13 | ❌ tắt | *"flat-13"* | Như B1 nhưng lấy nhiều hơn nữa |
| **C** | 5 | ✅ bật | *chỉ expansion* | Cô lập tác dụng riêng của expansion |
| **D1** | 9 | ✅ bật | *flat-9 + expansion* | **⭐ Cấu hình được chọn cho production** |
| **D2** | 13 | ✅ bật | *flat-13 + expansion* | Biến thể tốn context hơn |

> **Vì sao phải có arm B?** Nếu chỉ so C với A rồi kết luận "expansion tốt", ta không loại trừ được giải thích tầm thường: *"nó tốt chỉ vì nhét nhiều chữ hơn vào prompt."* Arm B nhét thêm chữ **bằng cách tầm thường** (tăng limit) để làm mốc đối chứng ở cùng ngân sách.

### 0.3 "Điều kiện thắng" — tiêu chí dùng xuyên tài liệu

Expansion chỉ được coi là thắng nếu:

> **Đạt recall cao hơn arm B ở cùng hoặc ít context hơn.**

Cao hơn nhưng tốn nhiều context hơn thì **không tính là thắng** — vì chỉ cần tăng `RETRIEVAL_LIMIT` là ai cũng làm được điều đó, không cần viết code mới.

### 0.4 Đơn vị và thuật ngữ khác

| Ký hiệu | Nghĩa |
|---|---|
| **pp** | *percentage point* — chêch lệch tuyệt đối giữa hai tỷ lệ. 71.1% → 84.8% là **+13.7pp**, không phải +19% |
| **P95** | Phân vị 95 — 95% request nhanh hơn con số này. Đo "đuôi chậm", không phải trung bình |
| **scramble control** | Nhét thêm chunk **ngẫu nhiên** thay vì sibling đúng. Nếu recall vẫn tăng ⇒ lợi ích chỉ do "thêm chữ", không do thiết kế |
| **hiệu suất khai thác** | Trong số Điều đã tìm ra đúng, bao nhiêu % lấy được trọn bằng chứng = `evidence_recall / coordinate_recall` |
| **all-or-nothing** | Luật: bù sibling thì phải lấy **trọn** một Điều, hoặc bỏ hẳn. Lý do ở Mục 2(b) |
| **orphan** | Chunk nằm trong Qdrant nhưng **không có** trong registry — xóa được |
| **missing** | Có trong registry nhưng **thiếu** trong Qdrant — phải re-ingest, **tuyệt đối không xóa** |

---

## 1. Vấn đề & trần cải thiện đã đo

Baseline `reports/rag_evaluation/2026-08-06_golden100_clean-baseline`: **coordinate_recall 81.6%**, **evidence_recall 71.1%**.

Khoảng cách ~10pp giữa hai chỉ số này là nhóm case **tìm đúng Điều nhưng trượt đoạn bằng chứng**. Đếm chính xác: **14 case**. Kiểm chứng bằng script offline: **14/14 recover được** nếu có trọn section.

> Trần lý thuyết: evidence_recall 71.1% → ~81.6%. **coordinate_recall không thể tăng** bằng cơ chế này — 8 case còn lại thất bại vì không tìm ra Điều nào đúng, đó là địa phận Query Transformation.

## 2. Hai phát hiện định hình thiết kế

**(a) Phải trả về sibling chunk, KHÔNG nhét `parent_text` vào prompt.**
`evaluation/metrics.py::score_retrieval_case` gom `hit.chunk.text` của **các SearchHit được trả về**, nhóm theo `(doc_id, chapter, article)`, sort theo `position`. Gắn thêm `parent_text` vào context **không làm metric nhúc nhích**. Hệ quả kèm theo: sibling là chunk thật, có coordinates thật → **citable hợp lệ**, nên không cần tách khối "evidence" riêng và **không phải đụng `src/prompts/` một dòng nào**.

**(b) `"".join` không dấu phân cách ⇒ luật ALL-OR-NOTHING.**
`chunker._split` đảm bảo các piece nối lại đúng bằng `section.strip()`. Thiếu **một sibling ở giữa** thì `"".join` dán piece 1 vào piece 3 → golden span không bao giờ khớp. Vì vậy mở rộng một parent phải **lấy trọn hoặc bỏ hẳn**; cắt bớt cho vừa budget = tốn token, thu về 0 recall.

**Đính chính hiện trạng khi khảo sát:** candidate pool thật là **20** (không phải 50) vì `.env` không có `RERANKER_MODEL` → `reranker=None` → `candidate_limit = max(limit*4, limit)`. Và lấy sibling là **miễn phí**: `search()` đã scroll toàn bộ collection cho BM25 (`lexical_candidate_limit=500` > 297 chunk), nên toàn bộ chunk đã nằm sẵn trong RAM mỗi query — không cần round trip mới, không đổi `ChunkStore` protocol.

## 3. Đã xây dựng gì

| File | Nội dung |
|---|---|
| `src/retrieval/hierarchical.py` *(mới)* | `ExpansionConfig`, `parent_key()`, `expand_with_siblings()` — hàm thuần, dùng chung cho cả 2 store |
| `src/storage/reconcile.py` *(mới)* | `reconcile()`, `purge_orphans()` — đối chiếu index ↔ registry (xem Mục 6) |
| `src/domain/schemas.py` | `Chunk.parent_id`, `parent_child_count`, `child_index`; hằng `RAPTOR_SECTION_PREFIX` |
| `src/ingestion/chunker.py` | Sinh parent identity trong vòng lặp section sẵn có (~6 dòng) |
| `src/retrieval/qdrant_store.py` | Gọi expansion; `list_indexed_documents()`, `purge_documents()` |
| `src/retrieval/memory_store.py` | Y hệt — bắt buộc, nếu không toàn bộ test dùng MemoryChunkStore sẽ không chạm code này |
| `src/retrieval/base.py` | Mở rộng `ChunkStore` protocol |
| `src/settings.py`, `.env.example` | 5 cờ `HIERARCHICAL_*`, mặc định TẮT |
| `src/api/app.py`, `src/evaluation/cli.py` | Nối dây DI; đưa config vào `artifact_fingerprint` để các arm phân biệt được |
| `src/cli.py`, `pyproject.toml` | Lệnh `company-rag-reconcile` |

**Thuật toán:** greedy theo rank (không phải ngưỡng coverage — ngưỡng coverage tính trên top-K *về mặt cấu trúc* không thể kích hoạt cho section lớn, vốn là section cần nhất). Gom họ theo `parent_id`, fallback khoá suy diễn + ràng buộc dải `position` liên tục cho index cũ chưa có `parent_id`. Bỏ qua RAPTOR node. Fail-closed khi họ không đủ thành viên.

**Test:** 242 pass, ruff sạch, mypy sạch 52 file. Gồm test khẳng định **cờ tắt ⇒ output y hệt input**, test `"".join` tái tạo đúng section, test all-or-nothing, và test contract chéo 2 store.

## 4. Kết quả đo

### 4.1 Đối chứng offline (0 API call)

| | evidence_recall | mean chunk | mean chars |
|---|---|---|---|
| baseline | 0.7115 | 5.00 | 4 542 |
| **scramble control** | **0.7115 (+0.0000)** | 9.52 | 8 222 |
| sibling expansion | **0.8125 (+0.1010)** | 9.09 | 7 786 |

Scramble nhét **nhiều chunk hơn và nhiều ký tự hơn** mà recall **không nhúc nhích**. ⇒ Lợi ích đến từ *chunk nào* (hoàn thiện section), không phải *lượng chữ*.

Sweep cũng cho thấy **`max_parents` mới là ràng buộc, không phải budget**: cùng số parent, budget 8 000 vs 16 000 ra kết quả y hệt; 2→3 parent thì +6.9pp → +10.1pp.

### 4.2 Sáu arm online (cùng một index, content hash `5b3a8d00f8fabba4`)

*(Nhắc lại định nghĩa arm ở Mục 0.2. `limit` = `RETRIEVAL_LIMIT`; `exp` = sibling expansion.)*

| arm | limit | exp | coord | evid | Δ evid so với A | hiệu suất khai thác | hits | chars |
|---|:---:|:---:|---|---|---|---|---|---|
| **A** baseline | 5 | ❌ | 0.8156 | 0.7115 | — | 87.2% | 5.00 | 4 542 |
| **B1** flat-9 | 9 | ❌ | 0.8604 | 0.7667 | +5.5pp | 89.1% | 9.00 | 8 226 |
| **B2** flat-13 | 13 | ❌ | 0.9083 | 0.8260 | +11.5pp | 90.9% | 13.00 | 11 782 |
| **C** chỉ exp | 5 | ✅ | 0.8156 | 0.8125 | +10.1pp | **99.6%** | 9.12 | 7 814 |
| **⭐ D1** flat-9 + exp | 9 | ✅ | 0.8604 | 0.8479 | +13.6pp | 98.5% | 12.89 | 11 312 |
| **D2** flat-13 + exp | 13 | ✅ | 0.9083 | **0.8760** | +16.5pp | 96.4% | 16.42 | 14 471 |

### Cách đọc bảng này

**(1) Đọc theo cột `coord`:** chỉ có **3 giá trị** — 0.8156, 0.8604, 0.9083 — và chúng bám chặt theo `limit` (5 / 9 / 13), **hoàn toàn không đổi khi bật expansion**. A và C cùng 0.8156; B1 và D1 cùng 0.8604; B2 và D2 cùng 0.9083.

> ⇒ **Expansion không tìm ra Điều mới bao giờ.** Nó chỉ việc với Điều đã tìm được. Muốn tăng `coordinate_recall` phải dùng cơ chế khác.

**(2) Đọc theo cột `hiệu suất khai thác`:** các arm không expansion đứng ~87–91% — tức **bỏ phí gần 10%** số Điều đã tìm đúng. Arm C đẩy lên **99.6%**, gần như vắt kiệt.

**(3) So cặp ở cùng ngân sách — đây mới là phép thử thật:**

| cặp so | recall | context | kết luận |
|---|---|---|---|
| **C** vs **B1** | 0.8125 vs 0.7667 → **+4.6pp** | 7 814 vs 8 226 → **ít hơn 5%** | C thắng |
| **D1** vs **B2** | 0.8479 vs 0.8260 → **+2.2pp** | 11 312 vs 11 782 → **ít hơn 4%** | D1 thắng |

Điều kiện thắng (Mục 0.3) đạt ở **hai mốc ngân sách độc lập** — recall cao hơn **và** tốn ít context hơn, chứ không phải đánh đổi.

**(4) Kết luận:** hai cơ chế **bổ sung nhau, không cạnh tranh**.

| | tăng `RETRIEVAL_LIMIT` | sibling expansion |
|---|---|---|
| Tìm thêm Điều mới | ✅ | ❌ |
| Vắt kiệt Điều đã tìm | ❌ (bỏ phí ~10%) | ✅ (99.6%) |

Ghép cả hai mới thắng toàn diện — **đó là lý do chọn D1** cho production. Không chọn D2 vì nó tốn thêm 28% context để đổi +2.8pp, và hiệu suất khai thác còn **tụt** (98.5% → 96.4%) — dấu hiệu đã vượt điểm tối ưu.

### 4.3 Cấu hình production cuối cùng

`company_knowledge_v2`, `RETRIEVAL_LIMIT=9`, expansion on (3 parents / 8 000 chars):

| | baseline | production | Δ |
|---|---|---|---|
| evidence_recall | 0.7115 | **0.8440** | **+13.3pp** |
| coordinate_recall | 0.8156 | 0.8568 | +4.1pp |
| citation_coverage | 0.9383¹ | 0.9381 | ~0 |
| citation_validity | 1.0000 | 1.0000 | — |
| abstention_accuracy | 1.0000 | 1.0000 | — |

¹ đo trên arm A cùng phiên, không phải con số 0.918 của báo cáo 06/08 (khác lần chạy).

**evidence_recall theo nhóm:**

| nhóm | baseline | production |
|---|---|---|
| `hard` | 0.5256 | **0.7692** |
| `multi_hop` | 0.6792 | **0.8500** |
| `ambiguous` | 0.5917 | **0.6917** |
| `direct_lookup` | 0.7250 | **0.8889** |
| `adversarial` | 0.8500 | **0.9500** |

Artifact: `reports/prod_final/summary.json`.

### 4.4 Lần chạy sạch 100/100 trên v2 (2026-08-07) — số chính thức

`reports/prod_clean/run1/`. `status=complete`, `evaluated_cases=100`, `errors=[]`, `baseline_eligible=true`.
Thay thế con số ở Mục 4.3 (đo trên 97 case do 3 case rớt mạng).

| | baseline 06/08 | **sạch 100/100 07/08** | Δ |
|---|---|---|---|
| evidence_recall | 0.7115 | **0.8479** | **+13.6pp** |
| coordinate_recall | 0.8156 | **0.8604** | +4.5pp |
| citation_coverage | 0.9383¹ | 0.9317 | −0.7pp |
| citation_validity | 1.0000 | 1.0000 | — |
| abstention_accuracy | 1.0000 | 1.0000 | — |

Khoảng cách coordinate − evidence thu từ **10.5pp xuống 1.3pp** — đúng điều cơ chế này nhắm tới, và gần sát trần lý thuyết ở Mục 1.

**Theo nhóm:**

| nhóm | coordinate | evidence | citation_coverage |
|---|---|---|---|
| `direct_lookup` | 0.9000 | 0.9000 | 1.0000 |
| `multi_hop` | 0.8333 | 0.8500 | 0.9625 |
| `ambiguous` | 0.7583 | 0.6917 | 1.0000 |
| `adversarial` | 0.9500 | 0.9500 | **0.6958** ← vẫn yếu, là vấn đề prompt |
| `unanswerable` | — | — | 1.0000 (abstention 1.0000) |
| `hard` (độ khó) | 0.7436 | 0.7692 | 0.9423 |

Latency lần này: end-to-end mean 2858ms / P95 4301ms; generation mean **1350ms** / P95 2025ms; retrieval mean 1509ms / P95 2734ms.

## 5. Độ chắc chắn — cập nhật 2026-08-07

**(a) Đã đóng: lần chạy sạch 100/100.** Cảnh báo cũ ("chưa có lần chạy nào sạch 100/100 trên v2", 3 case rớt do Qdrant Cloud ngắt kết nối) **không còn**. Ba lần chạy liên tiếp trong phiên 07/08 đều `status=complete`, `errors=[]`, 100/100 case. Nguyên nhân đã vá tận gốc bằng `_read_with_retry()` (Mục 8) — log lần chạy `run1` cho thấy đúng 2 lần `ResponseHandlingException` được retry và hồi phục; trước đây mỗi lần như vậy là một case rớt.

**(b) Chi phí latency — đã đo được phân phối. Con số cũ "+224ms mean / +635ms P95" là giả tạo do chỉ có 1 mẫu.**

*Đối chứng chạy liền nhau trong cùng phiên 07/08* (cùng mạng, cùng collection, cách nhau ~15 phút):

| lần chạy | arm | limit | exp | coord | evid | gen mean | gen P95 | e2e mean | e2e P95 | citation_cov |
|---|---|:---:|:---:|---|---|---|---|---|---|---|
| `armA1` | **A** | 5 | ❌ | 0.8156 | 0.7115 | 1 361ms | 1 869ms | 2 809ms | 4 279ms | 0.9117 |
| `run1` | **D1** | 9 | ✅ | 0.8604 | 0.8479 | 1 350ms | 2 025ms | 2 858ms | 4 301ms | 0.9317 |
| `base1` | **D1** *(lặp lại)* | 9 | ✅ | 0.8604 | 0.8479 | 1 394ms | 2 094ms | 2 850ms | 4 181ms | 0.9342 |

> **Arm A tái lập baseline 06/08 chính xác tới 4 chữ số** (0.8156 / 0.7115). Đây là control mạnh: nó chứng minh phép đo đủ ổn định để so sánh, và hai lần chạy D1 (`run1`, `base1`) cho **retrieval metric trùng khít nhau** — retrieval là tất định, chỉ latency và generation dao động.

*Phân phối generation latency qua các lần chạy (khác phiên):*

| arm | số mẫu | các mẫu mean (ms) | biên độ mean | các mẫu P95 (ms) | biên độ P95 |
|---|:---:|---|---|---|---|
| **A** baseline | 2 | 1 663 · 1 361 | 302ms | 2 827 · 1 869 | 958ms |
| **D1** production | 4 | 1 886 · 1 666 · 1 350 · 1 394 | **536ms** | 3 462 · 2 305 · 2 025 · 2 094 | **1 437ms** |

> Đọc bảng này như sau: **cả hai mẫu của arm A (1 663 và 1 361) đều nằm GỮA dải của D1 (1 350–1 886)**. Nếu expansion thực sự làm chậm hệ, mọi mẫu D1 phải nằm bên phải mọi mẫu A — thực tế chúng trộn lẫn hoàn toàn.

**Kết luận:**
- **Mean: không có chi phí đo được.** Đối chứng trong phiên cho **+11ms** (1 361 → 1 350/1 394) — nhỏ hơn biến động giữa hai lần chạy D1 với nhau (44ms). Biên độ giữa các phiên (1 350–1 886ms, **536ms**) lớn gấp ~50 lần hiệu ứng.
- **P95: có vẻ +~190ms, nhưng chưa tách được khỏi nhiễu.** Hướng này hợp lý về cơ chế (prompt dài hơn ⇒ đuôi dài hơn), nhưng biên độ P95 giữa các lần chạy D1 là **1 437ms** (2 025–3 462) — vẫn lớn hơn hiệu ứng nhiều lần. Muốn chốt con số phải có hàng chục mẫu.
- **citation_coverage không hồi quy** — production (0.9317 / 0.9342) thực ra **cao hơn** baseline (0.9117). Nghi ngờ cũ (0.9242 vs 0.9381) đúng là nhiễu.
- **SLA latency vẫn còn rất nhiều room:** e2e P95 4.3s so với 11.5s của baseline 06/08 — phần lớn cải thiện này đến từ hạ tầng/mạng chứ không phải expansion, nhưng điểm chính là expansion **không đẩy hệ ra khỏi ngân sách**.

**Cái chắc chắn:** lợi ích retrieval — đo **6 lần** trên 3 collection khác nhau, evidence_recall luôn rơi vào 0.844–0.848, và hai lần chạy gần nhất trùng khít đến từng chữ số (0.8479). Có scramble control + arm B loại trừ giả thuyết "chỉ là thêm chữ", và arm A chạy lại hôm nay tái lập đúng baseline cũ.

Artifact: `reports/prod_clean/{run1,base1,armA1}/`.

## 6. Bug production phát hiện ngoài dự kiến & cách vá

Khi verify collection mới, phát hiện `company_knowledge` chứa **Nghị định 01/2021 hai lần**:

```
01_2021_ND-CP_283247.docx   243 chunks   doc_id 99bfa7cc-…   ❌ KHÔNG có trong registry
01_2021_ND-CP_283247.md     244 chunks   doc_id ecb49b09-…   ✅ có trong registry
```

Cả hai đều mang `coordinates.doc_id = 01_2021_ND-CP_283247.md` nên không phân biệt được bằng tọa độ.

**Nguyên nhân gốc:** `replace_document()` chỉ xóa theo `document_id` mà caller đã biết. Khi một document rời registry, chunk của nó thành vùng chết — không liệt kê được, không thay thế được, không xóa được, nhưng vẫn tranh slot candidate mỗi query. **Hệ thống không có cách nào biết chúng tồn tại.**

**Đã vá:** `src/storage/reconcile.py` + lệnh `company-rag-reconcile`, phân biệt rõ **orphan** (trong index, không trong registry → xóa được) với **missing** (trong registry, thiếu trong index → phải re-ingest, tuyệt đối không xóa). Mặc định chỉ báo cáo; `--purge` mới xóa và còn một bước xác nhận. `purge_orphans()` đọc lại report ngay trước khi xóa nên report cũ không thể nới rộng phạm vi.

```bash
company-rag-reconcile            # báo cáo
company-rag-reconcile --purge    # xóa orphan, có hỏi xác nhận
```

## 7. Trạng thái hạ tầng hiện tại

```
company_knowledge_v2   ← .env đang trỏ vào (production)
  6 docs / 297 chunks / 0 orphan            ✅ sạch
  297/297 chunk có parent_id + parent_child_count
  content hash canonical = 5b3a8d00f8fabba4 (giống hệt bản cũ — ranh giới chunk không đổi)

company_knowledge      ← ảnh chụp rollback, GIỮ ĐẾN 2026-08-09
  7 docs / 540 chunks / 243 orphan
```

**Cố ý không dọn orphan trong collection cũ** — nó đang là phao rollback; sửa vào đó là làm hỏng chính cái phao. Sau 48h ổn định, cách sạch nhất là **xóa cả collection**.

**Rollback:** đổi `QDRANT_COLLECTION` về `company_knowledge` và `HIERARCHICAL_EXPANSION_ENABLED=false`, `RETRIEVAL_LIMIT=5`. Có unit test khẳng định khi tắt cờ thì `search()` trả về y hệt input.

Backup registry/uploads production trước khi re-ingest: `scratchpad/prod-backup/` (đã đối chiếu: `id`/`version`/`content_hash`/`status` giống hệt, chỉ khác `uploaded_at`).

## 8. Việc còn lại

Cập nhật 2026-08-07 (phiên sau).

### Đã đóng

- [x] **Chạy lại eval sạch 100/100 trên v2** — `reports/prod_clean/run1/`, `status=complete`, `evaluated_cases=100`, `errors=[]`, `baseline_eligible=true`. Số chính thức ở Mục 4.4.
- [x] **Lấy phân phối latency để kết luận Mục 5(b)** — chạy thêm 1 lần D1 lặp lại (`base1`) và 1 lần arm A thật (`armA1`, phải hoán đổi `.env` vì biến môi trường bị `.env` ghi đè — xem cạm bẫy bên dưới). Kết luận: **mean không có chi phí đo được (+11ms)**, P95 có vẻ +~190ms nhưng chưa tách được khỏi nhiễu. Con số cũ "+224ms/+635ms" là giả tạo do 1 mẫu.
- [x] **Retry cho Qdrant reads** — `_read_with_retry()` trong `qdrant_store.py`: 3 lần, backoff 0.5→1→2s, bao 4 read path (dense query, lexical scroll, document scroll, collection scroll). Phân biệt transient (`ResponseHandlingException`, 5xx) với lỗi client (4xx → không replay). **Write path cố ý không đụng.** Hiệu quả đã quan sát được: lần chạy sạch trên gặp đúng 2 lần đứt kết nối giữa chừng và hồi phục cả hai — trước đó mỗi lần như vậy là một case rớt.
- [x] **Gỡ `Chunk.parent_text`** — xóa luôn cả `ChunkingConfig.parent_child_enabled`/`parent_max_chars`, `_parent_text_for()`, 2 settings và 2 biến `CHUNK_PARENT_CHILD_ENABLED`/`CHUNK_PARENT_MAX_CHARS`. Payload Qdrant cũ còn key `parent_text` vẫn load bình thường (pydantic mặc định bỏ qua field thừa) → **không cần re-index**.
- [x] **Cập nhật `RAG-ROADMAP-ADVANCED.md`** — lên `v1.5`: bảng KPI Mục 5 thêm cột đo 2026-08-07, sửa action item Parent-Child ở Cấp Độ 1, đánh dấu Ưu Tiên 1 chunking đã xong.
- [x] **Commit** — `c43280e` (đợt hierarchical + reconcile).
- [x] **`.gitignore`** — đã vá: chặn cả `reports/`, `data/registry_*.json`, `data/uploads_*/`.

### Còn lại

- [ ] **Xóa `company_knowledge`** sau 2026-08-09 nếu v2 ổn định (chưa tới hạn).
- [x] `citation_coverage` nhóm `adversarial` — **ĐÃ SỬA** bằng prompt `answer_v4`: 69.6% → **97.5%**, overall 93.2% → **99.5%**. Xem Mục 9.
- [ ] `coordinate_recall` vẫn là trần: 86.0%, nhóm `ambiguous` 75.8%. Địa phận của **data isolation theo domain** + **Query Transformation**, expansion không giúp được.

### Hai cạm bẫy vận hành phát hiện khi chạy lại eval

**1. `.env` ghi đè biến môi trường, không phải ngược lại.** `Settings.settings_customise_sources` ([`src/settings.py`](../../src/settings.py)) trả về `(init, dotenv, env, secrets)` — `dotenv` **trước** `env`, ngược với mặc định của pydantic-settings. Nên `HIERARCHICAL_EXPANSION_ENABLED=false rag-eval ...` **không có tác dụng gì** mà cũng không báo lỗi — lần chạy `base1` tưởng là arm A nhưng thực ra vẫn là production. Cách duy nhất phát hiện sau khi chạy: so `configuration_fingerprints.runtime` trong `manifest.json` — trùng nhau nghĩa là override không ăn. Muốn đổi arm phải sửa `.env` thật, có backup + `trap ... EXIT INT TERM` để khôi phục.

**2. `rag-eval e2e` trần luôn fail preflight.** `_preflight_index` mặc định tìm registry theo tên `01_2021_ND-CP_283247.docx`, nhưng registry chỉ có bản `.md`. **Gợi ý trong thông báo lỗi là sai** — làm theo sẽ ingest bản sao thứ hai dưới `source_name` khác, đúng bằng bug orphan ở Mục 6. Lệnh đúng:

```bash
rag-eval e2e --ingest data/extracted/01_2021_ND-CP_283247.md --output-root <dir>
```

`--ingest` chỉ để tra tên; content hash khớp registry nên `_ingest_bytes` đi nhánh `idempotent_skip` — **không re-embed, không tốn API**. Chỉ `--force-reingest` mới thực sự ingest lại.

---

## 9. Prompt `answer_v4` — vá citation_coverage (2026-08-07)

### 9.1 Ba nguyên nhân, không phải một

Mổ 15 case có `citation_coverage < 1.0` trong `reports/prod_clean/run1/`:

| # | mẫu lỗi | số case | ví dụ |
|---|---|---|---|
| 1 | **Câu phán quyết mở đầu trống marker** | 12 | `ADV-001`: "Không đúng." — câu sau có `[C2]`, câu này không |
| 2 | **Marker gộp `[C3, C4]`** | 3 marker | Metric dùng regex `\[C\d+\]` — `[C3, C4]` **không khớp**, nên câu bị tính là không trích dẫn dù thực tế có |
| 3 | **Câu khẳng định tài liệu thiếu thông tin** | 1 | `MH-001`: "Tài liệu không đề cập đến cơ chế phản đối..." |

Nguyên nhân #2 đáng chú ý: **prompt cũ dạy sai ở hai nơi** — cả `answer_v2.yaml` ("kèm marker [C1], [C2]") lẫn `GroundedAnswer.answer` field description trong `generation/service.py`, mà description này được instructor đưa thẳng vào schema cho model. Sửa một nơi là không đủ.

### 9.2 Đã sửa gì

| File | Nội dung |
|---|---|
| `src/prompts/answer_v4.yaml` *(mới, thay `answer_v2.yaml`)* | 6 quy tắc trích dẫn + **Quy tắc 0** cho abstention |
| `src/prompts/answer_v4.py` | Đổi tên từ `answer_v2.py`; `PROMPT_VERSION` đi vào artifact để phân biệt được các lần chạy |
| `src/generation/service.py` | Sửa `GroundedAnswer.answer` description; thêm `normalize_citation_markers()` |

`normalize_citation_markers()` viết lại `[C1, C3]` → `[C1][C3]` bằng code. Lý do không chỉ dựa vào prompt: đây là lỗi **định dạng thuần cơ học**, code cho kết quả tất định còn prompt chỉ là best-effort. Nó **không đổi số được trích**, và trường `citations` (thứ quyết định `citation_validity`) không đi qua hàm này.

### 9.3 `answer_v3` — một lần thất bại có ghi lại

v3 sửa được cả 3 nguyên nhân (citation_coverage → **1.0000**, adversarial → **1.0000**) nhưng **làm sập `abstention_accuracy` từ 1.0000 xuống 0.4500**.

Quy tắc "câu khẳng định tài liệu thiếu thông tin cũng phải gắn marker" (nhắm nguyên nhân #3) bị model tổng quát hoá sang cả câu hỏi **hoàn toàn không trả lời được**: thay vì đi nhánh abstention, nó viết `"Tài liệu không đề cập đến X [C1]"` kèm citations không rỗng — mà `answer = ... if citations else ABSTENTION` nên answer không còn khớp chính xác chuỗi `ABSTENTION`. 11/20 case `unanswerable` rớt.

v4 vá bằng cách đặt abstention lên **Quy tắc 0, xét trước tiên, đè lên mọi quy tắc trích dẫn**, và gọi thẳng tên câu sai đó là cấm. Có test khoá thứ tự ưu tiên này (`test_abstention_outranks_the_cite_every_sentence_rule`).

### 9.4 Kết quả

Cả ba lần đều `status=complete`, 100/100 case, 0 lỗi, cùng collection `company_knowledge_v2`.

| | v2 (production cũ) | v3 (hỏng) | **v4** |
|---|---|---|---|
| citation_coverage | 0.9317 | 1.0000 | **0.9950** |
| — `adversarial` | 0.6958 | 1.0000 | **0.9750** |
| abstention_accuracy | 1.0000 | **0.4500** ⚠️ | **1.0000** |
| citation_validity | 1.0000 | 1.0000 | **1.0000** |
| coordinate_recall | 0.8604 | 0.8604 | 0.8604 |
| evidence_recall | 0.8479 | 0.8479 | 0.8479 |

Retrieval **không đổi một chữ số** qua cả ba — đúng như mong đợi, prompt không chạm tầng retrieval, và cũng là thêm một bằng chứng retrieval là tất định.

**Độ tin cậy:** `citation_coverage` ở v2 dao động 0.9117–0.9383 qua 3 lần chạy; 0.9950 của v4 nằm **ngoài hẳn** dải đó, nên hiệu ứng là thật chứ không phải nhiễu. Các metric generation khác vẫn chỉ có n=1 cho v4.

### 9.5 Còn sót

`ADV-019` vẫn mở đầu bằng "Không đúng." trống marker — 1/100 case, là nhiễu tuân thủ của model chứ không còn là lỗi hệ thống (12 → 1). **Cố ý không vá bằng code**: tự động chèn marker mà model không khẳng định sẽ làm rỗng nghĩa của `citation_validity`.

Artifact: `reports/prompt_v3/run1/` (thất bại), `reports/prompt_v4/run1/` (đạt).
