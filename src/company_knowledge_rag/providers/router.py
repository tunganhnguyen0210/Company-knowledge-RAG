import time

from company_knowledge_rag.providers.base import (
    GenerationProvider,
    GenerationRequest,
    GenerationResult,
    ProviderError,
)


class ProviderRouter:
    name = "gemini-with-openrouter-fallback"

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
                return self.primary.generate(request)
            except ProviderError as exc:
                if not exc.transient:
                    raise
                last_error = exc
                if attempt + 1 < self.max_attempts:
                    time.sleep(0.1 * (2**attempt))
        if self.fallback is not None:
            return self.fallback.generate(request)
        assert last_error is not None
        raise last_error

