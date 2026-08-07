"""Sibling expansion: re-assemble a whole legal section around a retrieved chunk.

When a query hits one chunk of a multi-chunk section, the evidence the user
actually needs is often in a neighbouring chunk of the same section. This module
pulls the missing siblings into the result set so the section reads whole.

Two properties drive the design:

1. **Siblings are returned as real `SearchHit`s, not folded into a "parent
   context" blob.** Downstream scoring (`evaluation.metrics.score_retrieval_case`)
   only ever looks at the `text` of *returned* hits, and citations index into the
   returned list -- so a sibling must be a first-class hit to count, and it is
   legitimately citable because it is a real chunk with real coordinates.

2. **Expansion is all-or-nothing per parent.** `score_retrieval_case` joins a
   section's retrieved chunks with `"".join(...)` -- no separator -- because
   `chunker._split` guarantees the pieces concatenate back to the exact section.
   A family missing a middle piece therefore glues piece 1 straight onto piece 3
   and the evidence span never matches. Partially filling a parent costs prompt
   budget and buys exactly nothing, so a family that does not fit is skipped
   whole.

Selection is greedy by rank rather than by a coverage ratio: the anchor chunks
are already the best-ranked results, and a ratio gate over the final top-K
structurally cannot fire for large sections (they would need to occupy most of
the K slots) -- precisely the sections where re-assembly matters most.
`min_pool_coverage` is retained as an optional knob, evaluated against the
*ranking* pool, never the sibling pool.
"""

from __future__ import annotations

from dataclasses import dataclass

from domain.schemas import RAPTOR_SECTION_PREFIX, Chunk, SearchHit


@dataclass(frozen=True)
class ExpansionConfig:
    enabled: bool = False
    max_parents: int = 3
    char_budget: int = 8000
    """Total characters that may be ADDED across all expanded parents."""
    max_parent_chars: int = 8000
    """Refuse to expand any single section larger than this."""
    min_pool_coverage: float = 0.0
    """Optional gate: fraction of a family that must appear in the ranking pool."""


DEFAULT_EXPANSION = ExpansionConfig()


def parent_key(chunk: Chunk) -> str | None:
    """Group key for "chunks of the same section", or None if not expandable.

    Prefers the explicit `parent_id` written at ingest. Falls back to a derived
    key so an index built before that field existed can still be expanded
    without a re-ingest. Coordinates alone are unsafe as a key: chapter-heading
    sections carry `article=None`, and documents parsed via generic headings get
    `(doc_id, None, None)` for *every* section -- keying on coordinates would
    merge a whole document into one "section". The section heading disambiguates,
    and `_contiguous_run` guards the remaining ambiguity.
    """
    if chunk.section and chunk.section.startswith(RAPTOR_SECTION_PREFIX):
        return None  # synthetic summary node: no real parent, coordinates approximate
    if chunk.parent_id:
        return chunk.parent_id
    coordinates = chunk.coordinates
    return (
        f"{chunk.document_id}:v{chunk.version}:"
        f"{coordinates.doc_id}|{coordinates.chapter}|{coordinates.article}|{chunk.section}"
    )


def expand_with_siblings(
    hits: list[SearchHit],
    *,
    sibling_pool: list[Chunk],
    ranking_pool: list[SearchHit] | None = None,
    config: ExpansionConfig = DEFAULT_EXPANSION,
) -> list[SearchHit]:
    """Return `hits` with whole sibling families spliced in around their anchors.

    `sibling_pool` supplies the chunks to splice in; callers already hold every
    candidate chunk in memory, so this costs no extra fetch. `ranking_pool` is
    only consulted by the optional `min_pool_coverage` gate.
    """
    if not config.enabled or not hits:
        return hits

    families = _index_families(sibling_pool, hits)
    hit_by_id = {hit.chunk.id: hit for hit in hits}
    pool_counts = _ranking_pool_counts(ranking_pool) if config.min_pool_coverage > 0 else {}

    remaining = config.char_budget
    expansions: dict[str, list[Chunk]] = {}
    for key, anchor in _anchors(hits)[: config.max_parents]:
        family = _contiguous_run(families[key], anchor.chunk)
        if not _is_complete(family):
            continue
        if config.min_pool_coverage > 0:
            coverage = pool_counts.get(key, 0) / len(family)
            if coverage < config.min_pool_coverage:
                continue
        added = sum(len(chunk.text) for chunk in family if chunk.id not in hit_by_id)
        total = sum(len(chunk.text) for chunk in family)
        if added == 0 or total > config.max_parent_chars or added > remaining:
            continue  # all-or-nothing: never partially fill a family
        remaining -= added
        expansions[key] = family

    if not expansions:
        return hits
    return _emit(hits, expansions, hit_by_id)


def _index_families(sibling_pool: list[Chunk], hits: list[SearchHit]) -> dict[str, list[Chunk]]:
    grouped: dict[str, dict[str, Chunk]] = {}
    for chunk in [*sibling_pool, *(hit.chunk for hit in hits)]:
        key = parent_key(chunk)
        if key is None:
            continue
        grouped.setdefault(key, {})[chunk.id] = chunk
    return {key: sorted(members.values(), key=lambda c: c.position) for key, members in grouped.items()}


def _anchors(hits: list[SearchHit]) -> list[tuple[str, SearchHit]]:
    """Distinct expandable parents, in rank order of their best-ranked chunk."""
    ordered: list[tuple[str, SearchHit]] = []
    seen: set[str] = set()
    for hit in hits:
        key = parent_key(hit.chunk)
        if key is None or key in seen:
            continue
        seen.add(key)
        ordered.append((key, hit))
    return ordered


def _ranking_pool_counts(ranking_pool: list[SearchHit] | None) -> dict[str, int]:
    counts: dict[str, int] = {}
    for hit in ranking_pool or []:
        key = parent_key(hit.chunk)
        if key is not None:
            counts[key] = counts.get(key, 0) + 1
    return counts


def _contiguous_run(family: list[Chunk], anchor: Chunk) -> list[Chunk]:
    """Maximal run of consecutive `position` values containing the anchor.

    Protects the derived-key path: two same-heading sections elsewhere in the
    document must not merge into one family. A no-op when `parent_id` is explicit.
    """
    index = next((i for i, chunk in enumerate(family) if chunk.id == anchor.id), None)
    if index is None:
        return []
    start = index
    while start > 0 and family[start - 1].position == family[start].position - 1:
        start -= 1
    end = index
    while end + 1 < len(family) and family[end + 1].position == family[end].position + 1:
        end += 1
    return family[start : end + 1]


def _is_complete(family: list[Chunk]) -> bool:
    """Reject families we cannot prove are whole -- gluing a gap corrupts evidence."""
    if len(family) <= 1:
        return False
    declared = {chunk.parent_child_count for chunk in family if chunk.parent_child_count is not None}
    if not declared:
        return True  # legacy payload: contiguity is the only available guarantee
    return len(declared) == 1 and declared.pop() == len(family)


def _emit(
    hits: list[SearchHit],
    expansions: dict[str, list[Chunk]],
    hit_by_id: dict[str, SearchHit],
) -> list[SearchHit]:
    """Walk hits in rank order, emitting each expanded family contiguously.

    Rank order is preserved so the top result stays first, and each section reads
    as one uninterrupted block rather than being scattered through the prompt.
    """
    output: list[SearchHit] = []
    emitted_ids: set[str] = set()
    emitted_keys: set[str] = set()
    for hit in hits:
        key = parent_key(hit.chunk)
        if key in expansions:
            if key in emitted_keys:
                continue
            emitted_keys.add(key)
            for chunk in expansions[key]:
                if chunk.id in emitted_ids:
                    continue
                emitted_ids.add(chunk.id)
                existing = hit_by_id.get(chunk.id)
                output.append(existing or SearchHit(chunk=chunk, score=hit.score))
        elif hit.chunk.id not in emitted_ids:
            emitted_ids.add(hit.chunk.id)
            output.append(hit)
    return output
