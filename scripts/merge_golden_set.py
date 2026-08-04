"""
Merge all golden_set_part_*.json files into golden_set.json

Usage:
    python scripts/merge_golden_set.py
    python scripts/merge_golden_set.py --parts-dir evaluation --output evaluation/golden_set.json --sort
"""
import argparse
import json
import re
from pathlib import Path


def merge_parts(parts_dir: Path, output_path: Path, sort_by_id: bool = True) -> None:
    # Find all part files, sorted by part number
    part_files = sorted(
        parts_dir.glob("golden_set_part_*.json"),
        key=lambda p: int(re.search(r"part_(\d+)", p.name).group(1)),
    )

    if not part_files:
        print(f"[ERROR] Không tìm thấy file golden_set_part_*.json trong: {parts_dir}")
        return

    merged = []
    for pf in part_files:
        with open(pf, encoding="utf-8") as f:
            items = json.load(f)
        print(f"  + {pf.name}: {len(items)} items")
        merged.extend(items)

    if sort_by_id:
        merged.sort(key=lambda x: (x.get("id") is None, x.get("id") or 0))

    # Check duplicate IDs
    ids = [item.get("id") for item in merged if item.get("id") is not None]
    duplicate_ids = {i for i in ids if ids.count(i) > 1}
    if duplicate_ids:
        print(f"[WARN] Duplicate IDs detected: {sorted(duplicate_ids)}")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)

    print(f"\nMerged {len(part_files)} files -> {len(merged)} items -> {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Merge golden_set_part_*.json into golden_set.json")
    parser.add_argument("--parts-dir", type=Path, default=Path("evaluation"),
                        help="Thư mục chứa các file part (default: evaluation)")
    parser.add_argument("--output", type=Path, default=Path("evaluation/golden_set.json"),
                        help="File output (default: evaluation/golden_set.json)")
    parser.add_argument("--sort", action="store_true", default=True,
                        help="Sắp xếp theo id sau khi gộp (default: True)")
    args = parser.parse_args()

    print(f"Scanning: {args.parts_dir}")
    merge_parts(args.parts_dir, args.output, sort_by_id=args.sort)


if __name__ == "__main__":
    main()
