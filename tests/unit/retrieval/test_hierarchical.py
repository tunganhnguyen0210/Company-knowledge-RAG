from domain.schemas import SearchHit, SourceCoordinates
from retrieval.hierarchical import DEFAULT_EXPANSION, ExpansionConfig, expand_with_siblings, parent_key
from tests.support.builders import make_chunk, make_family


def _hits(*chunks) -> list[SearchHit]:
    return [SearchHit(chunk=chunk, score=1.0 - index * 0.01) for index, chunk in enumerate(chunks)]


def _on(**overrides) -> ExpansionConfig:
    return ExpansionConfig(enabled=True, **overrides)


def _ids(hits: list[SearchHit]) -> list[str]:
    return [hit.chunk.id for hit in hits]


def test_disabled_returns_input_unchanged() -> None:
    family = make_family(texts=["a" * 100, "b" * 100])
    hits = _hits(family[0])

    assert expand_with_siblings(hits, sibling_pool=family, config=DEFAULT_EXPANSION) is hits


def test_single_child_family_is_not_expanded() -> None:
    family = make_family(texts=["only child"])
    hits = _hits(family[0])

    assert expand_with_siblings(hits, sibling_pool=family, config=_on()) == hits


def test_two_child_family_pulls_in_missing_sibling_in_position_order() -> None:
    family = make_family(texts=["first half. ", "second half."])
    hits = _hits(family[1])  # only the SECOND child was retrieved

    result = expand_with_siblings(hits, sibling_pool=family, config=_on())

    assert _ids(result) == [family[0].id, family[1].id]
    assert "".join(hit.chunk.text for hit in result) == "first half. second half."


def test_expanded_family_reassembles_section_exactly() -> None:
    """Asserted in the shape `score_retrieval_case` uses: "".join by position."""
    pieces = [f"piece{index}. " for index in range(6)]
    family = make_family(texts=pieces)
    hits = _hits(family[3])

    result = expand_with_siblings(hits, sibling_pool=family, config=_on())

    ordered = sorted(result, key=lambda hit: hit.chunk.position)
    assert "".join(hit.chunk.text for hit in ordered) == "".join(pieces)


def test_family_too_large_for_budget_is_skipped_whole() -> None:
    """All-or-nothing: a partial family would glue non-adjacent text together."""
    family = make_family(texts=["x" * 500 for _ in range(6)])
    hits = _hits(family[0])

    result = expand_with_siblings(hits, sibling_pool=family, config=_on(char_budget=400))

    assert result == hits


def test_family_exceeding_max_parent_chars_is_skipped() -> None:
    family = make_family(texts=["y" * 400 for _ in range(6)])
    hits = _hits(family[0])

    result = expand_with_siblings(
        hits, sibling_pool=family, config=_on(char_budget=99999, max_parent_chars=1000)
    )

    assert result == hits


def test_budget_fits_first_parent_only_leaves_second_untouched() -> None:
    first = make_family(parent_id="p1", texts=["a" * 100, "b" * 100], base_position=0)
    second = make_family(parent_id="p2", texts=["c" * 100, "d" * 100], base_position=10)
    hits = _hits(first[0], second[0])

    result = expand_with_siblings(
        hits, sibling_pool=[*first, *second], config=_on(char_budget=100)
    )

    assert _ids(result) == [first[0].id, first[1].id, second[0].id]


def test_max_parents_limits_how_many_families_expand() -> None:
    first = make_family(parent_id="p1", texts=["a" * 10, "b" * 10], base_position=0)
    second = make_family(parent_id="p2", texts=["c" * 10, "d" * 10], base_position=10)
    hits = _hits(first[0], second[0])

    result = expand_with_siblings(
        hits, sibling_pool=[*first, *second], config=_on(max_parents=1)
    )

    assert _ids(result) == [first[0].id, first[1].id, second[0].id]


def test_raptor_summary_node_is_never_expanded_or_injected() -> None:
    raptor_a = make_chunk(chunk_id="r1", text="summary one", section="__raptor_summary_L1__", position=90)
    raptor_b = make_chunk(chunk_id="r2", text="summary two", section="__raptor_summary_L1__", position=91)
    hits = _hits(raptor_a)

    result = expand_with_siblings(hits, sibling_pool=[raptor_a, raptor_b], config=_on())

    assert result == hits
    assert parent_key(raptor_a) is None


def test_incomplete_family_fails_closed() -> None:
    """Pool is missing a member -- gluing the rest would corrupt the evidence span."""
    family = make_family(texts=["one. ", "two. ", "three."])
    pool = [family[0], family[2]]  # middle sibling absent
    hits = _hits(family[0])

    result = expand_with_siblings(hits, sibling_pool=pool, config=_on())

    assert result == hits


def test_output_never_contains_duplicate_chunks() -> None:
    family = make_family(texts=["a" * 20, "b" * 20, "c" * 20])
    hits = _hits(family[0], family[2])  # two members of the same family already present

    result = expand_with_siblings(hits, sibling_pool=family, config=_on())

    assert _ids(result) == [family[0].id, family[1].id, family[2].id]
    assert len({hit.chunk.id for hit in result}) == len(result)


def test_derived_key_does_not_merge_same_heading_at_distant_positions() -> None:
    """Legacy payload path: identical heading + coordinates, non-contiguous positions."""
    shared = SourceCoordinates(doc_id="policy.md")
    near = [
        make_chunk(chunk_id="n0", text="near zero. ", section="Mục 1", position=0, coordinates=shared),
        make_chunk(chunk_id="n1", text="near one.", section="Mục 1", position=1, coordinates=shared),
    ]
    far = make_chunk(chunk_id="f9", text="far away.", section="Mục 1", position=40, coordinates=shared)
    hits = _hits(near[0])

    result = expand_with_siblings(hits, sibling_pool=[*near, far], config=_on())

    assert _ids(result) == ["n0", "n1"]
    assert "f9" not in _ids(result)


def test_legacy_family_without_declared_count_still_expands() -> None:
    family = make_family(texts=["alpha. ", "beta."], declare_count=False)
    hits = _hits(family[0])

    result = expand_with_siblings(hits, sibling_pool=family, config=_on())

    assert _ids(result) == [family[0].id, family[1].id]


def test_min_pool_coverage_gate_blocks_thinly_represented_family() -> None:
    family = make_family(texts=[f"p{index}. " for index in range(6)])
    hits = _hits(family[0])
    ranking_pool = _hits(family[0])  # 1 of 6 present in the ranking pool

    result = expand_with_siblings(
        hits, sibling_pool=family, ranking_pool=ranking_pool, config=_on(min_pool_coverage=0.6)
    )

    assert result == hits


def test_anchor_ordering_is_preserved_so_top_hit_stays_first() -> None:
    first = make_family(parent_id="p1", texts=["a" * 10, "b" * 10], base_position=0)
    second = make_family(parent_id="p2", texts=["c" * 10, "d" * 10], base_position=10)
    hits = _hits(second[0], first[0])  # second family outranks first

    result = expand_with_siblings(hits, sibling_pool=[*first, *second], config=_on())

    assert result[0].chunk.id == second[0].id
    assert _ids(result) == [second[0].id, second[1].id, first[0].id, first[1].id]
