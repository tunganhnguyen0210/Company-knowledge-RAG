import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

GOLDEN_PATH = Path("evaluation/golden_set.json")
EVAL_DIR = Path("evaluation")

TYPES = ["direct_lookup", "multi_hop", "unanswerable", "ambiguous", "adversarial"]

def main():
    if not GOLDEN_PATH.exists():
        print("Không tìm thấy file golden_set.json!")
        return

    with open(GOLDEN_PATH, "r", encoding="utf-8") as f:
        golden_data = json.load(f)

    # Gom nhóm theo type
    type_groups = {t: [] for t in TYPES}
    other_groups = {}

    for item in golden_data:
        item_type = item.get("type", "").strip()
        if item_type in type_groups:
            type_groups[item_type].append(item)
        else:
            if item_type not in other_groups:
                other_groups[item_type] = []
            other_groups[item_type].append(item)

    print(f"Tổng số sample trong golden_set.json: {len(golden_data)}\n")

    # Xuất từng file json tương ứng cho 5 loại
    for t in TYPES:
        out_file = EVAL_DIR / f"golden_set_{t}.json"
        items = type_groups[t]
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
        print(f"-> Đã tạo {out_file.name}: {len(items)} sample")

    # Nếu có type khác ngoài 5 type chuẩn
    for t, items in other_groups.items():
        out_file = EVAL_DIR / f"golden_set_{t}.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
        print(f"-> Đã tạo {out_file.name} (khác): {len(items)} sample")

if __name__ == "__main__":
    main()
