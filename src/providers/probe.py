"""One cheap real call that proves the configured model is actually usable.

Credentials, model access, provider routing and the structured-output mode all
fail in ways `ready()` cannot see, because `ready()` only inspects local config.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from providers.base import GenerationProvider, GenerationRequest

PROBE_REQUEST = GenerationRequest(
    system_instruction="Bạn là probe kiểm tra kết nối. Chỉ điền đúng giá trị được yêu cầu.",
    user_prompt="Đặt status = ready.",
    temperature=0.0,
    # Generous enough that a reasoning model still has budget left for the payload.
    max_output_tokens=256,
)


class ProbeResult(BaseModel):
    status: str = Field(description="Luôn là chuỗi 'ready'.")


def probe_generation(provider: GenerationProvider) -> str:
    """Return the model that answered, or raise ProviderError explaining why not."""
    return provider.generate_structured(PROBE_REQUEST, ProbeResult).model
