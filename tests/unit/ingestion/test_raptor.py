from domain.schemas import Chunk, Document, DocumentStatus, SourceCoordinates
from ingestion.raptor import RaptorConfig, build_raptor_nodes, is_raptor_node
from providers.base import GenerationRequest, GenerationResult


class StubProvider:
    name = "stub"

    def __init__(self) -> None:
        self.calls: list[GenerationRequest] = []

    def generate(self, request: GenerationRequest) -> GenerationResult:
        self.calls.append(request)
        return GenerationResult(text=f"summary of {len(self.calls)}", provider="stub", model="stub-model")

    def generate_structured(self, request, response_model):  # pragma: no cover - unused
        raise NotImplementedError


def _document() -> Document:
    return Document(
        id="doc",
        version=1,
        content_hash="hash",
        source_name="law.md",
        mime_type="text/markdown",
        status=DocumentStatus.READY,
    )


def _chunks(count: int) -> list[Chunk]:
    return [
        Chunk(
            id=f"doc:v1:{i}",
            document_id="doc",
            version=1,
            text=f"Nội dung điều {i}.",
            content_hash=f"hash{i}",
            source_name="law.md",
            mime_type="text/markdown",
            status=DocumentStatus.READY,
            coordinates=SourceCoordinates(doc_id="law.md"),
            position=i,
        )
        for i in range(count)
    ]


def test_disabled_by_default_produces_no_nodes() -> None:
    nodes = build_raptor_nodes(_document(), _chunks(6), RaptorConfig())

    assert nodes == []


def test_disabled_when_provider_missing_even_if_enabled_flag_set() -> None:
    nodes = build_raptor_nodes(_document(), _chunks(6), RaptorConfig(enabled=True, provider=None))

    assert nodes == []


def test_clusters_sibling_chunks_and_tags_summary_section() -> None:
    provider = StubProvider()
    config = RaptorConfig(enabled=True, cluster_size=3, max_depth=1, provider=provider)

    nodes = build_raptor_nodes(_document(), _chunks(7), config)

    # 7 chunks / cluster_size 3 -> clusters of [3, 3, 1]; the trailing size-1 cluster is skipped.
    assert len(nodes) == 2
    assert all(node.section == "__raptor_summary_L1__" for node in nodes)
    assert all(is_raptor_node(node) for node in nodes)
    assert all(node.retrieval_text == node.text for node in nodes)
    assert len(provider.calls) == 2


def test_too_few_chunks_produces_no_nodes() -> None:
    provider = StubProvider()
    config = RaptorConfig(enabled=True, cluster_size=5, provider=provider)

    nodes = build_raptor_nodes(_document(), _chunks(1), config)

    assert nodes == []
    assert provider.calls == []


def test_max_depth_recurses_over_previous_level_summaries() -> None:
    provider = StubProvider()
    config = RaptorConfig(enabled=True, cluster_size=2, max_depth=2, provider=provider)

    nodes = build_raptor_nodes(_document(), _chunks(4), config)

    levels = {node.section for node in nodes}
    assert levels == {"__raptor_summary_L1__", "__raptor_summary_L2__"}
