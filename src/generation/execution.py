from __future__ import annotations

from pydantic import BaseModel, Field

from domain.schemas import ChatResponse, Citation, RetrievalInfo, SearchHit


class RankedHit(BaseModel):
    rank: int = Field(ge=1)
    hit: SearchHit


class RetrievalExecution(BaseModel):
    question: str
    request_id: str
    hits: list[RankedHit]
    latency_ms: float


class GenerationExecution(BaseModel):
    answer: str
    citations: list[Citation]
    structured_response: dict[str, object]
    provider: str | None
    model: str | None
    prompt_version: str
    usage: dict[str, int]
    latency_ms: float


class RagExecution(BaseModel):
    request_id: str
    retrieval: RetrievalExecution
    generation: GenerationExecution | None

    def to_chat_response(self) -> ChatResponse:
        generated = self.generation
        return ChatResponse(
            answer=(
                generated.answer
                if generated is not None
                else "Không tìm thấy thông tin phù hợp trong tài liệu được phép truy cập."
            ),
            citations=generated.citations if generated is not None else [],
            retrieval=RetrievalInfo(
                result_count=len(self.retrieval.hits),
                latency_ms=self.retrieval.latency_ms,
            ),
            request_id=self.request_id,
            provider=generated.provider if generated is not None else None,
            model=generated.model if generated is not None else None,
        )
