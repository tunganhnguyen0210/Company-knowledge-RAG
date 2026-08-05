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
            self._client.start_as_current_observation(
                name=name, metadata=self.safe_payload(metadata)
            ),
        )

    def safe_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.mode is TraceMode.FULL:
            return payload
        sensitive_keys = {
            "answer",
            "context",
            "parsed_text",
            "prompt",
            "question",
            "response",
            "retrieval_text",
            "system_instruction",
            "text",
            "user_prompt",
        }

        def sanitize(value: Any) -> Any:
            if isinstance(value, dict):
                return {
                    key: sanitize(nested_value)
                    for key, nested_value in value.items()
                    if key not in sensitive_keys
                }
            if isinstance(value, list):
                return [sanitize(item) for item in value]
            return value

        return cast(dict[str, Any], sanitize(payload))

    def update(self, observation: Any, metadata: dict[str, Any]) -> None:
        if observation is not None and hasattr(observation, "update"):
            observation.update(metadata=self.safe_payload(metadata))

    def flush(self) -> None:
        if self._client is not None and hasattr(self._client, "flush"):
            self._client.flush()

