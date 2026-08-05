from typing import Any

from generation.service import GroundedAnswer
from providers.base import GenerationRequest, ProviderError, StructuredResult
from providers.probe import ProbeResult


class UncitedProvider:
    name = "stub"
    model = "stub-model"

    def generate_structured(
        self, request: GenerationRequest, response_model: type[GroundedAnswer]
    ) -> StructuredResult[GroundedAnswer]:
        answer = GroundedAnswer(answer="Câu trả lời không có nguồn.", citations=[])
        return StructuredResult(answer, "stub", "stub-model")


class CitedProvider:
    name = "stub"
    model = "stub-model"

    def generate_structured(
        self, request: GenerationRequest, response_model: type[GroundedAnswer]
    ) -> StructuredResult[GroundedAnswer]:
        answer = GroundedAnswer(answer="Được nghỉ 15 ngày [C1].", citations=[1])
        return StructuredResult(answer, "stub", "stub-model", {"input_tokens": 10})


class ZeroCitationProvider:
    name = "stub"
    model = "stub-model"

    def generate_structured(
        self, request: GenerationRequest, response_model: type[GroundedAnswer]
    ) -> StructuredResult[GroundedAnswer]:
        answer = GroundedAnswer(answer="Nguồn không hợp lệ [C0].", citations=[0])
        return StructuredResult(answer, "stub", "stub-model")


class AnswerProvider:
    name = "stub"
    model = "stub-model"

    def generate_structured(
        self, request: GenerationRequest, response_model: type[Any]
    ) -> StructuredResult[Any]:
        if response_model is ProbeResult:
            return StructuredResult(ProbeResult(status="ready"), "stub", "stub-model")
        answer = GroundedAnswer(answer="Nhân viên được nghỉ 15 ngày [C1].", citations=[1])
        return StructuredResult(answer, "stub", "stub-model")


class FailingProvider:
    name = "stub"
    model = "stub-model"

    def generate_structured(
        self, request: GenerationRequest, response_model: type[Any]
    ) -> StructuredResult[Any]:
        raise ProviderError("Generation failed", transient=True)


class UnreachableProvider(AnswerProvider):
    def generate_structured(
        self, request: GenerationRequest, response_model: type[Any]
    ) -> StructuredResult[Any]:
        raise ProviderError("Error code: 404 - no allowed providers", transient=False)
