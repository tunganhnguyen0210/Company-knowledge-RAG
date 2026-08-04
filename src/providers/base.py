from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class GenerationRequest:
    system_instruction: str
    user_prompt: str
    temperature: float = 0.0
    max_output_tokens: int = 1200


@dataclass(frozen=True)
class GenerationResult:
    text: str
    provider: str
    model: str
    usage: dict[str, int] = field(default_factory=dict)


class ProviderError(RuntimeError):
    def __init__(self, message: str, *, transient: bool) -> None:
        super().__init__(message)
        self.transient = transient


class GenerationProvider(Protocol):
    name: str

    def generate(self, request: GenerationRequest) -> GenerationResult: ...


class EmbeddingProvider(Protocol):
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...

