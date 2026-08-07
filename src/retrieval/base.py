from typing import Protocol

from domain.schemas import Chunk, SearchHit


class ChunkStore(Protocol):
    def replace_document(self, document_id: str, chunks: list[Chunk]) -> None: ...

    def search(self, query: str, limit: int = 5) -> list[SearchHit]: ...

    def list_document_chunks(
        self,
        document_id: str,
        version: int | None = None,
    ) -> list[Chunk]: ...

    def list_indexed_documents(self) -> dict[str, int]: ...
    """Every document_id present in the index, mapped to its chunk count.

    Needed to reconcile the index against the registry: `replace_document`
    only ever deletes by a document_id the caller already knows, so a document
    dropped from the registry leaves chunks nothing can reach.
    """

    def purge_documents(self, document_ids: list[str]) -> int: ...

    def ready(self) -> bool: ...

