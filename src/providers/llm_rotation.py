"""Quota-aware Gemini model rotation wrapper for LangChain / LangGraph and general runnables."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from typing import Any

from langchain_core.runnables import Runnable, RunnableConfig

from providers.gemini_key_pool import GeminiKeyPool, GeminiKeysExhausted

logger = logging.getLogger(__name__)


def is_gemini_quota_error(exc: Exception) -> bool:
    """Return True only for genuine per-key quota / rate-limit signals."""
    text = str(exc).casefold()
    return any(
        marker in text
        for marker in (
            "429",
            "quota",
            "rate limit",
            "rate_limit",
            "resource exhausted",
            "resource_exhausted",
        )
    )


def is_gemini_transient_error(exc: Exception) -> bool:
    """Return True for server-side transient errors warranting a key retry WITHOUT cooldown."""
    text = str(exc).casefold()
    return any(
        marker in text
        for marker in (
            "500",
            "503",
            "504",
            "deadline",
            "timeout",
            "unavailable",
            "connection error",
            "connection reset",
            "connection refused",
            "remotedisconnected",
        )
    )


class GeminiRotatingRunnable(Runnable[Any, Any]):
    """Invoke LLM operations per healthy Gemini key in pool without logging credentials."""

    def __init__(
        self,
        pool: GeminiKeyPool,
        model_factory: Callable[[str], Any],
        fallback_factory: Callable[[], Any] | None = None,
    ) -> None:
        self._pool = pool
        self._model_factory = model_factory
        self._fallback_factory = fallback_factory

    def invoke(
        self, input: Any, config: RunnableConfig | None = None, **kwargs: Any
    ) -> Any:
        """Synchronously invoke LLM with automatic key failover."""
        last_error: Exception
        try:
            return self._pool.invoke(
                lambda lease: self._model_factory(lease.api_key).invoke(
                    input, config=config, **kwargs
                ),
                is_quota_limited=is_gemini_quota_error,
            )
        except Exception as exc:
            if not (
                isinstance(exc, GeminiKeysExhausted)
                or is_gemini_quota_error(exc)
                or is_gemini_transient_error(exc)
            ):
                raise
            last_error = exc

        # All Gemini keys exhausted or failed transiently — attempt secondary provider
        if self._fallback_factory:
            logger.warning("All Gemini keys exhausted. Triggering fallback provider.")
            return self._fallback_factory().invoke(input, config=config, **kwargs)
        raise last_error

    def stream(
        self, input: Any, config: RunnableConfig | None = None, **kwargs: Any
    ) -> Iterator[Any]:
        """Stream chunks with failover prior to yielding the first chunk."""
        last_error: Exception | None = None
        for _ in range(self._pool.key_count):
            try:
                lease = self._pool.next_key()
            except GeminiKeysExhausted as exc:
                if self._fallback_factory:
                    logger.warning("Gemini keys exhausted. Triggering fallback stream.")
                    yield from self._fallback_factory().stream(input, config=config, **kwargs)
                    return
                if last_error is not None:
                    raise last_error from exc
                raise

            emitted = False
            try:
                for chunk in self._model_factory(lease.api_key).stream(
                    input, config=config, **kwargs
                ):
                    emitted = True
                    yield chunk
                return
            except Exception as exc:
                if emitted:
                    # Stream partially delivered — surface error immediately
                    raise
                if is_gemini_quota_error(exc):
                    self._pool.mark_quota_limited(lease)
                    last_error = exc
                elif is_gemini_transient_error(exc):
                    logger.warning(
                        "Gemini transient error during stream, retrying: %s", type(exc).__name__
                    )
                    last_error = exc
                else:
                    raise

        if self._fallback_factory:
            logger.warning("All Gemini keys exhausted. Triggering fallback stream.")
            yield from self._fallback_factory().stream(input, config=config, **kwargs)
            return

        if last_error is not None:
            raise last_error
        raise GeminiKeysExhausted("No configured Gemini API key is currently available.")
