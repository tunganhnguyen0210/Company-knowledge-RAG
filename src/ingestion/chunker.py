from __future__ import annotations

import re
from dataclasses import dataclass
from hashlib import sha256

from domain.schemas import Chunk, Document

DEFAULT_MAX_CHARS = 2500
BREADCRUMB_SEPARATOR = " > "

_MARKDOWN_HEADING = re.compile(r"^(#{1,6})\s+(.+)$")
# Vietnamese legal documents nest Phần → Chương → Mục → Điều. The numbering token is
# required so that ordinary prose ("Mục tiêu của chương trình…") is not read as a heading.
_NUMBERED_HEADING = re.compile(
    r"^(PHẦN|Phần|CHƯƠNG|Chương|MỤC|Mục)\s+((?:thứ\s+)?[IVXLCDM]+|\d+|thứ\s+\S+)\b[.:\-]?\s*(.*)$"
)
_DIEU_HEADING = re.compile(r"^(Điều\s+\d+[a-zđ]?)\s*[.:]\s*(.*)$")
_LEVELS = {"phần": 1, "chương": 2, "mục": 3}
_DIEU_LEVEL = 4
_MERGED_TITLE_MAX_CHARS = 200

# Split ladder, coarsest first: a chunk is only cut at a finer boundary when the
# coarser one still leaves a piece above the cap.
_KHOAN_BOUNDARY = re.compile(r"(?m)^[ \t]*\d+\.[ \t]")
_DIEM_BOUNDARY = re.compile(r"(?m)^[ \t]*[a-zđ][).][ \t]")
_BLANK_LINE = re.compile(r"\n[ \t]*\n+")
_LINE_BOUNDARY = re.compile(r"(?m)(?<=\n)(?=.)")
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.;:!?])\s+")


@dataclass(frozen=True)
class _Segment:
    """One structural unit of the document plus the headings it sits under."""

    title: str | None
    path: tuple[str, ...]
    body: str


def chunk_document(document: Document, text: str, max_chars: int = DEFAULT_MAX_CHARS) -> list[Chunk]:
    output: list[Chunk] = []
    for segment in _segments(text):
        for piece in _split(segment.body, max_chars):
            position = len(output)
            output.append(
                Chunk(
                    id=f"{document.id}:v{document.version}:{position}",
                    document_id=document.id,
                    version=document.version,
                    text=piece,
                    content_hash=sha256(piece.encode("utf-8")).hexdigest(),
                    source_name=document.source_name,
                    mime_type=document.mime_type,
                    status=document.status,
                    section=segment.title,
                    position=position,
                    retrieval_text=_retrieval_text(document, segment, piece),
                )
            )
    return output


def _retrieval_text(document: Document, segment: _Segment, piece: str) -> str | None:
    """Prepend the breadcrumb to what gets embedded and BM25-indexed.

    `text` stays byte-identical to the source so citations quote the document, but a
    chunk carved out of the middle of an article otherwise carries no trace of which
    article it belongs to — and that is exactly what legal questions ask about.
    """
    if not segment.path:
        return None
    breadcrumb = BREADCRUMB_SEPARATOR.join(segment.path)
    return f"{document.source_name} — {breadcrumb}\n\n{piece}"


def _segments(text: str) -> list[_Segment]:
    lines = text.splitlines()
    headings = _headings(lines)
    if not headings:
        stripped = text.strip()
        return [_Segment(None, (), stripped)] if stripped else []

    segments: list[_Segment] = []
    preamble = "\n".join(lines[: headings[0][0]]).strip()
    if preamble:
        segments.append(_Segment(None, (), preamble))

    path: list[tuple[int, str]] = []
    for index, (start, consumed, level, title) in enumerate(headings):
        path = [entry for entry in path if entry[0] < level]
        path.append((level, title))
        end = headings[index + 1][0] if index + 1 < len(headings) else len(lines)
        body = "\n".join(lines[start + consumed : end]).strip()
        if body:
            segments.append(_Segment(title, tuple(item[1] for item in path), body))
    return segments


def _headings(lines: list[str]) -> list[tuple[int, int, int, str]]:
    """Locate headings as (line index, lines consumed, level, title)."""
    found: list[tuple[int, int, int, str]] = []
    index = 0
    while index < len(lines):
        parsed = _parse_heading(lines, index)
        if parsed is None:
            index += 1
            continue
        consumed, level, title = parsed
        found.append((index, consumed, level, title))
        index += consumed
    return found


def _parse_heading(lines: list[str], index: int) -> tuple[int, int, str] | None:
    line = lines[index].strip()
    markdown = _MARKDOWN_HEADING.match(line)
    if markdown:
        line = markdown.group(2).strip()

    dieu = _DIEU_HEADING.match(line)
    if dieu:
        title = f"{dieu.group(1)}. {dieu.group(2)}".strip() if dieu.group(2) else dieu.group(1)
        return 1, _DIEU_LEVEL, title

    numbered = _NUMBERED_HEADING.match(line)
    if numbered:
        label = f"{numbered.group(1)} {numbered.group(2)}"
        level = _LEVELS[numbered.group(1).casefold()]
        inline_title = numbered.group(3).strip()
        if inline_title:
            return 1, level, f"{label}. {inline_title}"
        consumed, merged = _merge_title_line(lines, index + 1)
        return consumed + 1, level, f"{label}. {merged}" if merged else label

    if markdown:
        return 1, len(markdown.group(1)), line
    return None


def _merge_title_line(lines: list[str], index: int) -> tuple[int, str]:
    """Absorb the title that legal documents put on the line after 'Chương I'."""
    offset = 0
    while index + offset < len(lines) and not lines[index + offset].strip():
        offset += 1
    if index + offset >= len(lines):
        return offset, ""
    candidate = lines[index + offset].strip()
    if (
        not candidate
        or len(candidate) > _MERGED_TITLE_MAX_CHARS
        or candidate.endswith((".", ";"))
        or _parse_heading(lines, index + offset) is not None
    ):
        return 0, ""
    return offset + 1, candidate


def _split(text: str, max_chars: int) -> list[str]:
    stripped = text.strip()
    if not stripped:
        return []
    if len(stripped) <= max_chars:
        return [stripped]
    for cut in (_cut_at_khoan, _cut_at_diem, _cut_at_blank_line, _cut_at_line, _cut_at_sentence):
        parts = cut(text)
        if len(parts) > 1:
            return _pack(parts, max_chars)
    return [text[start : start + max_chars].strip() for start in range(0, len(text), max_chars)]


def _pack(parts: list[str], max_chars: int) -> list[str]:
    pieces: list[str] = []
    current = ""
    for part in parts:
        if current and len(current) + len(part) > max_chars:
            pieces.append(current.strip())
            current = ""
        if len(part.strip()) > max_chars:
            if current.strip():
                pieces.append(current.strip())
            current = ""
            pieces.extend(_split(part, max_chars))
        else:
            current += part
    if current.strip():
        pieces.append(current.strip())
    return [piece for piece in pieces if piece]


def _cut_before(text: str, pattern: re.Pattern[str]) -> list[str]:
    """Slice text before every match; concatenating the result rebuilds the input."""
    starts = [match.start() for match in pattern.finditer(text)]
    starts = [start for start in starts if start > 0]
    if not starts:
        return [text]
    bounds = [0, *starts, len(text)]
    return [text[begin:end] for begin, end in zip(bounds[:-1], bounds[1:], strict=True)]


def _cut_after(text: str, pattern: re.Pattern[str]) -> list[str]:
    ends = [match.end() for match in pattern.finditer(text) if 0 < match.end() < len(text)]
    if not ends:
        return [text]
    bounds = [0, *ends, len(text)]
    return [text[begin:end] for begin, end in zip(bounds[:-1], bounds[1:], strict=True)]


def _cut_at_khoan(text: str) -> list[str]:
    return _cut_before(text, _KHOAN_BOUNDARY)


def _cut_at_diem(text: str) -> list[str]:
    return _cut_before(text, _DIEM_BOUNDARY)


def _cut_at_blank_line(text: str) -> list[str]:
    return _cut_after(text, _BLANK_LINE)


def _cut_at_line(text: str) -> list[str]:
    return _cut_before(text, _LINE_BOUNDARY)


def _cut_at_sentence(text: str) -> list[str]:
    return _cut_after(text, _SENTENCE_BOUNDARY)
