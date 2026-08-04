"""Concurrency-safe discovery and health tracking for Gemini API keys."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from threading import Lock
from typing import Callable, Mapping, TypeVar

_NUMBERED_FALLBACK_KEY = re.compile(r"^GEMINI_API_FALLBACK_KEY([1-9][0-9]*)$")
T = TypeVar("T")


class GeminiKeysExhausted(RuntimeError):
    """Raised when no configured Gemini API key is currently eligible."""


@dataclass(frozen=True)
class GeminiKeyLease:
    """Opaque key lease container. Callers MUST NEVER log or print ``api_key``."""

    position: int
    api_key: str

    def __repr__(self) -> str:
        return f"GeminiKeyLease(position={self.position}, api_key='***')"

    def __str__(self) -> str:
        return f"GeminiKeyLease(position={self.position}, api_key='***')"


class GeminiKeyPool:
    """Select configured Gemini keys in healthy round-robin order."""

    def __init__(
        self,
        keys: list[str],
        *,
        clock: Callable[[], float] = time.monotonic,
        cooldown_seconds: float = 60.0,
    ) -> None:
        self._keys = keys
        self._clock = clock
        self._cooldown_seconds = cooldown_seconds
        self._cooldowns = [0.0] * len(keys)
        self._cursor = 0
        self._lock = Lock()

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str],
        *,
        clock: Callable[[], float] = time.monotonic,
        cooldown_seconds: float = 60.0,
    ) -> GeminiKeyPool:
        """Build a pool from environment variable names.

        Supported variable patterns:
        - GEMINI_API_KEY (Primary)
        - GEMINI_API_FALLBACK_KEY (Default fallback)
        - GEMINI_API_FALLBACK_KEY2, GEMINI_API_FALLBACK_KEY3, ... (Numbered fallbacks)
        """
        names = ["GEMINI_API_KEY", "GEMINI_API_FALLBACK_KEY"]
        numbered: list[tuple[int, str]] = []
        for name in environment:
            match = _NUMBERED_FALLBACK_KEY.fullmatch(name)
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
        return cls(keys, clock=clock, cooldown_seconds=cooldown_seconds)

    @property
    def key_count(self) -> int:
        """Return total number of unique configured keys."""
        return len(self._keys)

    def next_key(self) -> GeminiKeyLease:
        """Return the next healthy key and advance the cursor atomically."""
        if not self._keys:
            raise GeminiKeysExhausted("No configured Gemini API key is currently available.")

        with self._lock:
            now = self._clock()
            for offset in range(len(self._keys)):
                position = (self._cursor + offset) % len(self._keys)
                if self._cooldowns[position] <= now:
                    self._cursor = (position + 1) % len(self._keys)
                    return GeminiKeyLease(position, self._keys[position])
        raise GeminiKeysExhausted("No configured Gemini API key is currently available.")

    def mark_quota_limited(
        self, lease: GeminiKeyLease, *, cooldown_seconds: float | None = None
    ) -> None:
        """Temporarily place one key on cooldown."""
        duration = cooldown_seconds or self._cooldown_seconds
        with self._lock:
            self._cooldowns[lease.position] = self._clock() + duration

    def invoke(
        self,
        operation: Callable[[GeminiKeyLease], T],
        *,
        is_quota_limited: Callable[[Exception], bool],
    ) -> T:
        """Execute an operation, trying healthy keys sequentially if quota limited."""
        last_quota_error: Exception | None = None
        for _ in range(self.key_count):
            try:
                lease = self.next_key()
            except GeminiKeysExhausted:
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
        raise GeminiKeysExhausted("No configured Gemini API key is currently available.")
