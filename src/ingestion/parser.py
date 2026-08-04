from __future__ import annotations

import re
from io import BytesIO
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from docx.document import Document as DocxDocument
    from docx.table import Table
    from docx.text.paragraph import Paragraph

DOCX_MIME_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class UnsupportedDocumentError(ValueError):
    pass


def parse_document(filename: str, content: bytes) -> tuple[str, str]:
    lowered = filename.lower()
    if lowered.endswith((".md", ".txt")):
        try:
            return content.decode("utf-8"), "text/markdown" if lowered.endswith(".md") else "text/plain"
        except UnicodeDecodeError as exc:
            raise UnsupportedDocumentError("Text documents must use UTF-8") from exc
    if lowered.endswith(".pdf"):
        try:
            from pypdf import PdfReader

            reader = PdfReader(BytesIO(content))
            text = "\n\n".join(page.extract_text() or "" for page in reader.pages).strip()
            return text, "application/pdf"
        except Exception as exc:
            raise UnsupportedDocumentError("Unable to parse PDF; it may be corrupt or encrypted") from exc
    if lowered.endswith(".docx"):
        try:
            from docx import Document as read_docx

            document = read_docx(BytesIO(content))
        except Exception as exc:
            raise UnsupportedDocumentError("Unable to parse DOCX; it may be corrupt or password-protected") from exc
        return _docx_text(document), DOCX_MIME_TYPE
    raise UnsupportedDocumentError("Only .md, .txt, .pdf and .docx files are supported")


def _docx_text(document: DocxDocument) -> str:
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    blocks: list[str] = []
    for child in document.element.body.iterchildren():
        if child.tag.endswith("}p"):
            block = _paragraph_text(Paragraph(child, document))
        elif child.tag.endswith("}tbl"):
            block = _table_text(Table(child, document))
        else:
            continue
        if block:
            blocks.append(block)
    return "\n\n".join(blocks).strip()


def _paragraph_text(paragraph: Paragraph) -> str:
    text = paragraph.text.strip()
    if not text:
        return ""
    level = _heading_level(paragraph)
    return f"{'#' * level} {text}" if level else text


def _heading_level(paragraph: Paragraph) -> int:
    """Map a Word heading style to a markdown level so the chunker can see sections."""
    style = paragraph.style.name if paragraph.style is not None else ""
    if style == "Title":
        return 1
    match = re.fullmatch(r"Heading (\d)", style)
    return min(int(match.group(1)), 6) if match else 0


def _table_text(table: Table) -> str:
    """Render a table as pipe-separated rows; cell text would otherwise be dropped entirely."""
    rows: list[str] = []
    for row in table.rows:
        cells = [cell.text.strip().replace("\n", " ") for cell in row.cells]
        if any(cells):
            rows.append(" | ".join(cells))
    return "\n".join(rows)
