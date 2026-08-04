from __future__ import annotations

import time
from uuid import uuid4

from pydantic import BaseModel, Field

from domain.schemas import (
    ChatResponse,
    Citation,
    Principal,
    RetrievalInfo,
)
from observability.tracing import Tracer
from prompts.answer_v2 import PROMPT_VERSION, render_answer_prompt
from providers.base import GenerationProvider, GenerationRequest
from retrieval.base import ChunkStore

ABSTENTION = "Không tìm thấy thông tin phù hợp trong tài liệu được phép truy cập."


class GroundedAnswer(BaseModel):
    """Output contract every provider must satisfy, enforced by instructor."""

    answer: str = Field(description="Câu trả lời tiếng Việt, mỗi nhận định kèm marker [C1], [C2].")
    citations: list[int] = Field(
        description="Số thứ tự các đoạn CONTEXT đã dùng, ví dụ [1, 3]. Rỗng nếu không đủ bằng chứng."
    )


class ChatService:
    def __init__(
        self,
        store: ChunkStore,
        provider: GenerationProvider,
        tracer: Tracer,
        retrieval_limit: int = 5,
    ) -> None:
        self.store = store
        self.provider = provider
        self.tracer = tracer
        self.retrieval_limit = retrieval_limit

    def answer(self, question: str, principal: Principal | None = None) -> ChatResponse:
        active_principal = principal or Principal()
        request_id = str(uuid4())
        with self.tracer.span(
            "rag-request",
            self.tracer.safe_payload(
                {"request_id": request_id, "question": question, "subject": active_principal.subject}
            ),
        ):
            return self._answer(question, active_principal, request_id)

    def _answer(self, question: str, principal: Principal, request_id: str) -> ChatResponse:
        started = time.perf_counter()
        with self.tracer.span(
            "retrieval",
            self.tracer.safe_payload(
                {"request_id": request_id, "question": question, "roles": sorted(principal.roles)}
            ),
        ) as retrieval_observation:
            hits = self.store.search(question, principal, self.retrieval_limit)
            latency_ms = (time.perf_counter() - started) * 1000
            self.tracer.update(
                retrieval_observation,
                {"result_count": len(hits), "latency_ms": latency_ms},
            )
        if not hits:
            return ChatResponse(
                answer=ABSTENTION,
                citations=[],
                retrieval=RetrievalInfo(result_count=0, latency_ms=latency_ms),
                request_id=request_id,
            )

        chunks = [hit.chunk for hit in hits]
        prompt = render_answer_prompt(question, chunks)
        with self.tracer.span(
            "generation",
            self.tracer.safe_payload(
                {
                    "request_id": request_id,
                    "question": question,
                    "context": [chunk.text for chunk in chunks],
                    "prompt_version": PROMPT_VERSION,
                }
            ),
        ) as generation_observation:
            result = self.provider.generate_structured(
                GenerationRequest(prompt.system_instruction, prompt.user_prompt),
                GroundedAnswer,
            )
            self.tracer.update(
                generation_observation,
                {"provider": result.provider, "model": result.model, **result.usage},
            )
        # The model may still cite a chunk it was never shown; the range check is authoritative.
        cited_indexes = sorted(
            {index for index in result.value.citations if 1 <= index <= len(chunks)}
        )
        citations = [
            Citation(
                id=f"C{index}",
                document_id=chunks[index - 1].document_id,
                chunk_id=chunks[index - 1].id,
                source_name=chunks[index - 1].source_name,
                version=chunks[index - 1].version,
                excerpt=chunks[index - 1].text[:300],
            )
            for index in cited_indexes
        ]
        answer = result.value.answer if citations else ABSTENTION
        return ChatResponse(
            answer=answer,
            citations=citations,
            retrieval=RetrievalInfo(result_count=len(hits), latency_ms=latency_ms),
            request_id=request_id,
            provider=result.provider,
            model=result.model,
        )
