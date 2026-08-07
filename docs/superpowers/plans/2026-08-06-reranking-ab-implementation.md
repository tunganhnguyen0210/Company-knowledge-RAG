# Retrieval Reranking A/B Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a 50-result hybrid candidate pool rerankable, safely fall back to RRF, and compare the existing and reranked configurations.

**Architecture:** `Settings` provides a candidate-pool limit. `QdrantChunkStore` uses it for both dense and lexical candidates, fuses the candidates, and falls back to fused RRF results if the configured external reranker fails. Evaluation lineage records the setting so reports are comparable.

**Tech Stack:** Python 3.11, Pydantic Settings, Qdrant client, Jina Reranker API, pytest.

## Global Constraints

- Default `rerank_candidate_limit` is `50`; public retrieval output remains `retrieval_limit` (default 5).
- No reindexing or API contract changes.
- Empty `RERANKER_MODEL` remains the immediate rollback switch.

---

### Task 1: Candidate pool and failure fallback

**Files:**
- Modify: `src/retrieval/qdrant_store.py`
- Modify: `tests/unit/retrieval/test_qdrant_store.py`

**Interfaces:**
- Produces: `QdrantChunkStore(..., rerank_candidate_limit: int = 50)`.
- Produces: `search()` passes the configured pool to dense, lexical and RRF stages when reranking is enabled.

- [ ] **Step 1: Write failing tests**

```python
def test_reranker_receives_configured_candidate_pool() -> None:
    # Fake client returns 50 dense candidates and fake reranker records hits.
    assert reranker.received_count == 50

def test_reranker_failure_returns_rrf_results() -> None:
    # Fake reranker raises ProviderError.
    assert [hit.chunk.id for hit in store.search("query", limit=5)] == expected_rrf_ids
```

- [ ] **Step 2: Run tests to verify RED**

Run: `uv run pytest tests/unit/retrieval/test_qdrant_store.py -q`

Expected: failure because the constructor has no candidate-pool setting and reranker errors escape.

- [ ] **Step 3: Implement minimal retrieval behavior**

```python
candidate_limit = self.rerank_candidate_limit if self.reranker else limit
# Use candidate_limit for dense, lexical, and fused candidates.
try:
    return self.reranker.rerank(query, fused, top_n=limit)
except ProviderError:
    return fused[:limit]
```

- [ ] **Step 4: Run focused tests to verify GREEN**

Run: `uv run pytest tests/unit/retrieval/test_qdrant_store.py -q`

Expected: PASS.

### Task 2: Configuration and eval lineage

**Files:**
- Modify: `src/settings.py`
- Modify: `src/api/app.py`
- Modify: `src/evaluation/cli.py`
- Modify: `tests/unit/test_settings.py`

**Interfaces:**
- Produces: `Settings.rerank_candidate_limit: int`, default 50.
- Consumes: the field in `QdrantChunkStore` construction and persisted evaluation configuration.

- [ ] **Step 1: Write failing settings test**

```python
def test_settings_default_rerank_candidate_limit() -> None:
    assert Settings(_env_file=None).rerank_candidate_limit == 50
```

- [ ] **Step 2: Run test to verify RED**

Run: `uv run pytest tests/unit/test_settings.py::test_settings_default_rerank_candidate_limit -q`

Expected: failure because the setting does not exist.

- [ ] **Step 3: Implement setting and pass it through**

```python
rerank_candidate_limit: int = Field(default=50, ge=5)
```

Pass it from `_build_qdrant_store()` to the store and add it to `_runtime_configuration()`.

- [ ] **Step 4: Run focused tests to verify GREEN**

Run: `uv run pytest tests/unit/test_settings.py tests/unit/retrieval/test_qdrant_store.py -q`

Expected: PASS.

### Task 3: Verify and run A/B evaluations

**Files:**
- Create: `reports/rag_evaluation/ab/*` (ignored artifacts)

- [ ] **Step 1: Run affected unit tests and static checks**

Run: `uv run pytest tests/unit/test_settings.py tests/unit/retrieval/test_qdrant_store.py tests/unit/providers/test_jina.py -q; uv run ruff check src/settings.py src/api/app.py src/retrieval/qdrant_store.py src/evaluation/cli.py`

Expected: all pass.

- [ ] **Step 2: Run RRF-only control**

Run: `RERANKER_MODEL='' uv run rag-eval e2e --ingest data/extracted/01_2021_ND-CP_283247.md --output-root reports/rag_evaluation/ab/control`

- [ ] **Step 3: Run Jina-reranked treatment**

Run: `RERANKER_MODEL=jina-reranker-v3.5 uv run rag-eval e2e --ingest data/extracted/01_2021_ND-CP_283247.md --output-root reports/rag_evaluation/ab/reranked`

- [ ] **Step 4: Compare reports**

Report Evidence Recall, citation metrics, retrieval P95 and E2E P95. Treat provider-rate-limit cases as incomplete evidence, not quality gains.
