"""Concurrency-safe discovery and health tracking for Gemini API keys."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from typing import cast

from providers.key_pool import ApiKeyLease, ApiKeyPool, ApiKeysExhausted

# Backwards compatible exceptions and aliases
GeminiKeysExhausted = ApiKeysExhausted
GeminiKeyLease = ApiKeyLease


class GeminiKeyPool(ApiKeyPool):
    """Select configured Gemini keys in healthy round-robin order."""

    def __init__(
        self,
        keys: list[str],
        *,
        provider_name: str = "gemini",
        clock: Callable[[], float] = time.monotonic,
        cooldown_seconds: float = 30.0,
    ) -> None:
        super().__init__(
            keys,
            provider_name=provider_name,
            clock=clock,
            cooldown_seconds=cooldown_seconds,
        )

    @classmethod
    def from_environment(
        cls,
        environment_or_prefix: Mapping[str, str] | str = "GEMINI",
        environment: Mapping[str, str] | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
        cooldown_seconds: float = 30.0,
    ) -> GeminiKeyPool:
        """Build a Gemini key pool from environment variable names.

        Supported variable patterns:
        - GEMINI_API_KEY (Primary)
        - GEMINI_API_FALLBACK_KEY (Default fallback)
        - GEMINI_API_FALLBACK_KEY2, GEMINI_API_FALLBACK_KEY3, ... (Numbered fallbacks)
        """
        if isinstance(environment_or_prefix, str):
            prefix = environment_or_prefix
            env = environment if environment is not None else {}
        else:
            prefix = "GEMINI"
            env = environment_or_prefix

        pool = super().from_environment(
            prefix, env, clock=clock, cooldown_seconds=cooldown_seconds
        )
        return cast(GeminiKeyPool, pool)
