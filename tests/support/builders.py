from domain.schemas import Chunk, DocumentStatus, SourceCoordinates


def make_chunk(
    *,
    chunk_id: str = "chunk-1",
    document_id: str = "doc-1",
    version: int = 1,
    text: str = "Policy content",
    content_hash: str = "hash",
    source_name: str = "policy.md",
    mime_type: str = "text/markdown",
    section: str | None = None,
    position: int = 0,
    status: DocumentStatus = DocumentStatus.READY,
    coordinates: SourceCoordinates | None = None,
) -> Chunk:
    return Chunk(
        id=chunk_id,
        document_id=document_id,
        version=version,
        text=text,
        content_hash=content_hash,
        source_name=source_name,
        mime_type=mime_type,
        section=section,
        position=position,
        status=status,
        coordinates=coordinates or SourceCoordinates(doc_id="policy.md"),
    )
