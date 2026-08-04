from dataclasses import dataclass, field
from typing import Generic, Protocol, TypeVar

from pydantic import BaseModel

StructuredT = TypeVar("StructuredT", bound=BaseModel)


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


@dataclass(frozen=True)
class StructuredResult(Generic[StructuredT]):
    value: StructuredT
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

    def generate_structured(
        self,
        request: GenerationRequest,
        response_model: type[StructuredT],
    ) -> StructuredResult[StructuredT]: ...


class EmbeddingProvider(Protocol):
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...

