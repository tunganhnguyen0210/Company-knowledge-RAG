from domain.schemas import Chunk, DocumentStatus
from ingestion.enrichment import (
    MAX_HYPOTHESIS_QUESTIONS,
    ChunkEnrichment,
    LLMChunkEnricher,
    MetadataEntry,
)
from providers.base import GenerationRequest, StructuredResult


class StructuredProvider:
    name = "stub"

    def generate_structured(
        self, request: GenerationRequest, response_model: type[ChunkEnrichment]
    ) -> StructuredResult[ChunkEnrichment]:
        enrichment = ChunkEnrichment(
            summary="Nghỉ phép năm",
            questions=["Được nghỉ bao nhiêu ngày?"],
            context="Chính sách nhân sự",
            metadata=[MetadataEntry(key="category", value="hr")],
        )
        return StructuredResult(enrichment, "stub", "stub-model")


def _chunk() -> Chunk:
    return Chunk(
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


def test_llm_enrichment_preserves_original_and_adds_retrieval_context() -> None:
    chunk = _chunk()

    enriched = LLMChunkEnricher(StructuredProvider()).enrich(chunk)

    assert enriched.text == chunk.text
    assert enriched.retrieval_text == "Chính sách nhân sự\n\nNhân viên được nghỉ 15 ngày."
    assert enriched.summary == "Nghỉ phép năm"
    assert enriched.auto_metadata == {"category": "hr"}


def test_enrichment_caps_hypothesis_questions() -> None:
    enrichment = ChunkEnrichment(
        summary="s",
        questions=[f"q{index}" for index in range(MAX_HYPOTHESIS_QUESTIONS + 3)],
        context="c",
        metadata=[],
    )

    assert len(enrichment.questions) == MAX_HYPOTHESIS_QUESTIONS
