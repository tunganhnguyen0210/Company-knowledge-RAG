import pytest

from domain.schemas import Chunk, DocumentStatus
from generation.service import ChatService
from prompts.answer_v2 import PROMPT_VERSION
from retrieval.memory_store import MemoryChunkStore
from settings import Settings, TraceMode
from tests.support.providers import CitedProvider
from tests.support.tracing import RecordingTracer

pytestmark = pytest.mark.component


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
    assert generation.updates[0]["model"] == "stub-model"
    assert generation.updates[0]["input_tokens"] == 10
    assert generation.updates[0]["response"] == {
        "answer": "Được nghỉ 15 ngày [C1].",
        "citations": [1],
    }
    assert generation.updates[0]["citation_ids"] == ["C1"]
    assert generation.updates[0]["answer"] == response.answer
    assert response.citations[0].id == "C1"
