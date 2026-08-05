from domain.schemas import Chunk, DocumentStatus
from generation.service import ChatService
from retrieval.memory_store import MemoryChunkStore
from settings import Settings, TraceMode
from tests.support.providers import CitedProvider
from tests.support.tracing import RecordingTracer


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
            )
        ],
    )
    service = ChatService(store, CitedProvider(), StrictTracer(), retrieval_limit=5)  # type: ignore[arg-type]

    response = service.answer("Nghỉ phép?")

    assert response.citations[0].source_name == "leave.md"


def test_metadata_only_traces_redact_retrieval_text_and_final_answer() -> None:
    store = MemoryChunkStore()
    store.replace_document(
        "doc",
        [
            Chunk(
                id="chunk",
                document_id="doc",
                version=1,
                text="Leave policy permits fifteen days.",
                content_hash="hash",
                source_name="leave.md",
                mime_type="text/markdown",
                status=DocumentStatus.READY,
            )
        ],
    )
    tracer = RecordingTracer(
        Settings(
            trace_mode=TraceMode.METADATA_ONLY,
            langfuse_public_key="",
            langfuse_secret_key="",
        )
    )
    service = ChatService(store, CitedProvider(), tracer, retrieval_limit=5)  # type: ignore[arg-type]

    response = service.answer("Leave policy?")

    retrieval = tracer.observation("retrieval")
    assert "text" not in retrieval.updates[0]["top_k"][0]
    generation = tracer.observation("generation")
    assert "answer" not in generation.updates[0]
    assert response.citations[0].id == "C1"
