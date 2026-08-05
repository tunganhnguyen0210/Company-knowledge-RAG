import re

from domain.schemas import Document, DocumentStatus, SourceCoordinates
from ingestion.chunker import chunk_document
from ingestion.structure import extract_legal_sections

LEGAL_TEXT = """# Chương I

QUY ĐỊNH CHUNG

### Điều 1. Phạm vi điều chỉnh

Nội dung điều một.

### Điều 2. Đối tượng áp dụng

Nội dung điều hai.

# Chương II

### Điều 3. Quy định tiếp theo

Nội dung điều ba.
"""


def test_article_inherits_current_chapter() -> None:
    sections = extract_legal_sections(LEGAL_TEXT, "law.md")

    article_three = next(item for item in sections if item.coordinates.article == "Điều 3")
    assert article_three.coordinates == SourceCoordinates(
        doc_id="law.md", chapter="Chương II", article="Điều 3"
    )
    assert article_three.text.startswith("### Điều 3. Quy định tiếp theo")


def test_split_chunks_keep_article_coordinates() -> None:
    document = Document(
        id="doc",
        version=1,
        content_hash="hash",
        source_name="law.docx",
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        status=DocumentStatus.READY,
        metadata={"canonical_doc_id": "law.md"},
    )

    chunks = chunk_document(document, LEGAL_TEXT, max_chars=40)

    article_one = [chunk for chunk in chunks if chunk.coordinates.article == "Điều 1"]
    assert article_one
    article_one_text = next(
        section.text
        for section in extract_legal_sections(LEGAL_TEXT, "law.md")
        if section.coordinates == article_one[0].coordinates
    )
    assert all(chunk.coordinates.chapter == "Chương I" for chunk in article_one)
    assert all(chunk.coordinates.doc_id == "law.md" for chunk in article_one)
    assert "".join(chunk.text for chunk in article_one) == article_one_text


def test_plain_docx_legal_headings_match_markdown_hierarchy() -> None:
    plain = re.sub(r"(?m)^#{1,6}[ \t]+", "", LEGAL_TEXT)

    markdown_coordinates = [item.coordinates for item in extract_legal_sections(LEGAL_TEXT, "law.md")]
    plain_coordinates = [item.coordinates for item in extract_legal_sections(plain, "law.md")]

    assert plain_coordinates == markdown_coordinates
    assert sum(item.article is not None for item in plain_coordinates) == 3
