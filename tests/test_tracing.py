from contextlib import nullcontext
from typing import Any

from observability.tracing import Tracer
from settings import Settings


class RecordingObservation:
    def __init__(self) -> None:
        self.metadata: dict[str, Any] | None = None

    def update(self, *, metadata: dict[str, Any]) -> None:
        self.metadata = metadata


class RecordingClient:
    def __init__(self) -> None:
        self.metadata: dict[str, Any] | None = None

    def start_as_current_observation(
        self, *, name: str, metadata: dict[str, Any]
    ) -> Any:
        self.metadata = metadata
        return nullcontext()


def test_metadata_only_removes_sensitive_values_recursively() -> None:
    tracer = Tracer(Settings(trace_mode="metadata-only", _env_file=None))
    payload = tracer.safe_payload(
        {
            "question": "secret question",
            "top_k": [{"chunk_id": "c1", "text": "secret chunk"}],
            "answer": "secret answer",
            "result_count": 1,
        }
    )
    assert payload == {"top_k": [{"chunk_id": "c1"}], "result_count": 1}


def test_full_mode_preserves_sensitive_payload() -> None:
    tracer = Tracer(Settings(trace_mode="full", allow_sensitive_tracing=True, _env_file=None))
    payload = {"question": "q", "context": ["c"], "answer": "a"}
    assert tracer.safe_payload(payload) == payload


def test_update_sends_only_safe_metadata_to_active_observation() -> None:
    tracer = Tracer(Settings(trace_mode="metadata-only", _env_file=None))
    observation = RecordingObservation()

    tracer.update(observation, {"answer": "private", "result_count": 1})

    assert observation.metadata == {"result_count": 1}


def test_span_sends_only_safe_metadata_to_langfuse_client() -> None:
    tracer = Tracer(Settings(trace_mode="metadata-only", _env_file=None))
    client = RecordingClient()
    tracer._client = client

    with tracer.span("generation", {"prompt": "private", "result_count": 1}):
        pass

    assert client.metadata == {"result_count": 1}
