from typing import Protocol

from company_knowledge_rag.domain.schemas import Chunk, Principal, SearchHit


class ChunkStore(Protocol):
    def replace_document(self, document_id: str, chunks: list[Chunk]) -> None: ...

    def search(self, query: str, principal: Principal, limit: int) -> list[SearchHit]: ...

    def ready(self) -> bool: ...

