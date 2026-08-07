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
    retrieval_text: str | None = None,
    parent_id: str | None = None,
    parent_child_count: int | None = None,
    child_index: int = 0,
    parent_text: str | None = None,
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
        retrieval_text=retrieval_text,
        parent_id=parent_id,
        parent_child_count=parent_child_count,
        child_index=child_index,
        parent_text=parent_text,
    )


def make_family(
    *,
    parent_id: str = "doc-1:v1:p0",
    texts: list[str],
    base_position: int = 0,
    coordinates: SourceCoordinates | None = None,
    section: str | None = "Điều 1",
    declare_count: bool = True,
) -> list[Chunk]:
    """A consistent sibling family: contiguous positions, matching counts.

    `declare_count=False` leaves `parent_child_count` unset to simulate a legacy
    payload indexed before that field existed.
    """
    shared = coordinates or SourceCoordinates(doc_id="policy.md", chapter="Chương I", article="Điều 1")
    return [
        make_chunk(
            chunk_id=f"{parent_id}:c{index}",
            text=text,
            section=section,
            position=base_position + index,
            coordinates=shared,
            parent_id=parent_id,
            parent_child_count=len(texts) if declare_count else None,
            child_index=index,
        )
        for index, text in enumerate(texts)
    ]
