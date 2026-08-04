"""Concurrency-safe discovery and health tracking for arbitrary LLM/API keys."""

from __future__ import annotations

import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from threading import Lock
from typing import TypeVar

T = TypeVar("T")


class ApiKeysExhausted(RuntimeError):
    """Raised when no configured API key for a provider is currently eligible."""


@dataclass(frozen=True)
class ApiKeyLease:
    """Opaque key lease container. Callers MUST NEVER log or print ``api_key``."""

    position: int
    api_key: str
    provider_name: str = ""

    def __repr__(self) -> str:
        prov = f"provider={self.provider_name!r}, " if self.provider_name else ""
        return f"ApiKeyLease({prov}position={self.position}, api_key='***')"

    def __str__(self) -> str:
        return self.__repr__()


class ApiKeyPool:
    """Select configured API keys in healthy round-robin order."""

    def __init__(
        self,
        keys: list[str],
        *,
        provider_name: str = "",
        clock: Callable[[], float] = time.monotonic,
        cooldown_seconds: float = 30.0,
    ) -> None:
        self._keys = keys
        self.provider_name = provider_name
        self._clock = clock
        self._cooldown_seconds = cooldown_seconds
        self._cooldowns = [0.0] * len(keys)
        self._cursor = 0
        self._lock = Lock()

    @classmethod
    def from_environment(
        cls,
        prefix: str,
        environment: Mapping[str, str],
        *,
        clock: Callable[[], float] = time.monotonic,
        cooldown_seconds: float = 30.0,
    ) -> ApiKeyPool:
        """Build a key pool for a provider prefix from environment variable names.

        Supported variable patterns for prefix P (e.g. GEMINI, JINA, OPENAI):
        - P_API_KEY (Primary)
        - P_API_FALLBACK_KEY (Default fallback)
        - P_API_FALLBACK_KEY2, P_API_FALLBACK_KEY3, ... (Numbered fallbacks)
        """
        prefix_upper = prefix.upper()
        pattern = re.compile(rf"^{prefix_upper}_API_FALLBACK_KEY([1-9][0-9]*)$")
        names = [f"{prefix_upper}_API_KEY", f"{prefix_upper}_API_FALLBACK_KEY"]
        numbered: list[tuple[int, str]] = []
        for name in environment:
            match = pattern.fullmatch(name)
            if match:
                numbered.append((int(match.group(1)), name))
        names.extend(name for _, name in sorted(numbered))

        seen: set[str] = set()
        keys: list[str] = []
        for name in names:
            value = environment.get(name, "").strip()
            if value and value not in seen:
                seen.add(value)
                keys.append(value)
        return cls(
            keys,
            provider_name=prefix.lower(),
            clock=clock,
            cooldown_seconds=cooldown_seconds,
        )

    @property
    def key_count(self) -> int:
        """Return total number of unique configured keys."""
        return len(self._keys)

    @property
    def primary_key(self) -> str:
        """Return the primary (first) configured key, or empty string if none."""
        return self._keys[0] if self._keys else ""

    @property
    def cooldown_seconds(self) -> float:
        """How long a quota-limited key stays parked."""
        return self._cooldown_seconds

    def _exhausted_error(self) -> ApiKeysExhausted:
        prov_str = f" for {self.provider_name}" if self.provider_name else ""
        return ApiKeysExhausted(f"No configured API key{prov_str} is currently available.")

    def next_key(self) -> ApiKeyLease:
        """Return the next healthy key and advance the cursor atomically."""
        if not self._keys:
            raise self._exhausted_error()

        with self._lock:
            now = self._clock()
            for offset in range(len(self._keys)):
                position = (self._cursor + offset) % len(self._keys)
                if self._cooldowns[position] <= now:
                    self._cursor = (position + 1) % len(self._keys)
                    return ApiKeyLease(position, self._keys[position], self.provider_name)
        raise self._exhausted_error()

    def mark_quota_limited(
        self, lease: ApiKeyLease, *, cooldown_seconds: float | None = None
    ) -> None:
        """Temporarily place one key on cooldown."""
        duration = cooldown_seconds if cooldown_seconds is not None else self._cooldown_seconds
        with self._lock:
            if 0 <= lease.position < len(self._cooldowns):
                self._cooldowns[lease.position] = self._clock() + duration

    def invoke(
        self,
        operation: Callable[[ApiKeyLease], T],
        *,
        is_quota_limited: Callable[[Exception], bool],
    ) -> T:
        """Execute an operation, trying healthy keys sequentially if quota limited."""
        last_quota_error: Exception | None = None
        for _ in range(self.key_count):
            try:
                lease = self.next_key()
            except ApiKeysExhausted:
                if last_quota_error is not None:
                    raise last_quota_error from None
                raise
            try:
                return operation(lease)
            except Exception as exc:
                if not is_quota_limited(exc):
                    raise
                self.mark_quota_limited(lease)
                last_quota_error = exc
        if last_quota_error is not None:
            raise last_quota_error
        raise self._exhausted_error()
