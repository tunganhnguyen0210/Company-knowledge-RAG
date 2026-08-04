from typing import Protocol

from domain.schemas import Chunk, Principal, SearchHit


class ChunkStore(Protocol):
    def replace_document(self, document_id: str, chunks: list[Chunk]) -> None: ...

    def search(self, query: str, principal: Principal | None = None, limit: int = 5) -> list[SearchHit]: ...

    def ready(self) -> bool: ...

