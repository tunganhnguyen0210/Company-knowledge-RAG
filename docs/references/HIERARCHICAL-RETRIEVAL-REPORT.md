# Hierarchical Retrieval (Sibling Expansion) — Báo cáo triển khai & đo lường

> **Ngày:** 2026-08-07 · **Trạng thái:** đã bật trên production (`company_knowledge_v2`) · **Rollback:** 1 biến môi trường
> Thay thế phần "Parent-Child → Generation" trong [`LEVEL1-CHUNKING-ENRICHMENT-HANDOFF.md`](./LEVEL1-CHUNKING-ENRICHMENT-HANDOFF.md) (hướng cũ đã bị bác bỏ, xem Mục 2).

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

| arm | coord | evid | Δ | hiệu suất khai thác | hits | chars |
|---|---|---|---|---|---|---|
| A baseline | 0.8156 | 0.7115 | — | 87.2% | 5.00 | 4 542 |
| B1 flat-9 | 0.8604 | 0.7667 | +5.5pp | 89.1% | 9.00 | 8 226 |
| B2 flat-13 | 0.9083 | 0.8260 | +11.5pp | 90.9% | 13.00 | 11 782 |
| C expansion | 0.8156 | 0.8125 | +10.1pp | **99.6%** | 9.12 | 7 814 |
| **D1 flat-9 + exp** | 0.8604 | 0.8479 | +13.6pp | 98.5% | 12.89 | 11 312 |
| D2 flat-13 + exp | 0.9083 | **0.8760** | +16.5pp | 96.4% | 16.42 | 14 471 |

**Điều kiện thắng đạt ở hai mốc ngân sách độc lập:**
- C (7 814 chars) 0.8125 **vs** B1 (8 226 chars) 0.7667 → hơn +4.6pp với **ít hơn 5%** context
- D1 (11 312 chars) 0.8479 **vs** B2 (11 782 chars) 0.8260 → hơn +2.2pp với **ít hơn 4%** context

**Hai cơ chế bổ sung nhau, không cạnh tranh.** Expansion đẩy hiệu suất khai thác lên 99.6% (vắt kiệt Điều đã tìm được) nhưng **không tạo được Điều mới**. Tăng `retrieval_limit` tìm thêm Điều nhưng bỏ phí ~10%. Ghép cả hai mới thắng toàn diện — đó là lý do chọn D1.

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

## 5. ⚠️ Những gì KHÔNG chắc chắn

**(a) Lần chạy production rớt 3/100 case** (`DL-012`, `DL-014`, `UA-012`) — Qdrant Cloud ngắt kết nối, `status=incomplete`. Số ở Mục 4.3 tính trên **97 case**. Lỗi hạ tầng lặp lại suốt phiên (1 case lần trước, 3 case lần này), không phải lỗi code, nhưng **chưa có lần chạy nào sạch 100/100 trên v2**.

**(b) Chi phí latency chưa kết luận được — báo cáo trước đó đã nói quá.**

| | A baseline (đo cặp) | D1 (đo cặp) | production (lần khác) |
|---|---|---|---|
| gen latency mean | 1 663ms | 1 886ms | **1 666ms** |
| gen latency P95 | 2 827ms | 3 462ms | **2 305ms** |

Cặp A/B cho +224ms mean / +635ms P95, nhưng lần chạy production cùng cấu hình lại **thấp hơn cả baseline**. Biến động giữa các lần chạy **lớn ngang hiệu ứng đo được** ⇒ không đủ cơ sở khẳng định hồi quy latency. Muốn kết luận phải chạy nhiều lần lấy phân phối. Tương tự với citation_coverage (0.9242 lần đo cặp vs 0.9381 lần production — cùng nằm trong nhiễu).

**Cái chắc chắn:** lợi ích retrieval — đo 4 lần trên 3 collection khác nhau đều nhất quán 0.844–0.848, có scramble control + arm B loại trừ giả thuyết "chỉ là thêm chữ".

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

- [ ] **Chạy lại eval cho sạch 100/100** trên v2 (3 case rớt do mạng), và lấy phân phối latency nhiều lần để kết luận Mục 5(b)
- [ ] **Xóa `company_knowledge`** sau 2026-08-09 nếu v2 ổn định
- [ ] **Chưa commit gì** — toàn bộ thay đổi còn ở working tree
- [ ] **`.gitignore` có lỗ hổng**: chỉ chặn đúng path production (`data/registry.json`, `data/uploads/`, `reports/rag_evaluation/`), nên `data/registry_*_dev.json`, `data/uploads_*_dev/`, `reports/hier_ab/`, `reports/prod_final/` đang untracked và **sẽ bị `git add -A` quét nhầm**
- [ ] **Cập nhật `RAG-ROADMAP-ADVANCED.md`** Mục 5 với KPI mới (evidence_recall 71.1% → 84.4%)
- [ ] Cân nhắc **retry cho `qdrant_store.search()`** — lỗi ngắt kết nối lặp lại nhiều lần trong phiên
- [ ] `Chunk.parent_text` giờ **không còn ai đọc** (hướng cũ đã bỏ) — cân nhắc gỡ ở đợt dọn dẹp sau
