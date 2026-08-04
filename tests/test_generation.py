from domain.schemas import Chunk, DocumentStatus, Principal
from generation.service import ABSTENTION, ChatService
from observability.tracing import Tracer
from providers.base import GenerationRequest, GenerationResult
from retrieval.memory_store import MemoryChunkStore
from settings import Settings


class UncitedProvider:
    name = "stub"

    def generate(self, request: GenerationRequest) -> GenerationResult:
        return GenerationResult("Câu trả lời không có nguồn.", "stub", "stub")


class CitedProvider:
    name = "stub"

    def generate(self, request: GenerationRequest) -> GenerationResult:
        return GenerationResult("Được nghỉ 15 ngày [C1].", "stub", "stub", {"input_tokens": 10})


class ZeroCitationProvider:
    name = "stub"

    def generate(self, request: GenerationRequest) -> GenerationResult:
        return GenerationResult("Nguồn không hợp lệ [C0].", "stub", "stub")


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


def test_trace_metadata_is_updated_before_span_closes() -> None:
    class ActiveSpan:
        active = False

        def __enter__(self):
            self.active = True
            return self

        def __exit__(self, *args):
            self.active = False

    class StrictTracer:
        def span(self, name, metadata):
            return ActiveSpan()

        def safe_payload(self, payload):
            return payload

        def update(self, observation, metadata):
            assert observation.active, "trace updated after span closed"

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
    service = ChatService(store, CitedProvider(), StrictTracer(), retrieval_limit=5)  # type: ignore[arg-type]

    response = service.answer("Nghỉ phép?", Principal(subject="user", roles={"employee"}))

    assert response.citations[0].source_name == "leave.md"


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
                allowed_roles={"employee"},
            )
        ],
    )
    service = ChatService(store, ZeroCitationProvider(), Tracer(Settings()), 5)

    response = service.answer("Policy?", Principal(subject="user", roles={"employee"}))

    assert response.answer == ABSTENTION
    assert response.citations == []
