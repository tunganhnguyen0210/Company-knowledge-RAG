from domain.schemas import Chunk, DocumentStatus
from ingestion.enrichment import LLMChunkEnricher
from providers.base import GenerationRequest, GenerationResult


class StructuredProvider:
    name = "stub"

    def generate(self, request: GenerationRequest) -> GenerationResult:
        return GenerationResult(
            '{"summary":"Nghỉ phép năm",'
            '"questions":["Được nghỉ bao nhiêu ngày?"],'
            '"context":"Chính sách nhân sự",'
            '"metadata":{"category":"hr"}}',
            "stub",
            "stub-model",
        )


def test_llm_enrichment_preserves_original_and_adds_retrieval_context() -> None:
    chunk = Chunk(
        id="chunk",
        document_id="doc",
        version=1,
        text="Nhân viên được nghỉ 15 ngày.",
        content_hash="hash",
        source_name="leave.md",
        mime_type="text/markdown",
        status=DocumentStatus.READY,
        allowed_roles={"employee"},
    )

    enriched = LLMChunkEnricher(StructuredProvider()).enrich(chunk)

    assert enriched.text == chunk.text
    assert enriched.retrieval_text == "Chính sách nhân sự\n\nNhân viên được nghỉ 15 ngày."
    assert enriched.summary == "Nghỉ phép năm"
    assert enriched.auto_metadata == {"category": "hr"}
