from domain.schemas import Chunk, DocumentStatus, SourceCoordinates
from generation.service import ABSTENTION, ChatService
from observability.tracing import Tracer
from retrieval.memory_store import MemoryChunkStore
from settings import Settings
from tests.support.providers import UncitedProvider, ZeroCitationProvider


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
                coordinates=SourceCoordinates(doc_id="policy.md"),
            )
        ],
    )
    service = ChatService(
        store,
        UncitedProvider(),
        Tracer(Settings(langfuse_public_key="", langfuse_secret_key="")),
        retrieval_limit=5,
    )

    response = service.answer("Nghỉ phép?")

    assert response.answer == ABSTENTION
    assert response.citations == []


def test_generation_rejects_zero_citation_index() -> None:
    store = MemoryChunkStore()
    store.replace_document(
        "doc",
        [
            Chunk(
                id="chunk",
                document_id="doc",
                version=1,
                text="Policy",
                content_hash="hash",
                source_name="policy.md",
                mime_type="text/markdown",
                status=DocumentStatus.READY,
                coordinates=SourceCoordinates(doc_id="policy.md"),
            )
        ],
    )
    service = ChatService(
        store,
        ZeroCitationProvider(),
        Tracer(Settings(langfuse_public_key="", langfuse_secret_key="")),
        5,
    )

    response = service.answer("Policy?")

    assert response.answer == ABSTENTION
    assert response.citations == []
