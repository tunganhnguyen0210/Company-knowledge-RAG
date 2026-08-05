from contextlib import nullcontext
from typing import Any

from domain.schemas import Chunk, DocumentStatus, SearchHit, SourceCoordinates
from generation.service import ChatService, GroundedAnswer
from providers.base import StructuredResult


def _search_hit(text: str) -> SearchHit:
    return SearchHit(
        chunk=Chunk(
            id="chunk-1",
            document_id="document-1",
            version=1,
            text=text,
            content_hash="chunk-hash",
            source_name="law.docx",
            mime_type="application/docx",
            status=DocumentStatus.READY,
            coordinates=SourceCoordinates(
                doc_id="law.md", chapter="Chương I", article="Điều 1"
            ),
        ),
        score=0.9,
    )


class RecordingStore:
    def __init__(self, hits: list[SearchHit]) -> None:
        self.hits = hits
        self.search_calls = 0

    def search(self, query: str, limit: int = 5) -> list[SearchHit]:
        self.search_calls += 1
        return self.hits[:limit]


class CitedProvider:
    def generate_structured(
        self,
        request: Any,
        response_model: type[GroundedAnswer],
    ) -> StructuredResult[GroundedAnswer]:
        return StructuredResult(
            value=response_model(answer="Nội dung [C1].", citations=[1]),
            provider="fake",
            model="fake-model",
            usage={"input_tokens": 10, "output_tokens": 5},
        )


class SilentTracer:
    def span(self, name: str, payload: dict[str, object]):
        return nullcontext(object())

    def safe_payload(self, payload: dict[str, object]) -> dict[str, object]:
        return payload

    def update(self, observation: object, payload: dict[str, object]) -> None:
        return None


def _recording_chat() -> tuple[ChatService, RecordingStore]:
    store = RecordingStore([_search_hit("fixed-context")])
    return ChatService(store, CitedProvider(), SilentTracer()), store


def _chat_with_cited_provider() -> ChatService:
    return _recording_chat()[0]


def test_execute_returns_ranked_hits_and_projects_existing_chat_response() -> None:
    chat = _chat_with_cited_provider()

    execution = chat.execute("Nghỉ phép thế nào?")
    response = execution.to_chat_response()

    assert [item.hit.chunk.id for item in execution.retrieval.hits] == ["chunk-1"]
    assert execution.generation is not None
    assert response.answer == execution.generation.answer
    assert response.citations == execution.generation.citations
    assert set(response.model_dump()) == {
        "answer",
        "citations",
        "retrieval",
        "request_id",
        "provider",
        "model",
    }


def test_generation_replay_does_not_search_store() -> None:
    chat, store = _recording_chat()
    hits = [_search_hit("fixed-context")]

    generated = chat.generate_from_hits("Question", hits)

    assert store.search_calls == 0
    assert generated.answer
