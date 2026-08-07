from domain.schemas import Document, DocumentStatus
from ingestion.chunker import ChunkingConfig, _split, chunk_document


class StubEmbedder:
    """Deterministic topic vectors: text containing "AAA" vs "BBB" is orthogonal."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] if "AAA" in text else [0.0, 1.0] for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


def _document(**metadata: str) -> Document:
    return Document(
        id="doc",
        version=1,
        content_hash="hash",
        source_name="policy.md",
        mime_type="text/markdown",
        status=DocumentStatus.READY,
        metadata=metadata,
    )


def test_default_config_matches_legacy_fixed_window_splitting() -> None:
    text = "Nội dung ngắn không cần tách."

    legacy = chunk_document(_document(), text, max_chars=1200)
    explicit_default = chunk_document(_document(), text, config=ChunkingConfig(max_chars=1200))

    assert [chunk.text for chunk in legacy] == [chunk.text for chunk in explicit_default]


def test_semantic_chunking_splits_on_topic_change() -> None:
    text = (
        "AAA sentence number one here. AAA sentence number two here. "
        "BBB sentence number three here. BBB sentence number four here."
    )
    config = ChunkingConfig(
        max_chars=100,
        semantic_enabled=True,
        semantic_threshold=0.85,
        embedder=StubEmbedder(),
    )

    chunks = chunk_document(_document(), text, config=config)

    assert len(chunks) == 2
    assert "AAA" in chunks[0].text and "BBB" not in chunks[0].text
    assert "BBB" in chunks[1].text and "AAA" not in chunks[1].text


def test_semantic_chunking_falls_back_to_fixed_window_without_embedder() -> None:
    text = "AAA one. AAA two. BBB three. BBB four."
    config = ChunkingConfig(max_chars=1200, semantic_enabled=True, embedder=None)

    chunks = chunk_document(_document(), text, config=config)

    assert [chunk.text for chunk in chunks] == _split(text, 1200)


def test_semantic_chunking_reconstructs_source_exactly_with_original_whitespace() -> None:
    """Regression: rejoining sentences with a synthesized " " instead of the
    original separator silently corrupted multi-newline text -- caught by the
    golden-set eval's "ordered article chunks" reconstruction check."""
    text = "AAA sentence one here.\n\nAAA sentence two here.\n\nBBB sentence three here."
    config = ChunkingConfig(
        max_chars=1000,
        semantic_enabled=True,
        semantic_threshold=0.85,
        embedder=StubEmbedder(),
    )

    chunks = chunk_document(_document(), text, config=config)

    assert "".join(chunk.text for chunk in chunks) == text.strip()
    assert any("\n\n" in chunk.text for chunk in chunks)


def test_semantic_chunking_still_enforces_hard_max_chars() -> None:
    long_sentence = "AAA " + "x" * 150 + "."
    text = f"{long_sentence} BBB short."
    config = ChunkingConfig(
        max_chars=100,
        semantic_enabled=True,
        semantic_threshold=0.85,
        embedder=StubEmbedder(),
    )

    chunks = chunk_document(_document(), text, config=config)

    assert all(len(chunk.text) <= 100 for chunk in chunks)


def test_parent_identity_is_shared_across_siblings_and_distinct_across_sections() -> None:
    text = "# A\n\n" + ("Câu một. " * 40) + "\n\n# B\n\nNgắn."

    chunks = chunk_document(_document(), text, max_chars=60)

    by_parent: dict[str, list] = {}
    for chunk in chunks:
        assert chunk.parent_id is not None
        by_parent.setdefault(chunk.parent_id, []).append(chunk)

    assert len(by_parent) == 2, "two sections must yield two distinct parent ids"
    for family in by_parent.values():
        assert all(c.parent_child_count == len(family) for c in family)
        assert sorted(c.child_index for c in family) == list(range(len(family)))
        positions = sorted(c.position for c in family)
        assert positions == list(range(positions[0], positions[0] + len(family))), (
            "siblings must occupy contiguous positions"
        )


def test_single_piece_section_still_gets_parent_identity() -> None:
    chunks = chunk_document(_document(), "Đoạn ngắn.", max_chars=1200)

    assert len(chunks) == 1
    assert chunks[0].parent_id is not None
    assert chunks[0].parent_child_count == 1
    assert chunks[0].child_index == 0


def test_parent_id_is_version_scoped() -> None:
    text = "Nội dung."
    v1 = chunk_document(_document(), text)
    document_v2 = _document()
    bumped = document_v2.model_copy(update={"version": 2})

    v2 = chunk_document(bumped, text)

    assert v1[0].parent_id != v2[0].parent_id
