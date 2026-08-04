"""Shared instructor plumbing so every provider returns validated Pydantic objects.

Instructor owns the schema wiring, JSON parsing and the reask loop: when a model
answers with malformed JSON or a payload that fails validation, it feeds the
validation error back to the model instead of letting a broken string leak into
the pipeline.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

import instructor
from instructor.core.exceptions import InstructorRetryException

from providers.base import GenerationRequest, ProviderError, StructuredT

STRUCTURED_MAX_RETRIES = 2


def underlying_failure(exc: InstructorRetryException) -> Exception | None:
    """Instructor retries API errors too, so the wrapper hides the real cause."""
    failed_attempts = getattr(exc, "failed_attempts", None) or []
    if failed_attempts:
        last = getattr(failed_attempts[-1], "exception", None)
        if isinstance(last, Exception):
            return last
    cause = exc.__cause__
    return cause if isinstance(cause, Exception) else None


def structured_messages(request: GenerationRequest) -> list[dict[str, str]]:
    """Instructor normalizes this OpenAI-shaped history for every provider."""
    return [
        {"role": "system", "content": request.system_instruction},
        {"role": "user", "content": request.user_prompt},
    ]


def create_structured(
    client: instructor.Instructor,
    *,
    provider_name: str,
    model: str,
    request: GenerationRequest,
    response_model: type[StructuredT],
    max_retries: int,
    is_transient: Callable[[Exception], bool],
    **generation_kwargs: Any,
) -> tuple[StructuredT, Any]:
    """Return the validated model plus the raw completion (for usage metrics)."""
    try:
        return cast(
            tuple[StructuredT, Any],
            client.create_with_completion(
                model=model,
                messages=cast(Any, structured_messages(request)),
                response_model=response_model,
                max_retries=max_retries,
                **generation_kwargs,
            ),
        )
    except InstructorRetryException as exc:
        cause = underlying_failure(exc)
        raise ProviderError(
            f"{provider_name} did not return a valid {response_model.__name__} "
            f"after {exc.n_attempts} attempts: {cause or exc}",
            # A schema the model cannot satisfy is permanent, but a rate limit
            # behind the same wrapper still deserves the router's failover.
            transient=cause is not None and is_transient(cause),
        ) from exc
    except Exception as exc:
        raise ProviderError(
            f"{provider_name} structured request failed: {exc}",
            transient=is_transient(exc),
        ) from exc
