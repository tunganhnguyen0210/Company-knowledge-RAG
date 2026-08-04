from domain.schemas import Chunk, DocumentStatus
from generation.service import ABSTENTION, ChatService, GroundedAnswer
from observability.tracing import Tracer
from prompts.answer_v2 import PROMPT_VERSION
from providers.base import GenerationRequest, StructuredResult
from retrieval.memory_store import MemoryChunkStore
from settings import Settings, TraceMode


class RecordingObservation:
    def __init__(self, name: str, metadata: dict[object, object]) -> None:
        self.name = name
        self.initial_metadata = metadata
        self.updates: list[dict[object, object]] = []
        self.active = False

    def __enter__(self) -> "RecordingObservation":
        self.active = True
        return self

    def __exit__(self, *args: object) -> None:
        self.active = False

    def update(self, *, metadata: dict[object, object]) -> None:
        assert self.active, "trace updated after span closed"
        self.updates.append(metadata)


class RecordingTracer:
    def __init__(self, settings: Settings) -> None:
        self._tracer = Tracer(settings)
        self.observations: list[RecordingObservation] = []

    def span(self, name: str, metadata: dict[object, object]) -> RecordingObservation:
        observation = RecordingObservation(name, metadata)
        self.observations.append(observation)
        return observation

    def safe_payload(self, payload: dict[object, object]) -> dict[object, object]:
        return self._tracer.safe_payload(payload)  # type: ignore[arg-type, return-value]

    def update(self, observation: RecordingObservation, metadata: dict[object, object]) -> None:
        self._tracer.update(observation, metadata)  # type: ignore[arg-type]

    def observation(self, name: str) -> RecordingObservation:
        return next(observation for observation in self.observations if observation.name == name)


class UncitedProvider:
    name = "stub"

    def generate_structured(
        self, request: GenerationRequest, response_model: type[GroundedAnswer]
    ) -> StructuredResult[GroundedAnswer]:
        answer = GroundedAnswer(answer="Câu trả lời không có nguồn.", citations=[])
        return StructuredResult(answer, "stub", "stub")


class CitedProvider:
    name = "stub"

    def generate_structured(
        self, request: GenerationRequest, response_model: type[GroundedAnswer]
    ) -> StructuredResult[GroundedAnswer]:
        answer = GroundedAnswer(answer="Được nghỉ 15 ngày [C1].", citations=[1])
        return StructuredResult(answer, "stub", "stub", {"input_tokens": 10})


class ZeroCitationProvider:
    name = "stub"

    def generate_structured(
        self, request: GenerationRequest, response_model: type[GroundedAnswer]
    ) -> StructuredResult[GroundedAnswer]:
        answer = GroundedAnswer(answer="Nguồn không hợp lệ [C0].", citations=[0])
        return StructuredResult(answer, "stub", "stub")


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


def test_traces_ranked_retrieval_hits_and_citation_gated_final_answer() -> None:
    store = MemoryChunkStore()
    store.replace_document(
        "doc-1",
        [
            Chunk(
                id="chunk-1",
                document_id="doc-1",
                version=3,
                text="Leave policy permits fifteen days.",
                content_hash="hash-1",
                source_name="leave.md",
                mime_type="text/markdown",
                status=DocumentStatus.READY,
                section="Annual leave",
                position=4,
            )
        ],
    )
    store.replace_document(
        "doc-2",
        [
            Chunk(
                id="chunk-2",
                document_id="doc-2",
                version=1,
                text="Leave requests need manager approval.",
                content_hash="hash-2",
                source_name="requests.md",
                mime_type="text/markdown",
                status=DocumentStatus.READY,
                section="Requests",
                position=9,
            )
        ],
    )
    tracer = RecordingTracer(
        Settings(
            trace_mode=TraceMode.FULL,
            allow_sensitive_tracing=True,
            langfuse_public_key="",
            langfuse_secret_key="",
        )
    )
    service = ChatService(store, CitedProvider(), tracer, retrieval_limit=5)  # type: ignore[arg-type]

    response = service.answer("Leave policy?")

    retrieval = tracer.observation("retrieval")
    retrieval_update = retrieval.updates[0]
    assert retrieval_update["result_count"] == 2
    assert retrieval_update["latency_ms"] >= 0
    assert retrieval_update["top_k"] == [
        {
            "rank": 1,
            "score": 1.0,
            "chunk_id": "chunk-1",
            "document_id": "doc-1",
            "version": 3,
            "source_name": "leave.md",
            "section": "Annual leave",
            "position": 4,
            "content_hash": "hash-1",
            "text": "Leave policy permits fifteen days.",
        },
        {
            "rank": 2,
            "score": 0.5,
            "chunk_id": "chunk-2",
            "document_id": "doc-2",
            "version": 1,
            "source_name": "requests.md",
            "section": "Requests",
            "position": 9,
            "content_hash": "hash-2",
            "text": "Leave requests need manager approval.",
        },
    ]
    generation = tracer.observation("generation")
    assert generation.initial_metadata["question"] == "Leave policy?"
    assert generation.initial_metadata["context"] == [
        "Leave policy permits fifteen days.",
        "Leave requests need manager approval.",
    ]
    assert generation.initial_metadata["prompt_version"] == PROMPT_VERSION
    assert generation.initial_metadata["system_instruction"]
    assert generation.initial_metadata["user_prompt"]
    assert generation.updates[0]["provider"] == "stub"
    assert generation.updates[0]["model"] == "stub"
    assert generation.updates[0]["input_tokens"] == 10
    assert generation.updates[0]["response"] == {
        "answer": "Được nghỉ 15 ngày [C1].",
        "citations": [1],
    }
    assert generation.updates[0]["citation_ids"] == ["C1"]
    assert generation.updates[0]["answer"] == response.answer
    assert response.citations[0].id == "C1"


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
