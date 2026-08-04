import time
from collections.abc import Callable
from dataclasses import replace
from typing import Any, TypeVar

from providers.base import (
    GenerationProvider,
    GenerationRequest,
    GenerationResult,
    ProviderError,
    StructuredResult,
    StructuredT,
)

RoutedResultT = TypeVar("RoutedResultT", GenerationResult, StructuredResult[Any])


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
        return self._route(lambda provider: provider.generate(request))

    def generate_structured(
        self,
        request: GenerationRequest,
        response_model: type[StructuredT],
    ) -> StructuredResult[StructuredT]:
        return self._route(lambda provider: provider.generate_structured(request, response_model))

    def _route(
        self, call: Callable[[GenerationProvider], RoutedResultT]
    ) -> RoutedResultT:
        last_error: ProviderError | None = None
        for attempt in range(self.max_attempts):
            try:
                result = call(self.primary)
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
            result = call(self.fallback)
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
