from __future__ import annotations

import re

from pydantic import BaseModel

from domain.schemas import SourceCoordinates

LEGAL_HEADING_RE = re.compile(
    r"(?m)^(?:#{1,6}[ \t]+)?((?:Chương[ \t]+[IVXLCDM]+|Điều[ \t]+\d+[A-Za-z]?)\b.*)$"
)
GENERIC_HEADING_RE = re.compile(r"(?m)^#{1,6}[ \t]+(.+?)\s*$")
CHAPTER_RE = re.compile(r"^Chương\s+[IVXLCDM]+\b", re.IGNORECASE)
ARTICLE_RE = re.compile(r"^(Điều\s+\d+[A-Za-z]?)\b", re.IGNORECASE)


class LegalSection(BaseModel):
    heading: str | None
    text: str
    coordinates: SourceCoordinates


def extract_legal_sections(text: str, doc_id: str) -> list[LegalSection]:
    matches = list(LEGAL_HEADING_RE.finditer(text))
    if not matches:
        generic_matches = list(GENERIC_HEADING_RE.finditer(text))
        if generic_matches:
            output: list[LegalSection] = []
            prefix = text[: generic_matches[0].start()].strip()
            if prefix:
                output.append(
                    LegalSection(
                        heading=None,
                        text=prefix,
                        coordinates=SourceCoordinates(doc_id=doc_id),
                    )
                )
            for index, match in enumerate(generic_matches):
                end = generic_matches[index + 1].start() if index + 1 < len(generic_matches) else len(text)
                section_text = text[match.start() : end].strip()
                if section_text:
                    output.append(
                        LegalSection(
                            heading=match.group(1).strip(),
                            text=section_text,
                            coordinates=SourceCoordinates(doc_id=doc_id),
                        )
                    )
            return output
        stripped = text.strip()
        if not stripped:
            return []
        return [LegalSection(heading=None, text=stripped, coordinates=SourceCoordinates(doc_id=doc_id))]
    output: list[LegalSection] = []
    prefix = text[: matches[0].start()].strip()
    if prefix:
        output.append(LegalSection(heading=None, text=prefix, coordinates=SourceCoordinates(doc_id=doc_id)))
    chapter: str | None = None
    for index, match in enumerate(matches):
        heading = match.group(1).strip()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[match.end() : end].strip()
        chapter_match = CHAPTER_RE.match(heading)
        article_match = ARTICLE_RE.match(heading)
        if chapter_match:
            chapter = chapter_match.group(0)
        article = article_match.group(1) if article_match else None
        section_text = text[match.start() : end].strip() if article else body
        if section_text:
            output.append(
                LegalSection(
                    heading=heading,
                    text=section_text,
                    coordinates=SourceCoordinates(doc_id=doc_id, chapter=chapter, article=article),
                )
            )
    return output
