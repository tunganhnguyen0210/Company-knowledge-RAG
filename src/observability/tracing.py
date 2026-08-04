from __future__ import annotations

from contextlib import AbstractContextManager, nullcontext
from typing import Any, cast

from settings import Settings, TraceMode


class Tracer:
    def __init__(self, settings: Settings) -> None:
        self.mode = settings.trace_mode
        self._client: Any = None
        if (
            self.mode is not TraceMode.OFF
            and settings.langfuse_public_key
            and settings.langfuse_secret_key
        ):
            from langfuse import Langfuse

            self._client = Langfuse(
                public_key=settings.langfuse_public_key,
                secret_key=settings.langfuse_secret_key,
                host=settings.langfuse_host,
            )

    def span(self, name: str, metadata: dict[str, Any]) -> AbstractContextManager[Any]:
        if self._client is None:
            return nullcontext()
        return cast(
            AbstractContextManager[Any],
            self._client.start_as_current_observation(name=name, metadata=metadata),
        )

    def safe_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.mode is TraceMode.FULL:
            return payload
        return {key: value for key, value in payload.items() if key not in {"question", "context", "answer"}}

    @staticmethod
    def update(observation: Any, metadata: dict[str, Any]) -> None:
        if observation is not None and hasattr(observation, "update"):
            observation.update(metadata=metadata)
