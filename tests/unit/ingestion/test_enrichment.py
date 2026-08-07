from domain.schemas import Chunk, DocumentStatus, SourceCoordinates
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


def _chunk(**overrides: object) -> Chunk:
    defaults: dict[str, object] = dict(
        id="chunk",
        document_id="doc",
        version=1,
        text="Nhân viên được nghỉ 15 ngày.",
        content_hash="hash",
        source_name="leave.md",
        mime_type="text/markdown",
        status=DocumentStatus.READY,
        coordinates=SourceCoordinates(doc_id="policy.md"),
    )
    defaults.update(overrides)
    return Chunk(**defaults)


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


def test_contextual_embedding_leads_with_section_heading_when_present() -> None:
    chunk = _chunk(section="Điều 5. Nghỉ phép")

    enriched = LLMChunkEnricher(StructuredProvider()).enrich(chunk)

    assert enriched.retrieval_text == (
        "Điều 5. Nghỉ phép — Chính sách nhân sự\n\nNhân viên được nghỉ 15 ngày."
    )


class StubMrlEmbedder:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(texts)
        return [[0.1, 0.2] for _ in texts]

    def embed_query(self, text: str) -> list[float]:
        return [0.1, 0.2]


def test_mrl_embedder_populates_truncated_vector_from_retrieval_text() -> None:
    chunk = _chunk()
    mrl_embedder = StubMrlEmbedder()

    enriched = LLMChunkEnricher(StructuredProvider(), mrl_embedder=mrl_embedder).enrich(chunk)

    assert enriched.mrl_vector_128 == [0.1, 0.2]
    assert mrl_embedder.calls == [[enriched.retrieval_text]]


def test_mrl_vector_stays_none_without_mrl_embedder() -> None:
    chunk = _chunk()

    enriched = LLMChunkEnricher(StructuredProvider()).enrich(chunk)

    assert enriched.mrl_vector_128 is None
