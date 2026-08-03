from company_knowledge_rag.domain.schemas import Chunk, DocumentStatus, Principal
from company_knowledge_rag.generation.service import ABSTENTION, ChatService
from company_knowledge_rag.observability.tracing import Tracer
from company_knowledge_rag.providers.base import GenerationRequest, GenerationResult
from company_knowledge_rag.retrieval.memory_store import MemoryChunkStore
from company_knowledge_rag.settings import Settings


class UncitedProvider:
    name = "stub"

    def generate(self, request: GenerationRequest) -> GenerationResult:
        return GenerationResult("Câu trả lời không có nguồn.", "stub", "stub")


def test_generation_abstains_when_model_returns_no_valid_citation() -> None:
    store = MemoryChunkStore()
    store.replace_document(
        "doc",
        [
            Chunk(
                id="chunk",
                document_id="doc",
                version=1,
                text="Nhân viên được nghỉ 15 ngày.",
                content_hash="hash",
                source_name="leave.md",
                mime_type="text/markdown",
                status=DocumentStatus.READY,
                allowed_roles={"employee"},
            )
        ],
    )
    service = ChatService(store, UncitedProvider(), Tracer(Settings()), retrieval_limit=5)

    response = service.answer(
        "Nghỉ phép?",
        Principal(subject="employee-1", roles={"employee"}),
    )

    assert response.answer == ABSTENTION
    assert response.citations == []
