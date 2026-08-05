from __future__ import annotations

import time
from uuid import uuid4

from pydantic import BaseModel, Field

from domain.schemas import ChatResponse, Citation, SearchHit
from generation.execution import (
    GenerationExecution,
    RagExecution,
    RankedHit,
    RetrievalExecution,
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

    def answer(self, question: str) -> ChatResponse:
        return self.execute(question).to_chat_response()

    def retrieve(
        self,
        question: str,
        request_id: str | None = None,
    ) -> RetrievalExecution:
        current_request_id = request_id or str(uuid4())
        started = time.perf_counter()
        with self.tracer.span(
            "retrieval",
            self.tracer.safe_payload(
                {"request_id": current_request_id, "question": question}
            ),
        ) as observation:
            hits = self.store.search(question, limit=self.retrieval_limit)
            latency_ms = (time.perf_counter() - started) * 1000
            ranked = [
                RankedHit(rank=rank, hit=hit)
                for rank, hit in enumerate(hits, start=1)
            ]
            self.tracer.update(
                observation,
                {
                    "result_count": len(hits),
                    "latency_ms": latency_ms,
                    "top_k": [
                        {
                            "rank": item.rank,
                            "score": item.hit.score,
                            **item.hit.chunk.model_dump(mode="json"),
                        }
                        for item in ranked
                    ],
                },
            )
        return RetrievalExecution(
            question=question,
            request_id=current_request_id,
            hits=ranked,
            latency_ms=latency_ms,
        )

    def generate_from_hits(
        self,
        question: str,
        hits: list[SearchHit],
        request_id: str | None = None,
    ) -> GenerationExecution:
        current_request_id = request_id or str(uuid4())
        started = time.perf_counter()
        chunks = [hit.chunk for hit in hits]
        if not chunks:
            return GenerationExecution(
                answer=ABSTENTION,
                citations=[],
                structured_response={"answer": ABSTENTION, "citations": []},
                provider=None,
                model=None,
                prompt_version=PROMPT_VERSION,
                usage={},
                latency_ms=0.0,
            )
        prompt = render_answer_prompt(question, chunks)
        with self.tracer.span(
            "generation",
            self.tracer.safe_payload(
                {
                    "request_id": current_request_id,
                    "question": question,
                    "context": [chunk.text for chunk in chunks],
                    "prompt_version": PROMPT_VERSION,
                    "system_instruction": prompt.system_instruction,
                    "user_prompt": prompt.user_prompt,
                }
            ),
        ) as observation:
            result = self.provider.generate_structured(
                GenerationRequest(prompt.system_instruction, prompt.user_prompt),
                GroundedAnswer,
            )
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
            self.tracer.update(
                observation,
                {
                    "provider": result.provider,
                    "model": result.model,
                    **result.usage,
                    "response": result.value.model_dump(),
                    "citation_ids": [citation.id for citation in citations],
                    "answer": answer,
                },
            )
        return GenerationExecution(
            answer=answer,
            citations=citations,
            structured_response=result.value.model_dump(mode="json"),
            provider=result.provider,
            model=result.model,
            prompt_version=PROMPT_VERSION,
            usage=result.usage,
            latency_ms=(time.perf_counter() - started) * 1000,
        )

    def execute(
        self,
        question: str,
        retrieval: RetrievalExecution | None = None,
    ) -> RagExecution:
        request_id = retrieval.request_id if retrieval is not None else str(uuid4())
        with self.tracer.span(
            "rag-request",
            self.tracer.safe_payload(
                {"request_id": request_id, "question": question}
            ),
        ):
            retrieved = retrieval or self.retrieve(question, request_id)
            generated = (
                self.generate_from_hits(
                    question,
                    [item.hit for item in retrieved.hits],
                    request_id,
                )
                if retrieved.hits
                else None
            )
            return RagExecution(
                request_id=request_id,
                retrieval=retrieved,
                generation=generated,
            )
