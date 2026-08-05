import argparse
import json
import os
import re
from pathlib import Path

def clean_answer(text):
    text = re.sub(r'^Điều\s+\d+\.[^\n]*', '', text).strip()
    text = re.sub(r'^\d+\.\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'\s+\d+\.\s*', ' ', text)
    text = re.sub(r'\s+[a-zđ]\)\s*', ' ', text)
    text = re.sub(r'^[a-zđ]\)\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'\s+', ' ', text).strip()
    
    sentences = re.split(r'(?<=[.!?])\s+', text)
    if len(sentences) > 3:
        text = " ".join(sentences[:3])
    return text

def parse_markdown_legal(file_path):
    with open(file_path, encoding="utf-8") as f:
        lines = f.readlines()
        
    current_part = None
    current_chapter = None
    current_section = None
    
    articles = []
    current_article_title = None
    current_article_num = None
    current_article_lines = []
    
    for line in lines:
        stripped = line.strip()
        
        if re.match(r'^#\s+Phần\s+', stripped, re.IGNORECASE):
            current_part = stripped.replace('#', '').strip()
            continue
            
        if re.match(r'^#\s+Chương\s+', stripped, re.IGNORECASE):
            current_chapter = stripped.replace('#', '').strip()
            current_section = None
            continue
            
        if re.match(r'^##\s+Mục\s+', stripped, re.IGNORECASE):
            current_section = stripped.replace('##', '').strip()
            continue
            
        match_art = re.match(r'^###\s+Điều\s+(\d+)\.\s*(.*)$', stripped, re.IGNORECASE)
        if match_art:
            if current_article_title and current_article_lines:
                articles.append({
                    "part": current_part,
                    "chapter": current_chapter,
                    "section": current_section,
                    "article_num": current_article_num,
                    "title": current_article_title,
                    "body": "\n".join(current_article_lines).strip()
                })
            current_article_num = match_art.group(1)
            current_article_title = match_art.group(2).strip()
            current_article_lines = [f"Điều {current_article_num}. {current_article_title}"]
        else:
            if current_article_title is not None:
                current_article_lines.append(stripped)
                
    if current_article_title and current_article_lines:
        articles.append({
            "part": current_part,
            "chapter": current_chapter,
            "section": current_section,
            "article_num": current_article_num,
            "title": current_article_title,
            "body": "\n".join(current_article_lines).strip()
        })
        
    return articles

def generate_golden_set(input_file, output_file):
    doc_id = os.path.basename(input_file)
    articles = parse_markdown_legal(input_file)
    golden_set = []
    test_id = 1
    
    for art in articles:
        num = art["article_num"]
        title = art["title"].strip().rstrip('.')
        body = art["body"]
        clean_body = clean_answer(body)
        clean_name = re.sub(r'^(quy định về|thủ tục|trình tự|nội dung)\s+', '', title.lower())
        
        meta = {
            "doc_id": doc_id,
            "chapter": art["chapter"],
            "article": f"Điều {num}"
        }
        
        # 1. direct_lookup (easy)
        golden_set.append({
            "id": test_id,
            "type": "direct_lookup",
            "question": f"Quy định chi tiết về {clean_name} được thực hiện như thế nào?",
            "expected_answer": clean_body,
            "ground_truth_context": body,
            "gold_metadata": meta,
            "difficulty": "easy"
        })
        test_id += 1
        
        # 2. multi_hop (easy)
        golden_set.append({
            "id": test_id,
            "type": "multi_hop",
            "question": f"Những điểm tổng hợp quan trọng cần lưu ý khi tìm hiểu về {clean_name} gồm những gì?",
            "expected_answer": clean_body,
            "ground_truth_context": body,
            "gold_metadata": meta,
            "difficulty": "easy"
        })
        test_id += 1
        
        # 3. unanswerable (easy)
        golden_set.append({
            "id": test_id,
            "type": "unanswerable",
            "question": f"Mức phạt tiền cụ thể đối với vi phạm liên quan đến {clean_name} là bao nhiêu tiền?",
            "expected_answer": "Thông tin về mức xử phạt tiền cụ thể không có trong tài liệu quy định này.",
            "ground_truth_context": "",
            "gold_metadata": meta,
            "difficulty": "easy"
        })
        test_id += 1
        
        # 4. ambiguous (easy)
        golden_set.append({
            "id": test_id,
            "type": "ambiguous",
            "question": f"{clean_name.capitalize()} làm thế nào?",
            "expected_answer": f"Nội dung này phụ thuộc vào từng trường hợp cụ thể. Về tổng quan: {clean_body}",
            "ground_truth_context": body,
            "gold_metadata": meta,
            "difficulty": "easy"
        })
        test_id += 1
        
        # 5. adversarial (easy)
        golden_set.append({
            "id": test_id,
            "type": "adversarial",
            "question": f"Có phải quy định hiện hành đã hủy bỏ việc {clean_name} đúng không?",
            "expected_answer": f"Thông tin này không chính xác. Quy định về {clean_name} vẫn được áp dụng cụ thể như sau: {clean_body}",
            "ground_truth_context": body,
            "gold_metadata": meta,
            "difficulty": "easy"
        })
        test_id += 1
        
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(golden_set, f, ensure_ascii=False, indent=2)
        
    print(f"Successfully generated {len(golden_set)} items with doc_id '{doc_id}' into {output_file}")

def main():
    parser = argparse.ArgumentParser(description="Generate Golden Set from Extracted Legal Markdown")
    parser.add_argument("--input", type=Path, default=Path("data/extracted/01_2021_ND-CP_283247.md"), help="Path to input markdown file")
    parser.add_argument("--output", type=Path, default=Path("evaluation/golden_set.json"), help="Path to output JSON file")
    args = parser.parse_args()
    
    generate_golden_set(args.input, args.output)

if __name__ == "__main__":
    main()
