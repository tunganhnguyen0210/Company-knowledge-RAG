import re

from domain.schemas import Document, DocumentStatus
from ingestion.chunker import DEFAULT_MAX_CHARS, chunk_document

LEGAL_TEXT = """Số: 168/2024/NĐ-CP

NGHỊ ĐỊNH

Chương I

NHỮNG QUY ĐỊNH CHUNG

Điều 1. Phạm vi điều chỉnh

1. Nghị định này quy định về xử phạt vi phạm hành chính.

2. Các hành vi khác áp dụng quy định tại Nghị định chuyên ngành.

Điều 2. Đối tượng áp dụng

1. Cá nhân, tổ chức Việt Nam.
"""


def _document() -> Document:
    return Document(
        id="doc-1",
        version=3,
        content_hash="hash",
        source_name="168_2024_ND-CP.docx",
        mime_type="text/markdown",
        status=DocumentStatus.READY,
    )


def test_dieu_heading_becomes_the_section_of_its_chunks() -> None:
    chunks = chunk_document(_document(), LEGAL_TEXT)

    assert [chunk.section for chunk in chunks] == [
        None,
        "Điều 1. Phạm vi điều chỉnh",
        "Điều 2. Đối tượng áp dụng",
    ]
    assert [chunk.position for chunk in chunks] == [0, 1, 2]
    assert chunks[0].id == "doc-1:v3:0"


def test_chapter_title_on_the_next_line_joins_the_breadcrumb() -> None:
    chunks = chunk_document(_document(), LEGAL_TEXT)

    assert chunks[1].retrieval_text is not None
    assert chunks[1].retrieval_text.startswith(
        "168_2024_ND-CP.docx — Chương I. NHỮNG QUY ĐỊNH CHUNG > Điều 1. Phạm vi điều chỉnh\n\n"
    )
    # The breadcrumb is retrieval-only; citations must quote the document verbatim.
    assert chunks[1].text.startswith("1. Nghị định này quy định về")
    assert "NHỮNG QUY ĐỊNH CHUNG" not in chunks[1].text


def test_preamble_before_the_first_heading_keeps_no_section() -> None:
    chunks = chunk_document(_document(), LEGAL_TEXT)

    assert chunks[0].section is None
    assert chunks[0].retrieval_text is None
    assert "NGHỊ ĐỊNH" in chunks[0].text


def test_long_article_splits_on_khoan_boundaries() -> None:
    body = "\n\n".join(f"{number}. " + "Nội dung quy định. " * 20 for number in range(1, 11))
    text = f"Điều 7. Mức phạt tiền\n\n{body}"

    chunks = chunk_document(_document(), text, max_chars=1000)

    assert len(chunks) > 1
    assert all(len(chunk.text) <= 1000 for chunk in chunks)
    assert all(chunk.section == "Điều 7. Mức phạt tiền" for chunk in chunks)
    # Every chunk opens on a numbered khoản, so none of them starts mid-provision.
    assert all(re.match(r"^\d+\.\s", chunk.text) for chunk in chunks)


def test_oversized_khoan_falls_through_to_diem_boundaries() -> None:
    diem = "\n".join(f"{letter}) " + "Chi tiết hành vi vi phạm. " * 12 for letter in "abcdđe")
    text = f"Điều 8. Hành vi vi phạm\n\n1. Phạt tiền đối với các hành vi sau đây:\n{diem}"

    chunks = chunk_document(_document(), text, max_chars=600)

    assert len(chunks) > 1
    assert all(len(chunk.text) <= 600 for chunk in chunks)
    assert all(re.match(r"^(\d+\.|[a-zđ]\))\s", chunk.text) for chunk in chunks)


def test_unstructured_text_is_cut_at_sentence_ends_not_mid_word() -> None:
    text = " ".join("Câu văn dài không có cấu trúc pháp lý nào cả." for _ in range(60))

    chunks = chunk_document(_document(), text, max_chars=400)

    assert len(chunks) > 1
    assert all(chunk.text.endswith(".") for chunk in chunks)


def test_markdown_headings_still_define_sections() -> None:
    text = "# Chinh sach VPN\n\nNhan vien phai dung MFA.\n\n## Ngoai le\n\nTruong hop khan cap."

    chunks = chunk_document(_document(), text)

    assert [chunk.section for chunk in chunks] == ["Chinh sach VPN", "Ngoai le"]
    assert chunks[1].retrieval_text is not None
    assert "Chinh sach VPN > Ngoai le" in chunks[1].retrieval_text


def test_prose_starting_with_a_structural_word_is_not_a_heading() -> None:
    text = "Mục tiêu của chương trình là nâng cao an toàn.\n\nChương trình kéo dài ba năm."

    chunks = chunk_document(_document(), text)

    assert len(chunks) == 1
    assert chunks[0].section is None


def test_chunk_text_never_exceeds_the_cap_on_a_single_unbroken_run() -> None:
    text = "Điều 9. Định nghĩa\n\n" + "x" * 5000

    chunks = chunk_document(_document(), text, max_chars=1000)

    assert all(len(chunk.text) <= 1000 for chunk in chunks)
    assert "".join(chunk.text for chunk in chunks) == "x" * 5000


def test_chunking_loses_no_visible_content() -> None:
    chunks = chunk_document(_document(), LEGAL_TEXT)

    rebuilt = re.sub(r"\s+", "", "".join(chunk.text for chunk in chunks))
    original = re.sub(r"\s+", "", LEGAL_TEXT)
    # Heading lines move into `section`; everything else must survive verbatim.
    for heading in ("ChươngI", "NHỮNGQUYĐỊNHCHUNG", "Điều1.Phạmviđiềuchỉnh", "Điều2.Đốitượngápdụng"):
        original = original.replace(heading, "", 1)
    assert rebuilt == original


def test_default_cap_matches_the_ingestion_service() -> None:
    from ingestion.service import CHUNK_MAX_CHARS

    assert CHUNK_MAX_CHARS == DEFAULT_MAX_CHARS == 2500
