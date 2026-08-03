from __future__ import annotations

from io import BytesIO


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
        except Exception:
            return "", "application/pdf"
    raise UnsupportedDocumentError("Only .md, .txt and .pdf files are supported")

