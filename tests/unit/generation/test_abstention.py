from generation.service import ABSTENTION, ChatService
from observability.tracing import Tracer
from retrieval.memory_store import MemoryChunkStore
from settings import Settings
from tests.support.providers import CitedProvider


def test_generation_abstains_when_no_chunks_retrieved() -> None:
    store = MemoryChunkStore()
    service = ChatService(
        store,
        CitedProvider(),
        Tracer(Settings(langfuse_public_key="", langfuse_secret_key="")),
        retrieval_limit=5,
    )

    execution = service.execute("Nghỉ phép?")
    response = execution.to_chat_response()

    assert execution.generation is None
    assert response.answer == ABSTENTION
    assert response.citations == []
