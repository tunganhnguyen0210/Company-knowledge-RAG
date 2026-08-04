import time
from dataclasses import replace

from providers.base import (
    GenerationProvider,
    GenerationRequest,
    GenerationResult,
    ProviderError,
)


class ProviderRouter:
    name = "provider-router"

    def __init__(
        self,
        primary: GenerationProvider,
        fallback: GenerationProvider | None,
        *,
        max_attempts: int = 2,
    ) -> None:
        self.primary = primary
        self.fallback = fallback
        self.max_attempts = max(1, max_attempts)

    def generate(self, request: GenerationRequest) -> GenerationResult:
        last_error: ProviderError | None = None
        for attempt in range(self.max_attempts):
            try:
                result = self.primary.generate(request)
                return replace(
                    result,
                    usage={
                        **result.usage,
                        "primary_attempts": attempt + 1,
                        "fallback_used": 0,
                    },
                )
            except ProviderError as exc:
                if not exc.transient:
                    raise
                last_error = exc
                if attempt + 1 < self.max_attempts:
                    time.sleep(0.1 * (2**attempt))
        if self.fallback is not None:
            result = self.fallback.generate(request)
            return replace(
                result,
                usage={
                    **result.usage,
                    "primary_attempts": self.max_attempts,
                    "fallback_used": 1,
                },
            )
        assert last_error is not None
        raise last_error

    def ready(self) -> bool:
        ready = getattr(self.primary, "ready", None)
        return bool(ready and ready())
