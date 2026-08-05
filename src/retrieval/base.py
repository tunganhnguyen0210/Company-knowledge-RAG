from typing import Protocol

from domain.schemas import Chunk, SearchHit


class ChunkStore(Protocol):
    def replace_document(self, document_id: str, chunks: list[Chunk]) -> None: ...

    def search(self, query: str, limit: int = 5) -> list[SearchHit]: ...

    def list_chunks(self, document_id: str) -> list[Chunk]: ...

    def ready(self) -> bool: ...

