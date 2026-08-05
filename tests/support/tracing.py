from typing import Any

from observability.tracing import Tracer
from settings import Settings, TraceMode


class RecordingObservation:
    def __init__(self, name: str, metadata: dict[str, Any]) -> None:
        self.name = name
        self.initial_metadata = metadata
        self.updates: list[dict[str, Any]] = []
        self.active = False

    def __enter__(self) -> "RecordingObservation":
        self.active = True
        return self

    def __exit__(self, *args: object) -> None:
        self.active = False

    def update(self, *, metadata: dict[str, Any]) -> None:
        assert self.active, "trace updated after span closed"
        self.updates.append(metadata)


class RecordingTracer:
    def __init__(
        self,
        mode_or_settings_or_error: TraceMode | Settings | Exception | None = None,
        error: Exception | None = None,
    ) -> None:
        mode = TraceMode.FULL
        eff_error = error

        if isinstance(mode_or_settings_or_error, Exception):
            eff_error = mode_or_settings_or_error
            self._tracer = Tracer(Settings(_env_file=None))
        elif isinstance(mode_or_settings_or_error, Settings):
            self._tracer = Tracer(mode_or_settings_or_error)
        else:
            if mode_or_settings_or_error is not None:
                mode = mode_or_settings_or_error
            self._tracer = Tracer(
                Settings(
                    _env_file=None,
                    trace_mode=mode,
                    allow_sensitive_tracing=mode is TraceMode.FULL,
                )
            )

        self.observations: list[RecordingObservation] = []
        self.flush_calls = 0
        self.error = eff_error

    @property
    def names(self) -> list[str]:
        return [observation.name for observation in self.observations]

    def span(self, name: str, metadata: dict[str, Any]) -> RecordingObservation:
        observation = RecordingObservation(name, metadata)
        self.observations.append(observation)
        return observation

    def safe_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._tracer.safe_payload(payload)

    def update(self, observation: RecordingObservation, metadata: dict[str, Any]) -> None:
        self._tracer.update(observation, metadata)

    def observation(self, name: str) -> RecordingObservation:
        return next(observation for observation in self.observations if observation.name == name)

    def flush(self) -> None:
        self.flush_calls += 1
        if self.error is not None:
            raise self.error
