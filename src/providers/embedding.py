"""Helpers shared by every embedding backend."""

from __future__ import annotations

from collections.abc import Iterator
from math import sqrt


def normalize_embedding(values: list[float]) -> list[float]:
    norm = sqrt(sum(value * value for value in values))
    return [value / norm for value in values] if norm else values


def batched(texts: list[str], size: int) -> Iterator[list[str]]:
    """Embedding APIs cap how many texts one request may carry."""
    for start in range(0, len(texts), size):
        yield texts[start : start + size]
