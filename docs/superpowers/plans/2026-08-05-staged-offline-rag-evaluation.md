# Staged Offline RAG Evaluation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `rag-eval` staged offline evaluator for deterministic legal metadata, replayable ingestion/retrieval/generation runs, and report-only Ragas metrics against the finalized 100-case golden dataset.

**Architecture:** One deep `EvaluationRunner.run(EvaluationRequest) -> EvaluationReport` module owns orchestration. Production ingestion and generation gain typed evidence at internal seams; immutable index, retrieval, and generation artifacts let developers recompute only the phase they changed while preserving a final end-to-end confirmation path.

**Tech Stack:** Python 3.11+, Pydantic v2, argparse, FastAPI application wiring, Qdrant, pytest, Ragas v0.4, OpenAI-compatible async judge client, JSON/JSONL artifacts.

## Global Constraints

- Treat `evaluation/GOLDEN_SET_SPEC.md` as authoritative: five files, 20 cases per file, 100 cases total, prefixed string IDs, and exact `doc_id/chapter/article` grounding.
- Use `data/raw/01_2021_ND-CP_283247.docx` as the first real ingestion input and `data/extracted/01_2021_ND-CP_283247.md` as the canonical grounding source.
- Preserve physical `source_name=01_2021_ND-CP_283247.docx`, internal UUID `document_id`, and canonical `doc_id=01_2021_ND-CP_283247.md` as separate identities.
- LLM enrichment may modify retrieval text, summaries, and synthetic questions; it must never modify deterministic source coordinates.
- Keep the public `ChatResponse` schema and existing citation-gated abstention behavior unchanged.
- Replace the console entrypoint `company-rag-evaluate` with `rag-eval`; do not add a compatibility alias unless the user requests one.
- Pin Ragas to `>=0.4,<0.5` and record the exact installed version in run manifests.
- Treat `langchain-community<0.4` only as a resolver probe for the known Ragas import break; commit the exact equality constraint emitted from the verified installed version only after `import ragas.metrics.collections` passes.
- Ragas is opt-in for v1. Only `retrieval`, `generation`, and `e2e` accept `--ragas`; without it, no judge client is built and no semantic call is made.
- Apply the user's approved P0-3 option (a): trim AMB-014 context index 1 before `# Chương IX` and AMB-019 context index 1 before `# Chương IV`, then reissue the ambiguous file and regenerate/reconcile the migration and grounding-review evidence before claiming full conformance.
- Correctness invariants block. Deterministic quality rates and Ragas scores compare against `0.85` but remain report-only.
- Only complete, unfiltered, 100-case end-to-end runs may set `baseline_eligible=true`.
- All shell commands in this plan use the repository-required `rtk` prefix.
- Preserve unrelated worktree changes, including the user's deleted legacy helper scripts. Stage only paths named by each task.

---

## Planned File Structure

### New production files

- `src/ingestion/structure.py` — deterministic Markdown legal hierarchy extraction.
- `src/generation/execution.py` — internal retrieval/generation evidence models.
- `src/evaluation/golden.py` — finalized golden schema, loading, validation, and case selection.
- `src/evaluation/artifacts.py` — immutable phase artifacts, requests, reports, and fingerprints.
- `src/evaluation/repository.py` — local JSON/JSONL artifact persistence and in-memory test adapter.
- `src/evaluation/metrics.py` — deterministic retrieval/generation metric calculations.
- `src/evaluation/ragas_adapter.py` — injected Ragas v0.4 judge implementation.
- `src/evaluation/cli.py` — `rag-eval` subcommands and argument validation.

### Existing production files to modify

- `src/domain/schemas.py` — add typed source coordinates to chunks.
- `src/ingestion/chunker.py` — chunk structured article sections and retain coordinates.
- `src/ingestion/service.py` — pass canonical identity through chunking and tracing.
- `src/retrieval/base.py` — add indexed-document inspection to the store interface.
- `src/retrieval/memory_store.py` — implement indexed-document inspection.
- `src/retrieval/qdrant_store.py` — flatten/index coordinates and implement snapshot reads.
- `src/generation/service.py` — return internal execution evidence and project it to `ChatResponse`.
- `src/evaluation/runner.py` — replace the legacy loop with staged orchestration.
- `src/settings.py` and `.env.example` — configure the OpenAI-compatible Ragas judge.
- `src/cli.py` — remove the obsolete evaluation entrypoint.
- `pyproject.toml` and `uv.lock` — register `rag-eval` and pin Ragas v0.4.
- `.gitignore` — ignore local evaluation evidence under `reports/rag_evaluation/`.

### New tests

- `tests/unit/evaluation/test_golden.py`
- `tests/unit/ingestion/test_structure.py`
- `tests/unit/evaluation/test_validation.py`
- `tests/component/evaluation/test_validation.py`
- `tests/unit/generation/test_execution.py`
- `tests/unit/evaluation/test_artifacts.py`
- `tests/unit/evaluation/test_metrics.py`
- `tests/unit/evaluation/test_runner.py`
- `tests/unit/evaluation/test_ragas.py`
- `tests/component/api/test_evaluation_cli.py`
- `tests/support/evaluation_fakes.py` â€” concrete golden, chunk, artifact, judge, and runner test adapters shared by the new evaluation tests.

### Existing tests and docs to modify

- `tests/support/builders.py`, `tests/unit/generation/test_citation_gate.py`, `tests/unit/generation/test_tracing.py`, `tests/component/rag/test_retrieve_and_answer.py`, `tests/unit/ingestion/test_service.py`, `tests/unit/retrieval/test_qdrant_store.py`, `tests/unit/retrieval/test_retrieval.py`, `tests/unit/generation/test_abstention.py`, `tests/unit/ingestion/test_enrichment.py`, `tests/unit/retrieval/test_hybrid.py`, `tests/unit/providers/test_jina.py`, and `tests/unit/prompts/test_prompt.py` — supply required coordinates and prove unchanged behavior.
- `README.md`, `docs/architectures/01-system-context.md`, `docs/architectures/02-document-loading-and-ingestion.md`, `docs/architectures/04-retrieval-generation-and-citations.md`, and `docs/architectures/05-observability-evaluation-and-operations.md` — document staged evaluation and the short CLI.

### Approved golden-data reissue files

- `evaluation/golden_set/golden_set_ambiguous.json` — trim the two approved boundary-crossing contexts without changing IDs, questions, answers, metadata, or case counts.
- `evaluation/id_migration_map.json` — issue the legacy-to-prefixed direct-lookup ID map, including retired legacy ID `65`.
- `evaluation/golden_set_grounding_review.json` — record deterministic 100-case/130-context exact-source and coordinate review evidence.
- `evaluation/GOLDEN_SET_SPEC.md` — define both audit-artifact contracts and reconcile section 9 with the approved reissue.

---

### Task 0: Approved Golden-Data Reissue and Audit Evidence

**Files:**
- Modify: `evaluation/golden_set/golden_set_ambiguous.json`
- Create: `evaluation/id_migration_map.json`
- Create: `evaluation/golden_set_grounding_review.json`
- Modify: `evaluation/GOLDEN_SET_SPEC.md`

**Interfaces:**
- Consumes: the finalized five golden files, canonical `data/extracted/01_2021_ND-CP_283247.md`, the historical direct-lookup IDs at `f97292a^`, and the user's approved P0-3 option (a).
- Produces: a reissued five-file/100-case dataset whose 130 contexts are exact canonical substrings contained by their declared articles, plus machine-checkable ID-migration and grounding-review evidence consumed by Task 4.

- [ ] **Step 1: Run the read-only failing prerequisite probe**

```powershell
@'
import json
from pathlib import Path

root = Path("evaluation")
cases = json.loads((root / "golden_set/golden_set_ambiguous.json").read_text(encoding="utf-8"))
by_id = {case["id"]: case for case in cases}
assert "\n\n# Chương IX" not in by_id["AMB-014"]["golden_truth_contexts"][1]["golden_truth_context"]
assert "\n\n# Chương IV" not in by_id["AMB-019"]["golden_truth_contexts"][1]["golden_truth_context"]
assert (root / "id_migration_map.json").is_file()
assert (root / "golden_set_grounding_review.json").is_file()
'@ | rtk proxy uv run python -
```

Expected: FAIL because both selected contexts cross their declared article boundary and both audit artifacts are absent. Do not weaken the coordinate rule.

- [ ] **Step 2: Trim exactly the two approved context entries**

```powershell
@'
import json
from pathlib import Path

path = Path("evaluation/golden_set/golden_set_ambiguous.json")
cases = json.loads(path.read_text(encoding="utf-8"))
boundaries = {"AMB-014": "Chương IX", "AMB-019": "Chương IV"}
for case in cases:
    if case["id"] not in boundaries:
        continue
    marker = f"\n\n# {boundaries[case['id']]}"
    original = case["golden_truth_contexts"][1]["golden_truth_context"]
    assert original.count(marker) == 1
    trimmed = original.split(marker, 1)[0].rstrip()
    assert trimmed and len(trimmed) < len(original)
    case["golden_truth_contexts"][1]["golden_truth_context"] = trimmed
path.write_text(json.dumps(cases, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
'@ | rtk proxy uv run python -
```

Expected: only AMB-014 context index 1 and AMB-019 context index 1 change. IDs, metadata, questions, answers, context counts, file count, and case count remain unchanged.

- [ ] **Step 3: Issue the explicit migration evidence**

Create `evaluation/id_migration_map.json` with `schema_version=1`, `migration_commit="f97292a"`, and this complete `old_to_new` map:

```json
{
  "1": "DL-001", "5": "DL-002", "7": "DL-003", "9": "DL-004",
  "13": "DL-005", "17": "DL-006", "21": "DL-007", "25": "DL-008",
  "29": "DL-009", "33": "DL-010", "37": "DL-011", "41": "DL-012",
  "45": "DL-013", "49": "DL-014", "53": "DL-015", "57": "DL-016",
  "61": "DL-017", "65": null, "69": "DL-018", "73": "DL-019", "77": "DL-020"
}
```

Add `retired=[{"old_id":"65","status":"retired","reason":"The question asks for a number of days while Article 35 defines the filing-time event, so it is not a sound direct lookup."}]`. Do not reuse ID `65` or invent a replacement.

- [ ] **Step 4: Define artifact schemas and reconcile the issued status**

In `evaluation/GOLDEN_SET_SPEC.md` section 5, define the migration artifact fields `schema_version`, `migration_commit`, `old_to_new`, and `retired`; every non-null target must be a unique issued `DL-*` ID and every null source must have one retired record. In section 7.2, define the grounding-review fields `schema_version`, `canonical_doc_id`, `canonical_sha256`, `dataset_sha256`, `validated_cases`, `validated_contexts`, and per-case `case_id`, `status`, plus per-context `context_index`, `context_sha256`, `exact_source`, and `coordinate_match`.

Update section 9 only after Steps 2-3: record the approved 2026-08-05 reissue, name AMB-014/AMB-019 context index 1, state both were trimmed at the declared article boundary without changing IDs or metadata, and state that the regenerated review proves 100/100 cases and 130/130 contexts pass.

- [ ] **Step 5: Generate and verify grounding-review evidence**

Run this complete generator, which uses Task 2's markup-agnostic article slices and writes only after every assertion passes:

```powershell
@'
import hashlib, json, re
from pathlib import Path

root = Path("evaluation")
names = ["golden_set_direct_lookup.json", "golden_set_multi_hop.json", "golden_set_unanswerable.json", "golden_set_ambiguous.json", "golden_set_adversarial.json"]
files = [root / "golden_set" / name for name in names]
cases = [case for path in files for case in json.loads(path.read_text(encoding="utf-8"))]
canonical_path = Path("data/extracted/01_2021_ND-CP_283247.md")
canonical = canonical_path.read_text(encoding="utf-8")
heading_re = re.compile(r"(?m)^(?:#{1,6}[ \t]+)?((?:Chương[ \t]+[IVXLCDM]+|Điều[ \t]+\d+[A-Za-z]?)\b.*)$")
chapter_re = re.compile(r"^Chương\s+[IVXLCDM]+\b", re.IGNORECASE)
article_re = re.compile(r"^(Điều\s+\d+[A-Za-z]?)\b", re.IGNORECASE)
matches = list(heading_re.finditer(canonical))
chapter = None
articles = {}
for index, match in enumerate(matches):
    heading = match.group(1).strip()
    if chapter_match := chapter_re.match(heading):
        chapter = chapter_match.group(0)
    if article_match := article_re.match(heading):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(canonical)
        articles[(canonical_path.name, chapter, article_match.group(1))] = canonical[match.start():end].strip()
records = []
for case in cases:
    contexts = []
    for context_index, item in enumerate(case["golden_truth_contexts"]):
        evidence = item["golden_truth_context"]
        metadata = item["golden_metadata"]
        key = (metadata["doc_id"], metadata["chapter"], metadata["article"])
        contexts.append({"context_index": context_index, "context_sha256": hashlib.sha256(evidence.encode()).hexdigest(), "exact_source": evidence in canonical, "coordinate_match": evidence in articles.get(key, "")})
    records.append({"case_id": case["id"], "status": "passed" if all(item["exact_source"] and item["coordinate_match"] for item in contexts) else "failed", "contexts": contexts})
assert len(files) == 5 and len(cases) == 100 and len({case["id"] for case in cases}) == 100
assert sum(len(case["golden_truth_contexts"]) for case in cases) == 130
assert all(record["status"] == "passed" for record in records)
dataset_bytes = json.dumps(cases, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
review = {"schema_version": 1, "canonical_doc_id": canonical_path.name, "canonical_sha256": hashlib.sha256(canonical.encode()).hexdigest(), "dataset_sha256": hashlib.sha256(dataset_bytes).hexdigest(), "validated_cases": 100, "validated_contexts": 130, "cases": records}
(root / "golden_set_grounding_review.json").write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
'@ | rtk proxy uv run python -
```

Rerun Step 1, then verify migration targets are exactly `DL-001..DL-020`, old ID `65` is null and retired, recorded hashes match current files, and the review has exactly 100 passed cases/130 passed contexts.

Expected: both probes PASS; section 9 is supported by artifacts that exist and match the reissued data.

- [ ] **Step 6: Review and commit the reissue atomically**

```powershell
rtk git diff --check
rtk git diff -- evaluation/golden_set/golden_set_ambiguous.json evaluation/id_migration_map.json evaluation/golden_set_grounding_review.json evaluation/GOLDEN_SET_SPEC.md
rtk git add evaluation/golden_set/golden_set_ambiguous.json evaluation/id_migration_map.json evaluation/golden_set_grounding_review.json evaluation/GOLDEN_SET_SPEC.md
rtk git commit -m "data: reissue grounded golden evidence"
```

Expected: only the two approved context values, the two evidence files, and their specification/status contract change.

---

### Task 1: Finalized Golden Dataset Contract and Selection

**Files:**
- Create: `src/evaluation/golden.py`
- Create: `tests/unit/evaluation/test_golden.py`
- Modify: `src/evaluation/__init__.py`

**Interfaces:**
- Consumes: finalized JSON files under `evaluation/golden_set/`.
- Produces: `GoldenCase`, `GoldenDataset`, `load_golden_dataset(directory: Path, files: list[Path] | None = None) -> GoldenDataset`, and `select_cases(dataset: GoldenDataset, *, question_types: set[GoldenType] | None, case_ids: set[str] | None, limit: int | None) -> list[GoldenCase]` for every later task.

- [ ] **Step 1: Write failing schema and authoritative-file tests**

```python
# tests/unit/evaluation/test_golden.py
from pathlib import Path

import pytest
from pydantic import ValidationError

from evaluation.golden import TYPE_PREFIXES, GoldenCase, GoldenType, load_golden_dataset


def test_loads_finalized_authoritative_dataset() -> None:
    dataset = load_golden_dataset(Path("evaluation/golden_set"))

    assert len(dataset.cases) == 100
    assert {case.type for case in dataset.cases} == set(GoldenType)
    assert {case.id for case in dataset.cases if case.type is GoldenType.DIRECT_LOOKUP} == {
        f"DL-{index:03d}" for index in range(1, 21)
    }
    for kind, prefix in TYPE_PREFIXES.items():
        assert {case.id for case in dataset.cases if case.type is kind} == {
            f"{prefix}-{index:03d}" for index in range(1, 21)
        }


def test_unanswerable_rejects_non_empty_contexts() -> None:
    with pytest.raises(ValidationError, match="unanswerable contexts must be empty"):
        GoldenCase.model_validate(
            {
                "id": "UA-001",
                "type": "unanswerable",
                "question": "Ngoài phạm vi?",
                "expected_answer": "Không có thông tin.",
                "golden_truth_contexts": [
                    {
                        "golden_truth_context": "evidence",
                        "golden_metadata": {
                            "doc_id": "01_2021_ND-CP_283247.md",
                            "chapter": "Chương I",
                            "article": "Điều 1",
                        },
                    }
                ],
                "difficulty": "easy",
            }
        )
```

- [ ] **Step 2: Run the focused tests and confirm the module is missing**

Run:

```powershell
rtk proxy uv run pytest -p no:cacheprovider tests/unit/evaluation/test_golden.py -q
```

Expected: FAIL during collection with `ModuleNotFoundError` or missing finalized models.

- [ ] **Step 3: Implement strict Pydantic golden models and the five-file loader**

```python
# src/evaluation/golden.py
from __future__ import annotations

import json
import re
from collections import Counter, deque
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator


class GoldenType(StrEnum):
    DIRECT_LOOKUP = "direct_lookup"
    MULTI_HOP = "multi_hop"
    UNANSWERABLE = "unanswerable"
    AMBIGUOUS = "ambiguous"
    ADVERSARIAL = "adversarial"


class Difficulty(StrEnum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


TYPE_FILES = {
    GoldenType.DIRECT_LOOKUP: "golden_set_direct_lookup.json",
    GoldenType.MULTI_HOP: "golden_set_multi_hop.json",
    GoldenType.UNANSWERABLE: "golden_set_unanswerable.json",
    GoldenType.AMBIGUOUS: "golden_set_ambiguous.json",
    GoldenType.ADVERSARIAL: "golden_set_adversarial.json",
}
TYPE_PREFIXES = {
    GoldenType.DIRECT_LOOKUP: "DL",
    GoldenType.MULTI_HOP: "MH",
    GoldenType.UNANSWERABLE: "UA",
    GoldenType.AMBIGUOUS: "AMB",
    GoldenType.ADVERSARIAL: "ADV",
}


class GoldenMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    doc_id: str
    chapter: str
    article: str


class GoldenContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    golden_truth_context: str = Field(min_length=1)
    golden_metadata: GoldenMetadata


class GoldenCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^(DL|MH|UA|AMB|ADV)-\d{3}$")
    type: GoldenType
    question: str = Field(min_length=1)
    expected_answer: str = Field(min_length=1)
    golden_truth_contexts: list[GoldenContext]
    difficulty: Difficulty

    @model_validator(mode="after")
    def validate_type_contract(self) -> "GoldenCase":
        expected_prefix = TYPE_PREFIXES[self.type]
        if not self.id.startswith(f"{expected_prefix}-"):
            raise ValueError(f"id prefix must be {expected_prefix} for {self.type}")
        if self.type is GoldenType.UNANSWERABLE and self.golden_truth_contexts:
            raise ValueError("unanswerable contexts must be empty")
        if self.type is not GoldenType.UNANSWERABLE and not self.golden_truth_contexts:
            raise ValueError("answerable cases require at least one context")
        if self.type is GoldenType.MULTI_HOP and len(self.golden_truth_contexts) < 2:
            raise ValueError("multi_hop requires at least two contexts")
        return self


class GoldenDataset(BaseModel):
    cases: list[GoldenCase]
    source_files: list[str]
    scope: str = "full"


def load_golden_dataset(directory: Path, files: list[Path] | None = None) -> GoldenDataset:
    selected = files or [directory / TYPE_FILES[item] for item in GoldenType]
    cases: list[GoldenCase] = []
    for path in selected:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise ValueError(f"{path} must contain a JSON array")
        parsed = [GoldenCase.model_validate(item) for item in raw]
        if files is None:
            expected_type = next(kind for kind, name in TYPE_FILES.items() if name == path.name)
            if len(parsed) != 20 or any(case.type is not expected_type for case in parsed):
                raise ValueError(f"{path.name} must contain 20 {expected_type} cases")
            expected_ids = {
                f"{TYPE_PREFIXES[expected_type]}-{index:03d}"
                for index in range(1, 21)
            }
            actual_ids = {case.id for case in parsed}
            if actual_ids != expected_ids:
                raise ValueError(
                    f"{path.name} ids must be {sorted(expected_ids)}; got {sorted(actual_ids)}"
                )
        cases.extend(parsed)
    duplicates = [case_id for case_id, count in Counter(case.id for case in cases).items() if count > 1]
    if duplicates:
        raise ValueError(f"duplicate case ids: {sorted(duplicates)}")
    if files is None and len(cases) != 100:
        raise ValueError("authoritative dataset must contain 100 cases")
    return GoldenDataset(
        cases=cases,
        source_files=[str(path) for path in selected],
        scope="partial" if files is not None else "full",
    )
```

- [ ] **Step 4: Add deterministic type/case/limit selection tests**

```python
# append to tests/unit/evaluation/test_golden.py
from evaluation.golden import select_cases


def test_limit_round_robins_across_selected_types() -> None:
    dataset = load_golden_dataset(Path("evaluation/golden_set"))

    selected = select_cases(dataset, question_types=None, case_ids=None, limit=10)

    counts = {kind: sum(case.type is kind for case in selected) for kind in GoldenType}
    assert counts == {kind: 2 for kind in GoldenType}


def test_case_ids_must_exist_inside_type_filter() -> None:
    dataset = load_golden_dataset(Path("evaluation/golden_set"))

    with pytest.raises(ValueError, match="outside selected scope"):
        select_cases(
            dataset,
            question_types={GoldenType.DIRECT_LOOKUP},
            case_ids={"MH-001"},
            limit=None,
        )
```

- [ ] **Step 5: Implement stable selection in `golden.py`**

```python
def select_cases(
    dataset: GoldenDataset,
    *,
    question_types: set[GoldenType] | None,
    case_ids: set[str] | None,
    limit: int | None,
) -> list[GoldenCase]:
    selected_types = question_types or set(GoldenType)
    scoped = [case for case in dataset.cases if case.type in selected_types]
    if case_ids is not None:
        available = {case.id for case in scoped}
        missing = sorted(case_ids - available)
        if missing:
            raise ValueError(f"case ids outside selected scope: {missing}")
        scoped = [case for case in scoped if case.id in case_ids]
    if not scoped:
        raise ValueError("evaluation selection is empty")
    if limit is None:
        return sorted(scoped, key=lambda case: (list(GoldenType).index(case.type), case.id))
    if limit < 1:
        raise ValueError("limit must be at least 1")
    queues = {
        kind: deque(sorted((case for case in scoped if case.type is kind), key=lambda case: case.id))
        for kind in GoldenType
    }
    output: list[GoldenCase] = []
    while len(output) < min(limit, len(scoped)):
        for kind in GoldenType:
            if queues[kind] and len(output) < limit:
                output.append(queues[kind].popleft())
    return output
```

- [ ] **Step 6: Run focused tests and commit**

Run:

```powershell
rtk proxy uv run pytest -p no:cacheprovider tests/unit/evaluation/test_golden.py -q
rtk ruff check src/evaluation/golden.py tests/unit/evaluation/test_golden.py
```

Expected: all focused tests PASS and Ruff reports no errors.

Commit:

```powershell
rtk git add src/evaluation/golden.py src/evaluation/__init__.py tests/unit/evaluation/test_golden.py
rtk git commit -m "feat: validate finalized golden dataset"
```

---

### Task 2: Deterministic Legal Structure and Metadata-Preserving Chunking

**Files:**
- Create: `src/ingestion/structure.py`
- Create: `tests/unit/ingestion/test_structure.py`
- Modify: `src/domain/schemas.py`
- Modify: `src/ingestion/chunker.py`
- Modify: `tests/support/builders.py`
- Modify: `tests/unit/generation/test_citation_gate.py`
- Modify: `tests/unit/generation/test_tracing.py`
- Modify: `tests/component/rag/test_retrieve_and_answer.py`
- Modify: `tests/unit/ingestion/test_enrichment.py`
- Modify: `tests/unit/retrieval/test_hybrid.py`
- Modify: `tests/unit/providers/test_jina.py`
- Modify: `tests/unit/prompts/test_prompt.py`
- Modify: `tests/unit/retrieval/test_qdrant_store.py`
- Modify: `tests/unit/retrieval/test_retrieval.py`

**Interfaces:**
- Consumes: parsed Markdown-like text and an explicit canonical `doc_id`.
- Produces: `SourceCoordinates`, `LegalSection`, `extract_legal_sections(text: str, doc_id: str) -> list[LegalSection]`, and chunks with required coordinates.

- [ ] **Step 1: Write failing hierarchy and chunk-inheritance tests**

```python
# tests/unit/ingestion/test_structure.py
import re

from domain.schemas import Document, DocumentStatus, SourceCoordinates
from ingestion.chunker import chunk_document
from ingestion.structure import extract_legal_sections


LEGAL_TEXT = """# Chương I

QUY ĐỊNH CHUNG

### Điều 1. Phạm vi điều chỉnh

Nội dung điều một.

### Điều 2. Đối tượng áp dụng

Nội dung điều hai.

# Chương II

### Điều 3. Quy định tiếp theo

Nội dung điều ba.
"""


def test_article_inherits_current_chapter() -> None:
    sections = extract_legal_sections(LEGAL_TEXT, "law.md")

    article_three = next(item for item in sections if item.coordinates.article == "Điều 3")
    assert article_three.coordinates == SourceCoordinates(
        doc_id="law.md", chapter="Chương II", article="Điều 3"
    )
    assert article_three.text.startswith("### Điều 3. Quy định tiếp theo")


def test_split_chunks_keep_article_coordinates() -> None:
    document = Document(
        id="doc",
        version=1,
        content_hash="hash",
        source_name="law.docx",
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        status=DocumentStatus.READY,
        metadata={"canonical_doc_id": "law.md"},
    )

    chunks = chunk_document(document, LEGAL_TEXT, max_chars=40)

    article_one = [chunk for chunk in chunks if chunk.coordinates.article == "Điều 1"]
    assert article_one
    article_one_text = next(
        section.text
        for section in extract_legal_sections(LEGAL_TEXT, "law.md")
        if section.coordinates == article_one[0].coordinates
    )
    assert all(chunk.coordinates.chapter == "Chương I" for chunk in article_one)
    assert all(chunk.coordinates.doc_id == "law.md" for chunk in article_one)
    assert "".join(chunk.text for chunk in article_one) == article_one_text


def test_plain_docx_legal_headings_match_markdown_hierarchy() -> None:
    plain = re.sub(r"(?m)^#{1,6}[ \t]+", "", LEGAL_TEXT)

    markdown_coordinates = [item.coordinates for item in extract_legal_sections(LEGAL_TEXT, "law.md")]
    plain_coordinates = [item.coordinates for item in extract_legal_sections(plain, "law.md")]

    assert plain_coordinates == markdown_coordinates
    assert sum(item.article is not None for item in plain_coordinates) == 3
```

- [ ] **Step 2: Run the tests and confirm deterministic hierarchy is absent**

Run:

```powershell
rtk proxy uv run pytest -p no:cacheprovider tests/unit/ingestion/test_structure.py -q
```

Expected: FAIL because `SourceCoordinates` and `ingestion.structure` do not exist.

- [ ] **Step 3: Add typed coordinates and legal sections**

```python
# add to src/domain/schemas.py before Chunk
class SourceCoordinates(BaseModel):
    doc_id: str = Field(min_length=1)
    chapter: str | None = None
    article: str | None = None


# add this required field to Chunk
coordinates: SourceCoordinates
```

```python
# src/ingestion/structure.py
from __future__ import annotations

import re

from pydantic import BaseModel

from domain.schemas import SourceCoordinates

LEGAL_HEADING_RE = re.compile(
    r"(?m)^(?:#{1,6}[ \t]+)?((?:Chương[ \t]+[IVXLCDM]+|Điều[ \t]+\d+[A-Za-z]?)\b.*)$"
)
CHAPTER_RE = re.compile(r"^Chương\s+[IVXLCDM]+\b", re.IGNORECASE)
ARTICLE_RE = re.compile(r"^(Điều\s+\d+[A-Za-z]?)\b", re.IGNORECASE)


class LegalSection(BaseModel):
    heading: str | None
    text: str
    coordinates: SourceCoordinates


def extract_legal_sections(text: str, doc_id: str) -> list[LegalSection]:
    matches = list(LEGAL_HEADING_RE.finditer(text))
    if not matches:
        stripped = text.strip()
        return [LegalSection(heading=None, text=stripped, coordinates=SourceCoordinates(doc_id=doc_id))] if stripped else []
    output: list[LegalSection] = []
    prefix = text[: matches[0].start()].strip()
    if prefix:
        output.append(LegalSection(heading=None, text=prefix, coordinates=SourceCoordinates(doc_id=doc_id)))
    chapter: str | None = None
    for index, match in enumerate(matches):
        heading = match.group(1).strip()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[match.end() : end].strip()
        chapter_match = CHAPTER_RE.match(heading)
        article_match = ARTICLE_RE.match(heading)
        if chapter_match:
            chapter = chapter_match.group(0)
        article = article_match.group(1) if article_match else None
        section_text = text[match.start() : end].strip() if article else body
        if section_text:
            output.append(
                LegalSection(
                    heading=heading,
                    text=section_text,
                    coordinates=SourceCoordinates(doc_id=doc_id, chapter=chapter, article=article),
                )
            )
    return output
```

- [ ] **Step 4: Replace flat section discovery in `chunk_document`**

```python
# src/ingestion/chunker.py
from ingestion.structure import extract_legal_sections


def chunk_document(document: Document, text: str, max_chars: int = 1200) -> list[Chunk]:
    canonical_doc_id = document.metadata.get("canonical_doc_id", document.source_name)
    output: list[Chunk] = []
    for legal_section in extract_legal_sections(text, canonical_doc_id):
        for piece in _split(legal_section.text, max_chars):
            position = len(output)
            chunk_hash = sha256(piece.encode("utf-8")).hexdigest()
            output.append(
                Chunk(
                    id=f"{document.id}:v{document.version}:{position}",
                    document_id=document.id,
                    version=document.version,
                    text=piece,
                    content_hash=chunk_hash,
                    source_name=document.source_name,
                    mime_type=document.mime_type,
                    status=document.status,
                    section=legal_section.heading,
                    position=position,
                    coordinates=legal_section.coordinates,
                )
            )
    return output


def _split(text: str, max_chars: int) -> list[str]:
    """Return contiguous slices whose concatenation exactly equals text.strip()."""
    source = text.strip()
    if not source:
        return []
    pieces: list[str] = []
    cursor = 0
    while len(source) - cursor > max_chars:
        window = source[cursor : cursor + max_chars]
        minimum = max_chars // 2
        split_at = max_chars
        for separator in ("\n\n", "\n", " "):
            candidate = window.rfind(separator)
            if candidate >= minimum:
                split_at = candidate + len(separator)
                break
        pieces.append(source[cursor : cursor + split_at])
        cursor += split_at
    pieces.append(source[cursor:])
    return pieces
```

Remove `_sections`. The lossless `_split` may choose a natural boundary, but it never drops or invents characters; `"".join(_split(text, n)) == text.strip()` is a required invariant.

- [ ] **Step 5: Update manually constructed chunks in existing tests**

Add this import and argument wherever tests construct `Chunk` directly:

```python
from domain.schemas import SourceCoordinates

# add this keyword argument to each existing Chunk constructor
coordinates=SourceCoordinates(doc_id="policy.md"),
```

For legal-coordinate tests, use explicit chapter/article values instead of the generic value.

- [ ] **Step 6: Run focused and regression tests, then commit**

Run:

```powershell
rtk proxy uv run pytest -p no:cacheprovider tests/unit/ingestion/test_structure.py tests/unit/ingestion/test_enrichment.py tests/unit/retrieval/test_retrieval.py tests/unit/generation/test_citation_gate.py tests/unit/generation/test_tracing.py tests/component/rag/test_retrieve_and_answer.py tests/unit/retrieval/test_hybrid.py tests/unit/providers/test_jina.py tests/unit/prompts/test_prompt.py tests/unit/retrieval/test_qdrant_store.py -q
rtk ruff check src/domain/schemas.py src/ingestion tests/support/builders.py tests/unit/ingestion/test_structure.py tests/unit/generation/test_citation_gate.py tests/unit/generation/test_tracing.py tests/component/rag/test_retrieve_and_answer.py
```

Expected: all selected tests PASS.

Commit:

```powershell
rtk git add src/domain/schemas.py src/ingestion/structure.py src/ingestion/chunker.py tests/support/builders.py tests/unit/ingestion/test_structure.py tests/unit/ingestion/test_enrichment.py tests/unit/generation/test_citation_gate.py tests/unit/generation/test_tracing.py tests/component/rag/test_retrieve_and_answer.py tests/unit/retrieval/test_hybrid.py tests/unit/providers/test_jina.py tests/unit/prompts/test_prompt.py tests/unit/retrieval/test_qdrant_store.py tests/unit/retrieval/test_retrieval.py
rtk git commit -m "feat: extract legal chunk coordinates"
```

---

### Task 3: Coordinate Persistence and Index Snapshot Reads

**Files:**
- Modify: `src/ingestion/service.py`
- Modify: `src/retrieval/base.py`
- Modify: `src/retrieval/memory_store.py`
- Modify: `src/retrieval/qdrant_store.py`
- Modify: `tests/unit/ingestion/test_service.py`
- Modify: `tests/unit/retrieval/test_qdrant_store.py`
- Modify: `tests/unit/retrieval/test_retrieval.py`

**Interfaces:**
- Consumes: chunks with `SourceCoordinates` from Task 2.
- Produces: `ChunkStore.list_document_chunks(document_id, version)` and flat indexed coordinate payloads for preflight/snapshot validation.

- [ ] **Step 1: Write failing store-inspection and payload tests**

```python
# append to tests/unit/retrieval/test_retrieval.py
def _chunk(
    chunk_id: str,
    text: str,
    *,
    document_id: str | None = None,
    version: int = 1,
) -> Chunk:
    return Chunk(
        id=chunk_id,
        document_id=document_id or f"doc-{chunk_id}",
        version=version,
        text=text,
        content_hash=chunk_id,
        source_name=f"{chunk_id}.md",
        mime_type="text/markdown",
        status=DocumentStatus.READY,
        coordinates=SourceCoordinates(doc_id="law.md"),
    )


def test_list_document_chunks_filters_version() -> None:
    store = MemoryChunkStore()
    first = _chunk("v1", "first", document_id="doc", version=1)
    second = _chunk("v2", "second", document_id="doc", version=2)
    store.all_chunks = [first, second]

    assert store.list_document_chunks("doc", version=2) == [second]
```

```python
# append to tests/unit/retrieval/test_qdrant_store.py
from retrieval.qdrant_store import _chunk_payload


def test_chunk_payload_flattens_source_coordinates() -> None:
    chunk = Chunk(
        id="chunk",
        document_id="doc",
        version=1,
        text="Điều 1",
        content_hash="hash",
        source_name="law.docx",
        mime_type="application/docx",
        status=DocumentStatus.READY,
        coordinates=SourceCoordinates(doc_id="law.md", chapter="Chương I", article="Điều 1"),
    )

    payload = _chunk_payload(chunk)

    assert payload["doc_id"] == "law.md"
    assert payload["chapter"] == "Chương I"
    assert payload["article"] == "Điều 1"
```

- [ ] **Step 2: Run the focused tests and verify the new interface is absent**

Run:

```powershell
rtk proxy uv run pytest -p no:cacheprovider tests/unit/retrieval/test_retrieval.py tests/unit/retrieval/test_qdrant_store.py -q
```

Expected: FAIL for missing `list_document_chunks` and `_chunk_payload`.

- [ ] **Step 3: Extend the store interface and memory adapter**

```python
# src/retrieval/base.py
class ChunkStore(Protocol):
    def replace_document(self, document_id: str, chunks: list[Chunk]) -> None:
        raise NotImplementedError

    def search(self, query: str, limit: int = 5) -> list[SearchHit]:
        raise NotImplementedError

    def list_document_chunks(
        self,
        document_id: str,
        version: int | None = None,
    ) -> list[Chunk]:
        raise NotImplementedError

    def ready(self) -> bool:
        raise NotImplementedError
```

```python
# src/retrieval/memory_store.py
def list_document_chunks(self, document_id: str, version: int | None = None) -> list[Chunk]:
    return sorted(
        (
            chunk
            for chunk in self.all_chunks
            if chunk.document_id == document_id and (version is None or chunk.version == version)
        ),
        key=lambda chunk: chunk.position,
    )
```

- [ ] **Step 4: Flatten coordinate payloads and index their filter fields in Qdrant**

```python
# src/retrieval/qdrant_store.py
def _chunk_payload(chunk: Chunk) -> dict[str, object]:
    payload = chunk.model_dump(mode="json")
    payload.update(chunk.coordinates.model_dump())
    return payload
```

Change `ensure_collection()` to create keyword payload indexes for
`document_id`, `status`, `doc_id`, `chapter`, and `article`, plus the existing integer
index for `version`. Change each `PointStruct` construction to pass `payload=_chunk_payload(chunk)`.

Implement paginated inspection:

```python
def list_document_chunks(self, document_id: str, version: int | None = None) -> list[Chunk]:
    self.ensure_collection()
    must = [
        models.FieldCondition(key="document_id", match=models.MatchValue(value=document_id))
    ]
    if version is not None:
        must.append(models.FieldCondition(key="version", match=models.MatchValue(value=version)))
    output: list[Chunk] = []
    offset: object | None = None
    while True:
        records, next_offset = self.client.scroll(
            collection_name=self.collection,
            scroll_filter=models.Filter(must=must),
            limit=256,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        output.extend(Chunk.model_validate(record.payload) for record in records)
        if next_offset is None:
            break
        offset = next_offset
    return sorted(output, key=lambda chunk: chunk.position)
```

- [ ] **Step 5: Prove canonical metadata reaches ingestion and traces**

Add a test in `tests/unit/ingestion/test_service.py` that calls:

```python
document = service.ingest_bytes(
    "01_2021_ND-CP_283247.docx",
    raw_docx_bytes,
    {"canonical_doc_id": "01_2021_ND-CP_283247.md"},
)
chunks = store.list_document_chunks(document.id, document.version)
assert chunks
assert {chunk.coordinates.doc_id for chunk in chunks} == {"01_2021_ND-CP_283247.md"}
article_chunks = [chunk for chunk in chunks if chunk.coordinates.article is not None]
assert article_chunks
assert all(chunk.coordinates.chapter is not None for chunk in article_chunks)
```

Update `_chunk_trace_payload` to include `doc_id`, `chapter`, and `article`; keep text subject to the existing trace privacy rules.

- [ ] **Step 6: Run focused tests and commit**

Run:

```powershell
rtk proxy uv run pytest -p no:cacheprovider tests/unit/ingestion/test_service.py tests/unit/retrieval/test_retrieval.py tests/unit/retrieval/test_qdrant_store.py -q
rtk ruff check src/ingestion/service.py src/retrieval tests/unit/ingestion/test_service.py tests/unit/retrieval/test_retrieval.py tests/unit/retrieval/test_qdrant_store.py
```

Expected: all selected tests PASS.

Commit:

```powershell
rtk git add src/ingestion/service.py src/retrieval/base.py src/retrieval/memory_store.py src/retrieval/qdrant_store.py tests/unit/ingestion/test_service.py tests/unit/retrieval/test_retrieval.py tests/unit/retrieval/test_qdrant_store.py
rtk git commit -m "feat: persist and inspect chunk coordinates"
```

---

### Task 4: Canonical Grounding and Chunk-Recoverability Validation

**Files:**
- Modify: `src/evaluation/golden.py`
- Create: `tests/unit/evaluation/test_validation.py`
- Create: `tests/component/evaluation/test_validation.py`

**Interfaces:**
- Consumes: `GoldenDataset`, canonical Markdown, and metadata-bearing chunks.
- Produces: `GoldenValidationReport` with blocking errors, non-blocking audit warnings, and full-conformance status.

- [ ] **Step 1: Write failing exact-source, coordinate, and audit-warning tests**

```python
# tests/unit/evaluation/test_validation.py
import json
from pathlib import Path

from evaluation.golden import (
    Difficulty,
    GoldenCase,
    GoldenContext,
    GoldenDataset,
    GoldenMetadata,
    GoldenType,
    load_golden_dataset,
    validate_golden_dataset,
)


def _single_case_dataset(*, context: str, chapter: str, article: str) -> GoldenDataset:
    return GoldenDataset(
        cases=[
            GoldenCase(
                id="DL-001",
                type=GoldenType.DIRECT_LOOKUP,
                question="Question",
                expected_answer="Answer",
                golden_truth_contexts=[
                    GoldenContext(
                        golden_truth_context=context,
                        golden_metadata=GoldenMetadata(
                            doc_id="law.md",
                            chapter=chapter,
                            article=article,
                        ),
                    )
                ],
                difficulty=Difficulty.EASY,
            )
        ],
        source_files=["test.json"],
        scope="partial",
    )


def test_finalized_dataset_is_exactly_grounded() -> None:
    dataset = load_golden_dataset(Path("evaluation/golden_set"))
    report = validate_golden_dataset(
        dataset,
        canonical_path=Path("data/extracted/01_2021_ND-CP_283247.md"),
        chunks=None,
        audit_root=Path("evaluation"),
    )

    assert report.errors == []
    assert report.warnings == []
    assert report.full_conformance is True


def test_context_in_wrong_article_is_rejected(tmp_path: Path) -> None:
    canonical = tmp_path / "law.md"
    canonical.write_text("# Chương I\n\n### Điều 1. A\n\nBằng chứng", encoding="utf-8")
    dataset = _single_case_dataset(
        context="Bằng chứng",
        chapter="Chương I",
        article="Điều 2",
    )

    report = validate_golden_dataset(dataset, canonical, chunks=None, audit_root=tmp_path)

    assert [issue.code for issue in report.errors] == ["context_coordinate_mismatch"]


def _copy_audits(tmp_path: Path) -> None:
    for filename in ("id_migration_map.json", "golden_set_grounding_review.json"):
        (tmp_path / filename).write_bytes((Path("evaluation") / filename).read_bytes())


@pytest.mark.parametrize(
    ("filename", "warning_code", "path", "value", "remove"),
    [
        (
            "id_migration_map.json",
            "invalid_id_migration_map",
            ("migration_commit",),
            "wrong",
            False,
        ),
        (
            "id_migration_map.json",
            "invalid_id_migration_map",
            ("old_to_new", "61"),
            "DL-999",
            False,
        ),
        (
            "id_migration_map.json",
            "invalid_id_migration_map",
            ("old_to_new", "61"),
            None,
            True,
        ),
        (
            "id_migration_map.json",
            "invalid_id_migration_map",
            ("retired", 0, "status"),
            "active",
            False,
        ),
        (
            "golden_set_grounding_review.json",
            "invalid_grounding_review",
            ("cases", 0, "case_id"),
            "DL-999",
            False,
        ),
        (
            "golden_set_grounding_review.json",
            "invalid_grounding_review",
            ("cases", 0, "status"),
            "failed",
            False,
        ),
        (
            "golden_set_grounding_review.json",
            "invalid_grounding_review",
            ("cases", 0, "contexts", 0, "context_index"),
            99,
            False,
        ),
        (
            "golden_set_grounding_review.json",
            "invalid_grounding_review",
            ("canonical_sha256",),
            "0" * 64,
            False,
        ),
        (
            "golden_set_grounding_review.json",
            "invalid_grounding_review",
            ("dataset_sha256",),
            "0" * 64,
            False,
        ),
        (
            "golden_set_grounding_review.json",
            "invalid_grounding_review",
            ("cases", 0, "contexts", 0, "context_sha256"),
            "0" * 64,
            False,
        ),
    ],
    ids=[
        "migration-commit",
        "migration-mapping",
        "migration-completeness",
        "retired-record",
        "grounding-case-id",
        "grounding-case-status",
        "grounding-context-index",
        "grounding-canonical-hash",
        "grounding-dataset-hash",
        "grounding-context-hash",
    ],
)
def test_each_audit_evidence_field_is_validated_independently(
    tmp_path: Path,
    filename: str,
    warning_code: str,
    path: tuple[str | int, ...],
    value: object,
    remove: bool,
) -> None:
    _copy_audits(tmp_path)
    artifact_path = tmp_path / filename
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    target = artifact
    for segment in path[:-1]:
        target = target[segment]
    if remove:
        del target[path[-1]]
    else:
        target[path[-1]] = value
    artifact_path.write_text(json.dumps(artifact, ensure_ascii=False), encoding="utf-8")

    report = validate_golden_dataset(
        load_golden_dataset(Path("evaluation/golden_set")),
        Path("data/extracted/01_2021_ND-CP_283247.md"),
        chunks=None,
        audit_root=tmp_path,
    )

    assert warning_code in {warning.code for warning in report.warnings}
    assert report.full_conformance is False
```

- [ ] **Step 2: Run the tests and verify validation types are missing**

Run:

```powershell
rtk proxy uv run pytest -p no:cacheprovider tests/unit/evaluation/test_validation.py -q
```

Expected: FAIL because `validate_golden_dataset` and report models do not exist.

- [ ] **Step 3: Implement validation issue/report models and exact canonical checks**

```python
# add to the existing top-level import section in src/evaluation/golden.py
from hashlib import sha256

from domain.schemas import Chunk
from ingestion.structure import extract_legal_sections


class ValidationIssue(BaseModel):
    code: str
    message: str
    case_id: str | None = None


class GoldenValidationReport(BaseModel):
    errors: list[ValidationIssue]
    warnings: list[ValidationIssue]
    validated_cases: int
    full_conformance: bool


def _normalized(text: str) -> str:
    without_markers = re.sub(r"(?m)^#{1,6}[ \t]+", "", text)
    return re.sub(r"\s+", " ", without_markers).strip()


def validate_golden_dataset(
    dataset: GoldenDataset,
    canonical_path: Path,
    chunks: list[Chunk] | None,
    audit_root: Path,
) -> GoldenValidationReport:
    canonical = canonical_path.read_text(encoding="utf-8")
    doc_id = canonical_path.name
    sections = extract_legal_sections(canonical, doc_id)
    article_text = {
        (section.coordinates.doc_id, section.coordinates.chapter, section.coordinates.article): section.text
        for section in sections
        if section.coordinates.article is not None
    }
    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []
    for case in dataset.cases:
        for context in case.golden_truth_contexts:
            evidence = context.golden_truth_context
            metadata = context.golden_metadata
            key = (metadata.doc_id, metadata.chapter, metadata.article)
            if evidence not in canonical:
                errors.append(ValidationIssue(code="context_not_exact_source", message="context is not an exact canonical substring", case_id=case.id))
            elif evidence not in article_text.get(key, ""):
                errors.append(ValidationIssue(code="context_coordinate_mismatch", message=f"context is not inside {metadata.chapter}/{metadata.article}", case_id=case.id))
            if "..." in evidence or "…" in evidence:
                errors.append(ValidationIssue(code="context_contains_ellipsis", message="context contains a forbidden omission marker", case_id=case.id))
    if chunks is not None:
        chunk_text: dict[tuple[str, str | None, str | None], str] = {}
        for chunk in sorted(chunks, key=lambda item: item.position):
            key = (chunk.coordinates.doc_id, chunk.coordinates.chapter, chunk.coordinates.article)
            chunk_text[key] = f"{chunk_text.get(key, '')}{chunk.text}"
        for case in dataset.cases:
            for context in case.golden_truth_contexts:
                metadata = context.golden_metadata
                key = (metadata.doc_id, metadata.chapter, metadata.article)
                if _normalized(context.golden_truth_context) not in _normalized(chunk_text.get(key, "")):
                    errors.append(ValidationIssue(code="context_not_recoverable_from_chunks", message="context is not recoverable from ordered article chunks", case_id=case.id))
    migration_path = audit_root / "id_migration_map.json"
    review_path = audit_root / "golden_set_grounding_review.json"
    expected_migration = {
        "schema_version": 1,
        "migration_commit": "f97292a",
        "old_to_new": {
            "1": "DL-001", "5": "DL-002", "7": "DL-003", "9": "DL-004",
            "13": "DL-005", "17": "DL-006", "21": "DL-007", "25": "DL-008",
            "29": "DL-009", "33": "DL-010", "37": "DL-011", "41": "DL-012",
            "45": "DL-013", "49": "DL-014", "53": "DL-015", "57": "DL-016",
            "61": "DL-017", "65": None, "69": "DL-018", "73": "DL-019", "77": "DL-020",
        },
        "retired": [{
            "old_id": "65",
            "status": "retired",
            "reason": "The question asks for a number of days while Article 35 defines the filing-time event, so it is not a sound direct lookup.",
        }],
    }
    if not migration_path.exists():
        warnings.append(ValidationIssue(code="missing_id_migration_map", message=f"missing audit artifact: {migration_path.name}"))
    else:
        migration = json.loads(migration_path.read_text(encoding="utf-8"))
        if migration != expected_migration:
            warnings.append(ValidationIssue(code="invalid_id_migration_map", message="ID migration evidence does not match the issued direct-lookup namespace"))
    if not review_path.exists():
        warnings.append(ValidationIssue(code="missing_grounding_review", message=f"missing audit artifact: {review_path.name}"))
    else:
        review = json.loads(review_path.read_text(encoding="utf-8"))
        dataset_bytes = json.dumps([case.model_dump(mode="json") for case in dataset.cases], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        expected_cases = []
        for case in dataset.cases:
            expected_contexts = []
            for context_index, context in enumerate(case.golden_truth_contexts):
                evidence = context.golden_truth_context
                metadata = context.golden_metadata
                key = (metadata.doc_id, metadata.chapter, metadata.article)
                expected_contexts.append({
                    "context_index": context_index,
                    "context_sha256": sha256(evidence.encode("utf-8")).hexdigest(),
                    "exact_source": evidence in canonical,
                    "coordinate_match": evidence in article_text.get(key, ""),
                })
            expected_cases.append({
                "case_id": case.id,
                "status": "passed" if all(item["exact_source"] and item["coordinate_match"] for item in expected_contexts) else "failed",
                "contexts": expected_contexts,
            })
        expected_review = {
            "schema_version": 1,
            "canonical_doc_id": canonical_path.name,
            "canonical_sha256": sha256(canonical.encode("utf-8")).hexdigest(),
            "dataset_sha256": sha256(dataset_bytes).hexdigest(),
            "validated_cases": len(dataset.cases),
            "validated_contexts": sum(len(case.golden_truth_contexts) for case in dataset.cases),
            "cases": expected_cases,
        }
        if review != expected_review:
            warnings.append(ValidationIssue(code="invalid_grounding_review", message="grounding review evidence does not match the current canonical source and dataset"))
    return GoldenValidationReport(
        errors=errors,
        warnings=warnings,
        validated_cases=len(dataset.cases),
        full_conformance=not errors and not warnings,
    )
```

Add `import json` and `from hashlib import sha256`. Do not treat mere file presence as conformance: Task 0 defines and creates both artifact schemas, and missing or content/hash-incompatible evidence keeps `full_conformance=false`.

- [ ] **Step 4: Add raw-DOCX parser/chunker recoverability coverage**

```python
# tests/component/evaluation/test_validation.py
from pathlib import Path

from domain.schemas import Document, DocumentStatus
from evaluation.golden import load_golden_dataset, validate_golden_dataset
from ingestion.chunker import chunk_document
from ingestion.parser import parse_document


def test_real_docx_chunks_recover_all_answerable_golden_evidence() -> None:
    raw_path = Path("data/raw/01_2021_ND-CP_283247.docx")
    parsed_text, mime_type = parse_document(raw_path.name, raw_path.read_bytes())
    document = Document(
        id="offline-eval-document",
        version=1,
        content_hash="fixture-hash",
        source_name=raw_path.name,
        mime_type=mime_type,
        status=DocumentStatus.READY,
        metadata={"canonical_doc_id": "01_2021_ND-CP_283247.md"},
    )
    chunks = chunk_document(document, parsed_text)
    report = validate_golden_dataset(
        load_golden_dataset(Path("evaluation/golden_set")),
        canonical_path=Path("data/extracted/01_2021_ND-CP_283247.md"),
        chunks=chunks,
        audit_root=Path("evaluation"),
    )

    assert not {
        issue.case_id
        for issue in report.errors
        if issue.code == "context_not_recoverable_from_chunks"
    }
```

If this test exposes a genuine mismatch, fix `structure.py` or `chunker.py`; never weaken exact canonical validation.

- [ ] **Step 5: Run focused tests and commit**

Run:

```powershell
rtk proxy uv run pytest -p no:cacheprovider tests/unit/evaluation/test_golden.py tests/unit/evaluation/test_validation.py tests/component/evaluation/test_validation.py tests/unit/ingestion/test_structure.py -q
rtk ruff check src/evaluation/golden.py tests/unit/evaluation/test_validation.py tests/component/evaluation/test_validation.py
```

Expected: tests PASS; the finalized reissued dataset and both validated audit artifacts report full conformance with no warnings.

Commit:

```powershell
rtk git add src/evaluation/golden.py tests/unit/evaluation/test_validation.py tests/component/evaluation/test_validation.py
rtk git commit -m "feat: validate golden grounding and chunk recovery"
```

---

### Task 5: Internal Retrieval and Generation Evidence

**Files:**
- Create: `src/generation/execution.py`
- Create: `tests/unit/generation/test_execution.py`
- Modify: `src/generation/service.py`
- Modify: `tests/unit/generation/test_abstention.py`

**Interfaces:**
- Consumes: `ChunkStore`, `SearchHit`, provider structured output, and existing tracing.
- Produces: `RetrievalExecution`, `GenerationExecution`, `RagExecution`, `ChatService.retrieve(question: str, request_id: str | None = None) -> RetrievalExecution`, `ChatService.generate_from_hits(question: str, hits: list[SearchHit], request_id: str | None = None) -> GenerationExecution`, and unchanged `ChatService.answer(question: str) -> ChatResponse`.

- [ ] **Step 1: Write failing execution-evidence and projection tests**

```python
# tests/unit/generation/test_execution.py
from contextlib import nullcontext
from typing import Any

from domain.schemas import Chunk, DocumentStatus, SearchHit, SourceCoordinates
from generation.service import ChatService, GroundedAnswer
from providers.base import StructuredResult


def _search_hit(text: str) -> SearchHit:
    return SearchHit(
        chunk=Chunk(
            id="chunk-1",
            document_id="document-1",
            version=1,
            text=text,
            content_hash="chunk-hash",
            source_name="law.docx",
            mime_type="application/docx",
            status=DocumentStatus.READY,
            coordinates=SourceCoordinates(doc_id="law.md", chapter="Chương I", article="Điều 1"),
        ),
        score=0.9,
    )


class RecordingStore:
    def __init__(self, hits: list[SearchHit]) -> None:
        self.hits = hits
        self.search_calls = 0

    def search(self, query: str, limit: int = 5) -> list[SearchHit]:
        self.search_calls += 1
        return self.hits[:limit]


class CitedProvider:
    def generate_structured(self, request: Any, response_model: type[GroundedAnswer]) -> StructuredResult[GroundedAnswer]:
        return StructuredResult(
            value=response_model(answer="Nội dung [C1].", citations=[1]),
            provider="fake",
            model="fake-model",
            usage={"input_tokens": 10, "output_tokens": 5},
        )


class SilentTracer:
    def span(self, name: str, payload: dict[str, object]):
        return nullcontext(object())

    def safe_payload(self, payload: dict[str, object]) -> dict[str, object]:
        return payload

    def update(self, observation: object, payload: dict[str, object]) -> None:
        return None


def _recording_chat() -> tuple[ChatService, RecordingStore]:
    store = RecordingStore([_search_hit("fixed-context")])
    return ChatService(store, CitedProvider(), SilentTracer()), store


def _chat_with_cited_provider() -> ChatService:
    return _recording_chat()[0]


def test_execute_returns_ranked_hits_and_projects_existing_chat_response() -> None:
    chat = _chat_with_cited_provider()

    execution = chat.execute("Nghỉ phép thế nào?")
    response = execution.to_chat_response()

    assert [item.hit.chunk.id for item in execution.retrieval.hits] == ["chunk-1"]
    assert execution.generation is not None
    assert response.answer == execution.generation.answer
    assert response.citations == execution.generation.citations
    assert set(response.model_dump()) == {
        "answer", "citations", "retrieval", "request_id", "provider", "model"
    }


def test_generation_replay_does_not_search_store() -> None:
    chat, store = _recording_chat()
    hits = [_search_hit("fixed-context")]

    generated = chat.generate_from_hits("Question", hits)

    assert store.search_calls == 0
    assert generated.answer
```

- [ ] **Step 2: Run the tests and verify the evidence interface is absent**

Run:

```powershell
rtk proxy uv run pytest -p no:cacheprovider tests/unit/generation/test_execution.py -q
```

Expected: FAIL because execution models and methods are missing.

- [ ] **Step 3: Add internal evidence models**

```python
# src/generation/execution.py
from __future__ import annotations

from pydantic import BaseModel, Field

from domain.schemas import ChatResponse, Citation, RetrievalInfo, SearchHit


class RankedHit(BaseModel):
    rank: int = Field(ge=1)
    hit: SearchHit


class RetrievalExecution(BaseModel):
    question: str
    request_id: str
    hits: list[RankedHit]
    latency_ms: float


class GenerationExecution(BaseModel):
    answer: str
    citations: list[Citation]
    structured_response: dict[str, object]
    provider: str | None
    model: str | None
    prompt_version: str
    usage: dict[str, int]
    latency_ms: float


class RagExecution(BaseModel):
    request_id: str
    retrieval: RetrievalExecution
    generation: GenerationExecution | None

    def to_chat_response(self) -> ChatResponse:
        generated = self.generation
        return ChatResponse(
            answer=generated.answer if generated is not None else "Không tìm thấy thông tin phù hợp trong tài liệu được phép truy cập.",
            citations=generated.citations if generated is not None else [],
            retrieval=RetrievalInfo(result_count=len(self.retrieval.hits), latency_ms=self.retrieval.latency_ms),
            request_id=self.request_id,
            provider=generated.provider if generated is not None else None,
            model=generated.model if generated is not None else None,
        )
```

- [ ] **Step 4: Refactor `ChatService` around evidence-producing methods**

Replace `_answer` with these exact evidence-producing methods; retain the current imports, prompt rendering, tracer privacy handling, and `ABSTENTION` constant:

```python
def retrieve(self, question: str, request_id: str | None = None) -> RetrievalExecution:
    current_request_id = request_id or str(uuid4())
    started = time.perf_counter()
    with self.tracer.span(
        "retrieval",
        self.tracer.safe_payload({"request_id": current_request_id, "question": question}),
    ) as observation:
        hits = self.store.search(question, limit=self.retrieval_limit)
        latency_ms = (time.perf_counter() - started) * 1000
        ranked = [RankedHit(rank=rank, hit=hit) for rank, hit in enumerate(hits, start=1)]
        self.tracer.update(
            observation,
            {
                "result_count": len(hits),
                "latency_ms": latency_ms,
                "top_k": [
                    {
                        "rank": item.rank,
                        "score": item.hit.score,
                        **item.hit.chunk.model_dump(mode="json"),
                    }
                    for item in ranked
                ],
            },
        )
    return RetrievalExecution(
        question=question,
        request_id=current_request_id,
        hits=ranked,
        latency_ms=latency_ms,
    )

def generate_from_hits(
    self,
    question: str,
    hits: list[SearchHit],
    request_id: str | None = None,
) -> GenerationExecution:
    current_request_id = request_id or str(uuid4())
    started = time.perf_counter()
    chunks = [hit.chunk for hit in hits]
    if not chunks:
        return GenerationExecution(
            answer=ABSTENTION,
            citations=[],
            structured_response={"answer": ABSTENTION, "citations": []},
            provider=None,
            model=None,
            prompt_version=PROMPT_VERSION,
            usage={},
            latency_ms=0.0,
        )
    prompt = render_answer_prompt(question, chunks)
    with self.tracer.span(
        "generation",
        self.tracer.safe_payload(
            {
                "request_id": current_request_id,
                "question": question,
                "context": [chunk.text for chunk in chunks],
                "prompt_version": PROMPT_VERSION,
                "system_instruction": prompt.system_instruction,
                "user_prompt": prompt.user_prompt,
            }
        ),
    ) as observation:
        result = self.provider.generate_structured(
            GenerationRequest(prompt.system_instruction, prompt.user_prompt),
            GroundedAnswer,
        )
        cited_indexes = sorted(
            {index for index in result.value.citations if 1 <= index <= len(chunks)}
        )
        citations = [
            Citation(
                id=f"C{index}",
                document_id=chunks[index - 1].document_id,
                chunk_id=chunks[index - 1].id,
                source_name=chunks[index - 1].source_name,
                version=chunks[index - 1].version,
                excerpt=chunks[index - 1].text[:300],
            )
            for index in cited_indexes
        ]
        answer = result.value.answer if citations else ABSTENTION
        self.tracer.update(
            observation,
            {
                "provider": result.provider,
                "model": result.model,
                **result.usage,
                "response": result.value.model_dump(),
                "citation_ids": [citation.id for citation in citations],
                "answer": answer,
            },
        )
    return GenerationExecution(
        answer=answer,
        citations=citations,
        structured_response=result.value.model_dump(mode="json"),
        provider=result.provider,
        model=result.model,
        prompt_version=PROMPT_VERSION,
        usage=result.usage,
        latency_ms=(time.perf_counter() - started) * 1000,
    )

def execute(self, question: str, retrieval: RetrievalExecution | None = None) -> RagExecution:
    request_id = retrieval.request_id if retrieval is not None else str(uuid4())
    with self.tracer.span(
        "rag-request",
        self.tracer.safe_payload({"request_id": request_id, "question": question}),
    ):
        retrieved = retrieval or self.retrieve(question, request_id)
        generated = (
            self.generate_from_hits(
                question,
                [item.hit for item in retrieved.hits],
                request_id,
            )
            if retrieved.hits
            else None
        )
        return RagExecution(
            request_id=request_id,
            retrieval=retrieved,
            generation=generated,
        )

def answer(self, question: str) -> ChatResponse:
    return self.execute(question).to_chat_response()
```

Import `RankedHit`, `RetrievalExecution`, `GenerationExecution`, and `RagExecution` from `generation.execution`. This implementation preserves the exact public projection, prevents replay from calling `store.search`, and keeps retrieval and generation latency separate.

- [ ] **Step 5: Run new and existing generation tests**

Run:

```powershell
rtk proxy uv run pytest -p no:cacheprovider tests/unit/generation/test_execution.py tests/unit/generation/test_abstention.py tests/component/api/test_api.py tests/unit/prompts/test_prompt.py -q
rtk ruff check src/generation tests/unit/generation/test_execution.py tests/unit/generation/test_abstention.py
```

Expected: all tests PASS and existing API response assertions remain unchanged.

- [ ] **Step 6: Commit the evidence seam**

```powershell
rtk git add src/generation/execution.py src/generation/service.py tests/unit/generation/test_execution.py tests/unit/generation/test_abstention.py
rtk git commit -m "refactor: expose internal rag execution evidence"
```

---

### Task 6: Immutable Artifacts, Fingerprints, and Run Repository

**Files:**
- Create: `src/evaluation/artifacts.py`
- Create: `src/evaluation/repository.py`
- Create: `tests/support/evaluation_fakes.py`
- Create: `tests/unit/evaluation/test_artifacts.py`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: golden cases and execution evidence from Tasks 1 and 5.
- Produces: `EvaluationRequest`, `RunManifest`, `IndexSnapshot`, `RetrievalRun` (including `golden_dir`, complete `dataset_source_files`, `dataset_scope`, and `canonical_source` replay selection), `GenerationRun`, `EvaluationReport`, `fingerprint(value) -> str`, `artifact_fingerprint(value: BaseModel) -> str`, `RunRepository`, `LocalRunRepository`, and `InMemoryRunRepository`.

- [ ] **Step 1: Write failing fingerprint and round-trip tests**

```python
# tests/unit/evaluation/test_artifacts.py
from evaluation.artifacts import EvaluationMode, EvaluationRequest, artifact_fingerprint, fingerprint
from evaluation.repository import InMemoryRunRepository, LocalRunRepository
from tests.support.evaluation_fakes import make_retrieval_run


def test_fingerprint_is_stable_across_dictionary_order() -> None:
    assert fingerprint({"a": 1, "b": 2}) == fingerprint({"b": 2, "a": 1})


def test_local_repository_round_trips_retrieval_run(tmp_path) -> None:
    repository = LocalRunRepository(tmp_path)
    run = make_retrieval_run(run_id="retrieval-1")

    repository.save_retrieval(run)

    assert repository.load_retrieval("retrieval-1") == run


def test_limited_request_is_not_baseline_eligible() -> None:
    request = EvaluationRequest(mode=EvaluationMode.E2E, limit=10)
    assert request.baseline_candidate is False


def test_artifact_fingerprint_excludes_run_identity_and_timestamp() -> None:
    first = make_retrieval_run(run_id="run-a")
    second = make_retrieval_run(run_id="run-b")

    assert artifact_fingerprint(first) == artifact_fingerprint(second)


def test_artifact_fingerprint_excludes_nested_execution_volatiles() -> None:
    first = make_retrieval_run()
    source_case = first.cases[0]
    assert source_case.retrieval is not None
    changed = source_case.retrieval.model_copy(
        update={"request_id": "different-request", "latency_ms": 999.0}
    )
    second = first.model_copy(
        update={"cases": [source_case.model_copy(update={"retrieval": changed})]}
    )
    assert artifact_fingerprint(first) == artifact_fingerprint(second)


def test_ragas_is_off_by_default() -> None:
    assert EvaluationRequest(mode=EvaluationMode.E2E).run_ragas is False
```

- [ ] **Step 2: Run tests and confirm artifact modules are absent**

Run:

```powershell
rtk proxy uv run pytest -p no:cacheprovider tests/unit/evaluation/test_artifacts.py -q
```

Expected: FAIL during import.

- [ ] **Step 3: Implement artifact models and canonical fingerprints**

```python
# src/evaluation/artifacts.py
from __future__ import annotations

import json
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from domain.schemas import Chunk
from evaluation.golden import GoldenType
from generation.execution import GenerationExecution, RetrievalExecution


def fingerprint(value: BaseModel | dict[str, Any] | list[Any]) -> str:
    raw = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    encoded = json.dumps(raw, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(encoded).hexdigest()


VOLATILE_ARTIFACT_FIELDS: dict[str, object] = {
    "run_id": True,
    "created_at": True,
    "snapshot_fingerprint": True,
    "run_fingerprint": True,
    "cases": {
        "__all__": {
            "retrieval": {"latency_ms", "request_id"},
            "generation": {"latency_ms", "usage"},
        }
    },
}


def artifact_fingerprint(value: BaseModel) -> str:
    """Hash only phase inputs/evidence; never hash timestamps or storage identity."""
    return fingerprint(value.model_dump(mode="json", exclude=VOLATILE_ARTIFACT_FIELDS))


class EvaluationMode(StrEnum):
    VALIDATE = "validate"
    INGEST = "ingest"
    RETRIEVAL = "retrieval"
    GENERATION = "generation"
    E2E = "e2e"


class ArtifactModel(BaseModel):
    model_config = ConfigDict(frozen=True)


class EvaluationRequest(BaseModel):
    mode: EvaluationMode
    golden_dir: Path = Path("evaluation/golden_set")
    golden_files: list[Path] = Field(default_factory=list)
    question_types: set[GoldenType] = Field(default_factory=set)
    case_ids: set[str] = Field(default_factory=set)
    limit: int | None = Field(default=None, ge=1)
    canonical_source: Path = Path("data/extracted/01_2021_ND-CP_283247.md")
    ingestion_source: Path | None = None
    force_reingest: bool = False
    from_run: str | None = None
    run_ragas: bool = False
    output_root: Path = Path("reports/rag_evaluation")

    @computed_field
    @property
    def baseline_candidate(self) -> bool:
        return (
            self.mode is EvaluationMode.E2E
            and not self.golden_files
            and not self.question_types
            and not self.case_ids
            and self.limit is None
        )

    @model_validator(mode="after")
    def validate_mode_contract(self) -> "EvaluationRequest":
        if self.golden_files and self.question_types:
            raise ValueError("golden_files and question_types are mutually exclusive")
        if self.force_reingest and self.ingestion_source is None:
            raise ValueError("force_reingest requires an ingestion source")
        if self.mode is EvaluationMode.INGEST and self.ingestion_source is None:
            raise ValueError("ingest mode requires an ingestion source")
        if self.mode is EvaluationMode.GENERATION and self.from_run is None:
            raise ValueError("generation mode requires from_run")
        if self.mode in {EvaluationMode.VALIDATE, EvaluationMode.INGEST} and self.run_ragas:
            raise ValueError(f"{self.mode} does not support Ragas")
        if self.mode is EvaluationMode.VALIDATE and (
            self.question_types or self.case_ids or self.limit is not None
        ):
            raise ValueError("validate checks the complete standard dataset unless golden_files are explicit")
        if self.mode is EvaluationMode.INGEST and (
            self.golden_files or self.question_types or self.case_ids or self.limit is not None
        ):
            raise ValueError("ingest always validates the complete standard dataset")
        replay_replacements = self.model_fields_set & {
            "golden_dir", "golden_files", "question_types", "case_ids", "limit", "canonical_source"
        }
        if self.mode is EvaluationMode.GENERATION and replay_replacements:
            raise ValueError("generation replay inherits the saved retrieval selection")
        return self


class RunManifest(ArtifactModel):
    run_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    mode: EvaluationMode
    arguments: dict[str, Any]
    git_revision: str | None
    dataset_fingerprint: str
    source_fingerprints: dict[str, str]
    configuration_fingerprints: dict[str, str]
    dependency_versions: dict[str, str]
    artifact_lineage: dict[str, str]


class IndexSnapshot(ArtifactModel):
    run_id: str
    document_id: str
    document_version: int
    source_name: str
    canonical_doc_id: str
    raw_source_hash: str
    canonical_source_hash: str
    chunk_count: int
    collection_name: str
    configuration: dict[str, Any]
    metadata_validation: dict[str, Any]
    chunks: list[Chunk]
    snapshot_fingerprint: str


class RetrievalCaseArtifact(ArtifactModel):
    case_id: str
    type: GoldenType
    difficulty: str
    expected_answer: str
    golden_contexts: list[str]
    retrieval: RetrievalExecution | None
    deterministic_scores: dict[str, float | None] = Field(default_factory=dict)
    error: str | None = None


class RetrievalRun(ArtifactModel):
    run_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    dataset_fingerprint: str
    golden_dir: Path
    dataset_source_files: list[str]
    dataset_scope: str
    canonical_source: Path
    index_snapshot_fingerprint: str
    configuration: dict[str, Any]
    cases: list[RetrievalCaseArtifact]
    run_fingerprint: str


class GenerationCaseArtifact(ArtifactModel):
    case_id: str
    generation: GenerationExecution | None
    deterministic_scores: dict[str, float | None] = Field(default_factory=dict)
    error: str | None = None


class GenerationRun(ArtifactModel):
    run_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    retrieval_run_fingerprint: str
    configuration: dict[str, Any]
    cases: list[GenerationCaseArtifact]
    run_fingerprint: str


class SemanticScoreBatch(ArtifactModel):
    scores: dict[str, dict[str, float | None]]
    errors: dict[str, list[str]] = Field(default_factory=dict)


class EvaluationReport(ArtifactModel):
    run_id: str
    mode: EvaluationMode
    status: str
    dataset_size: int
    evaluated_cases: int
    validation: dict[str, Any]
    aggregates: dict[str, Any]
    target_comparison: dict[str, Any] = Field(default_factory=dict)
    case_scores: dict[str, dict[str, float | None]] = Field(default_factory=dict)
    errors: list[str]
    artifact_ids: dict[str, str]
    baseline_eligible: bool
    report_path: Path | None = None
```

- [ ] **Step 4: Implement local and in-memory repositories**

Use this repository seam; the evaluator knows no filesystem details beyond it:

```python
# src/evaluation/repository.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel

from evaluation.artifacts import (
    EvaluationReport,
    GenerationRun,
    IndexSnapshot,
    RetrievalCaseArtifact,
    RetrievalRun,
    RunManifest,
)


class RunRepository(Protocol):
    def save_manifest(self, manifest: RunManifest) -> Path:
        raise NotImplementedError

    def load_manifest(self, run_id: str) -> RunManifest:
        raise NotImplementedError

    def save_snapshot(self, snapshot: IndexSnapshot) -> Path:
        raise NotImplementedError

    def save_retrieval(self, run: RetrievalRun) -> Path:
        raise NotImplementedError

    def load_retrieval(self, run_id: str) -> RetrievalRun:
        raise NotImplementedError

    def save_generation(self, run: GenerationRun) -> Path:
        raise NotImplementedError

    def save_report(self, report: EvaluationReport) -> Path:
        raise NotImplementedError


def _atomic_write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)
    return path


def _json(model: BaseModel) -> str:
    return json.dumps(model.model_dump(mode="json"), ensure_ascii=False, indent=2)


class LocalRunRepository:
    def __init__(self, root: Path) -> None:
        self.root = root

    def _path(self, run_id: str, filename: str) -> Path:
        return self.root / run_id / filename

    def save_manifest(self, manifest: RunManifest) -> Path:
        return _atomic_write(self._path(manifest.run_id, "manifest.json"), _json(manifest))

    def load_manifest(self, run_id: str) -> RunManifest:
        return RunManifest.model_validate_json(
            self._path(run_id, "manifest.json").read_text(encoding="utf-8")
        )

    def save_snapshot(self, snapshot: IndexSnapshot) -> Path:
        return _atomic_write(self._path(snapshot.run_id, "index_snapshot.json"), _json(snapshot))

    def save_retrieval(self, run: RetrievalRun) -> Path:
        header = run.model_dump(mode="json", exclude={"cases"})
        records = [{"record_type": "header", "value": header}]
        records.extend(
            {"record_type": "case", "value": case.model_dump(mode="json")}
            for case in run.cases
        )
        body = "\n".join(json.dumps(item, ensure_ascii=False) for item in records) + "\n"
        return _atomic_write(self._path(run.run_id, "retrieval.jsonl"), body)

    def load_retrieval(self, run_id: str) -> RetrievalRun:
        records = [
            json.loads(line)
            for line in self._path(run_id, "retrieval.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if not records or records[0].get("record_type") != "header":
            raise ValueError(f"retrieval run {run_id} has no valid header")
        cases = [
            RetrievalCaseArtifact.model_validate(item["value"])
            for item in records[1:]
            if item.get("record_type") == "case"
        ]
        return RetrievalRun.model_validate({**records[0]["value"], "cases": cases})

    def save_generation(self, run: GenerationRun) -> Path:
        header = run.model_dump(mode="json", exclude={"cases"})
        records = [{"record_type": "header", "value": header}]
        records.extend(
            {"record_type": "case", "value": case.model_dump(mode="json")}
            for case in run.cases
        )
        body = "\n".join(json.dumps(item, ensure_ascii=False) for item in records) + "\n"
        return _atomic_write(self._path(run.run_id, "generation.jsonl"), body)

    def save_report(self, report: EvaluationReport) -> Path:
        return _atomic_write(self._path(report.run_id, "report.json"), _json(report))


class InMemoryRunRepository:
    def __init__(self) -> None:
        self.manifests: dict[str, RunManifest] = {}
        self.snapshots: dict[str, IndexSnapshot] = {}
        self.snapshot_save_calls = 0
        self.retrieval_runs: dict[str, RetrievalRun] = {}
        self.generation_runs: dict[str, GenerationRun] = {}
        self.reports: dict[str, EvaluationReport] = {}
        self.report_save_calls = 0

    def save_manifest(self, manifest: RunManifest) -> Path:
        self.manifests[manifest.run_id] = manifest
        return Path(manifest.run_id) / "manifest.json"

    def load_manifest(self, run_id: str) -> RunManifest:
        try:
            return self.manifests[run_id]
        except KeyError as exc:
            raise FileNotFoundError(f"manifest not found: {run_id}") from exc

    def save_snapshot(self, snapshot: IndexSnapshot) -> Path:
        self.snapshot_save_calls += 1
        self.snapshots[snapshot.run_id] = snapshot
        return Path(snapshot.run_id) / "index_snapshot.json"

    def save_retrieval(self, run: RetrievalRun) -> Path:
        self.retrieval_runs[run.run_id] = run
        return Path(run.run_id) / "retrieval.jsonl"

    def load_retrieval(self, run_id: str) -> RetrievalRun:
        try:
            return self.retrieval_runs[run_id]
        except KeyError as exc:
            raise FileNotFoundError(f"retrieval run not found: {run_id}") from exc

    def save_generation(self, run: GenerationRun) -> Path:
        self.generation_runs[run.run_id] = run
        return Path(run.run_id) / "generation.jsonl"

    def save_report(self, report: EvaluationReport) -> Path:
        self.report_save_calls += 1
        self.reports[report.run_id] = report
        return Path(report.run_id) / "report.json"
```

Add concrete shared test factories instead of leaving helper names implicit:

```python
# tests/support/evaluation_fakes.py
from datetime import UTC, datetime
from pathlib import Path

from domain.schemas import Chunk, DocumentStatus, SearchHit, SourceCoordinates
from evaluation.artifacts import (
    GenerationCaseArtifact,
    GenerationRun,
    RetrievalCaseArtifact,
    RetrievalRun,
    artifact_fingerprint,
    fingerprint,
)
from evaluation.golden import GoldenType, load_golden_dataset
from generation.execution import GenerationExecution, RankedHit, RetrievalExecution


def make_chunk(
    *,
    chunk_id: str = "chunk-1",
    text: str = "retrieved original text",
    position: int = 0,
    coordinates: SourceCoordinates | None = None,
) -> Chunk:
    return Chunk(
        id=chunk_id,
        document_id="document-1",
        version=1,
        text=text,
        content_hash="chunk-hash",
        source_name="01_2021_ND-CP_283247.docx",
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        status=DocumentStatus.READY,
        position=position,
        coordinates=coordinates or SourceCoordinates(
            doc_id="01_2021_ND-CP_283247.md", chapter="Chương I", article="Điều 1"
        ),
    )


def make_retrieval_run(
    *,
    run_id: str = "retrieval-1",
    dataset_scope: str = "partial",
    golden_dir: Path = Path("evaluation/golden_set"),
    canonical_source: Path = Path("data/extracted/01_2021_ND-CP_283247.md"),
) -> RetrievalRun:
    source_file = golden_dir / "golden_set_direct_lookup.json"
    dataset = load_golden_dataset(
        golden_dir,
        files=None if dataset_scope == "full" else [source_file],
    )
    hit = SearchHit(chunk=make_chunk(), score=0.9)
    case = RetrievalCaseArtifact(
        case_id="DL-001",
        type=GoldenType.DIRECT_LOOKUP,
        difficulty="easy",
        expected_answer="golden reference",
        golden_contexts=["retrieved original text"],
        retrieval=RetrievalExecution(
            question="golden question",
            request_id="request-1",
            hits=[RankedHit(rank=1, hit=hit)],
            latency_ms=1.0,
        ),
    )
    draft = RetrievalRun(
        run_id=run_id,
        created_at=datetime(2026, 8, 5, tzinfo=UTC),
        dataset_fingerprint=fingerprint(
            [case.model_dump(mode="json") for case in dataset.cases]
        ),
        golden_dir=golden_dir,
        dataset_source_files=dataset.source_files,
        dataset_scope=dataset.scope,
        canonical_source=canonical_source,
        index_snapshot_fingerprint="snapshot-fingerprint",
        configuration={"top_k": 5},
        cases=[case],
        run_fingerprint="",
    )
    return draft.model_copy(update={"run_fingerprint": artifact_fingerprint(draft)})


def make_generation_run(*, retrieval: RetrievalRun | None = None) -> GenerationRun:
    source = retrieval or make_retrieval_run()
    case = GenerationCaseArtifact(
        case_id="DL-001",
        generation=GenerationExecution(
            answer="generated answer [C1].",
            citations=[],
            structured_response={"answer": "generated answer [C1].", "citations": [1]},
            provider="fake",
            model="fake-model",
            prompt_version="v1",
            usage={},
            latency_ms=2.0,
        ),
    )
    draft = GenerationRun(
        run_id=source.run_id,
        created_at=datetime(2026, 8, 5, tzinfo=UTC),
        retrieval_run_fingerprint=source.run_fingerprint,
        configuration={"prompt_version": "v1", "model": "fake-model"},
        cases=[case],
        run_fingerprint="",
    )
    return draft.model_copy(update={"run_fingerprint": artifact_fingerprint(draft)})
```

Add this exact ignore rule:

```gitignore
reports/rag_evaluation/
```

- [ ] **Step 5: Run tests and commit**

Run:

```powershell
rtk proxy uv run pytest -p no:cacheprovider tests/unit/evaluation/test_artifacts.py -q
rtk ruff check src/evaluation/artifacts.py src/evaluation/repository.py tests/support/evaluation_fakes.py tests/unit/evaluation/test_artifacts.py
```

Expected: all tests PASS.

Commit:

```powershell
rtk git add .gitignore src/evaluation/artifacts.py src/evaluation/repository.py tests/support/evaluation_fakes.py tests/unit/evaluation/test_artifacts.py
rtk git commit -m "feat: persist replayable evaluation artifacts"
```

---

### Task 7: Deterministic Retrieval and Generation Metrics

**Files:**
- Create: `src/evaluation/metrics.py`
- Create: `tests/unit/evaluation/test_metrics.py`

**Interfaces:**
- Consumes: `GoldenCase`, ranked `SearchHit` values, answer text, and citations.
- Produces: `score_retrieval_case(case: GoldenCase, hits: list[SearchHit]) -> dict[str, float | None]`, `score_generation_case(case: GoldenCase, *, answer: str, cited_chunk_ids: set[str], retrieved_chunk_ids: set[str], retrieval_latency_ms: float, generation_latency_ms: float) -> dict[str, float | None]`, and `aggregate_scores(rows: list[dict[str, float | None]]) -> dict[str, float]`.

- [ ] **Step 1: Write failing coordinate/evidence/citation metric tests**

```python
# tests/unit/evaluation/test_metrics.py
from domain.schemas import Chunk, DocumentStatus, SearchHit, SourceCoordinates
from evaluation.golden import (
    Difficulty,
    GoldenCase,
    GoldenContext,
    GoldenMetadata,
    GoldenType,
)
from evaluation.metrics import aggregate_scores, score_generation_case, score_retrieval_case


def _context(article: str, text: str) -> GoldenContext:
    return GoldenContext(
        golden_truth_context=text,
        golden_metadata=GoldenMetadata(
            doc_id="law.md",
            chapter="Chương I",
            article=article,
        ),
    )


def _case(case_id: str, kind: GoldenType, contexts: list[GoldenContext]) -> GoldenCase:
    return GoldenCase(
        id=case_id,
        type=kind,
        question="Question",
        expected_answer="Answer",
        golden_truth_contexts=contexts,
        difficulty=Difficulty.EASY,
    )


def _multi_hop_case_with_articles(first: str, second: str) -> GoldenCase:
    return _case(
        "MH-001",
        GoldenType.MULTI_HOP,
        [_context(first, "first evidence"), _context(second, "second evidence")],
    )


def _unanswerable_case() -> GoldenCase:
    return _case("UA-001", GoldenType.UNANSWERABLE, [])


def _direct_case() -> GoldenCase:
    return _case("DL-001", GoldenType.DIRECT_LOOKUP, [_context("Điều 1", "evidence")])


def _hit(*, article: str, text: str) -> SearchHit:
    return SearchHit(
        chunk=Chunk(
            id=f"chunk-{article}",
            document_id="document-1",
            version=1,
            text=text,
            content_hash=f"hash-{article}",
            source_name="law.docx",
            mime_type="application/docx",
            status=DocumentStatus.READY,
            position=0,
            coordinates=SourceCoordinates(doc_id="law.md", chapter="Chương I", article=article),
        ),
        score=0.9,
    )


def test_multi_hop_coordinate_recall_requires_every_unique_coordinate() -> None:
    case = _multi_hop_case_with_articles("Điều 1", "Điều 2")
    hits = [_hit(article="Điều 1", text="first evidence")]

    scores = score_retrieval_case(case, hits)

    assert scores["coordinate_recall"] == 0.5


def test_unanswerable_is_excluded_from_retrieval_recall() -> None:
    assert score_retrieval_case(_unanswerable_case(), []) == {
        "coordinate_recall": None,
        "evidence_recall": None,
    }


def test_invalid_citation_is_detected() -> None:
    scores = score_generation_case(
        _direct_case(),
        answer="Trả lời [C1].",
        cited_chunk_ids={"not-retrieved"},
        retrieved_chunk_ids={"retrieved"},
        retrieval_latency_ms=10.0,
        generation_latency_ms=20.0,
    )
    assert scores["citation_validity"] == 0.0
```

- [ ] **Step 2: Run tests and verify metric functions are missing**

Run:

```powershell
rtk proxy uv run pytest -p no:cacheprovider tests/unit/evaluation/test_metrics.py -q
```

Expected: FAIL during import.

- [ ] **Step 3: Implement deterministic metric definitions**

```python
# src/evaluation/metrics.py
from __future__ import annotations

import re
from collections import defaultdict
from statistics import mean

from domain.schemas import SearchHit
from evaluation.golden import GoldenCase, GoldenType
from generation.service import ABSTENTION


def _normalized(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def score_retrieval_case(case: GoldenCase, hits: list[SearchHit]) -> dict[str, float | None]:
    if not case.golden_truth_contexts:
        return {"coordinate_recall": None, "evidence_recall": None}
    required_coordinates = {
        (item.golden_metadata.doc_id, item.golden_metadata.chapter, item.golden_metadata.article)
        for item in case.golden_truth_contexts
    }
    retrieved_coordinates = {
        (hit.chunk.coordinates.doc_id, hit.chunk.coordinates.chapter, hit.chunk.coordinates.article)
        for hit in hits
    }
    grouped: dict[tuple[str, str | None, str | None], list[tuple[int, str]]] = defaultdict(list)
    for hit in hits:
        key = (hit.chunk.coordinates.doc_id, hit.chunk.coordinates.chapter, hit.chunk.coordinates.article)
        grouped[key].append((hit.chunk.position, hit.chunk.text))
    recovered = 0
    for item in case.golden_truth_contexts:
        metadata = item.golden_metadata
        key = (metadata.doc_id, metadata.chapter, metadata.article)
        text = "".join(value for _, value in sorted(grouped.get(key, [])))
        recovered += _normalized(item.golden_truth_context) in _normalized(text)
    return {
        "coordinate_recall": len(required_coordinates & retrieved_coordinates) / len(required_coordinates),
        "evidence_recall": recovered / len(case.golden_truth_contexts),
    }


def score_generation_case(
    case: GoldenCase,
    *,
    answer: str,
    cited_chunk_ids: set[str],
    retrieved_chunk_ids: set[str],
    retrieval_latency_ms: float,
    generation_latency_ms: float,
) -> dict[str, float | None]:
    abstained = answer.strip() == ABSTENTION
    sentences = [item.strip() for item in re.split(r"(?<=[.!?])\s+", answer) if item.strip()]
    cited_sentences = sum(bool(re.search(r"\[C\d+\]", sentence)) for sentence in sentences)
    return {
        "citation_validity": 1.0 if cited_chunk_ids <= retrieved_chunk_ids else 0.0,
        "citation_coverage": 1.0 if abstained else cited_sentences / max(len(sentences), 1),
        "abstention_accuracy": (1.0 if abstained else 0.0) if case.type is GoldenType.UNANSWERABLE else None,
        "retrieval_latency_ms": retrieval_latency_ms,
        "generation_latency_ms": generation_latency_ms,
        "end_to_end_latency_ms": retrieval_latency_ms + generation_latency_ms,
    }


def aggregate_scores(rows: list[dict[str, float | None]]) -> dict[str, float]:
    keys = sorted({key for row in rows for key in row})
    return {
        key: mean(values)
        for key in keys
        if (values := [float(row[key]) for row in rows if row.get(key) is not None])
    }
```

- [ ] **Step 4: Add aggregate-by-type/difficulty and p95 tests**

Add this test:

```python
from evaluation.metrics import compare_to_target, percentile_95, segment_aggregates


def test_segment_aggregates_exclude_nulls_and_report_latency_p95() -> None:
    cases = [_direct_case(), _unanswerable_case()]
    rows = [
        {"coordinate_recall": 0.5, "retrieval_latency_ms": 10.0},
        {"coordinate_recall": None, "retrieval_latency_ms": 30.0},
    ]

    aggregates = segment_aggregates(cases, rows)

    assert aggregates["overall"]["coordinate_recall"] == 0.5
    assert aggregates["overall"]["retrieval_latency_ms_p95"] == 30.0
    assert percentile_95([10.0, 30.0]) == 30.0


def test_target_comparison_is_report_only_metadata() -> None:
    comparison = compare_to_target(
        {"overall": {"coordinate_recall": 0.84, "retrieval_latency_ms": 10.0}}
    )

    assert comparison == {
        "overall": {
            "coordinate_recall": {"target": 0.85, "meets_target": False}
        }
    }
```

Implement nearest-rank p95 and segmentation exactly as follows:

```python
# append to src/evaluation/metrics.py
from math import ceil
from typing import Any


def percentile_95(values: list[float]) -> float:
    if not values:
        raise ValueError("percentile requires at least one value")
    ordered = sorted(values)
    return ordered[max(ceil(0.95 * len(ordered)) - 1, 0)]


def _aggregate_segment(rows: list[dict[str, float | None]]) -> dict[str, float]:
    output = aggregate_scores(rows)
    for key in sorted({name for row in rows for name in row if name.endswith("latency_ms")}):
        values = [float(row[key]) for row in rows if row.get(key) is not None]
        if values:
            output[f"{key}_p95"] = percentile_95(values)
    return output


def segment_aggregates(
    cases: list[GoldenCase],
    rows: list[dict[str, float | None]],
) -> dict[str, Any]:
    if len(cases) != len(rows):
        raise ValueError("cases and score rows must have equal length")
    pairs = list(zip(cases, rows, strict=True))
    return {
        "overall": _aggregate_segment(rows),
        "by_type": {
            kind.value: _aggregate_segment([row for case, row in pairs if case.type is kind])
            for kind in GoldenType
            if any(case.type is kind for case, _ in pairs)
        },
        "by_difficulty": {
            difficulty.value: _aggregate_segment(
                [row for case, row in pairs if case.difficulty is difficulty]
            )
            for difficulty in Difficulty
            if any(case.difficulty is difficulty for case, _ in pairs)
        },
    }


RATE_METRICS = {
    "coordinate_recall",
    "evidence_recall",
    "citation_validity",
    "citation_coverage",
    "abstention_accuracy",
    "context_precision",
    "context_recall",
    "faithfulness",
    "answer_relevancy",
}


def compare_to_target(value: dict[str, Any], target: float = 0.85) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, item in value.items():
        if isinstance(item, dict):
            nested = compare_to_target(item, target)
            if nested:
                output[key] = nested
        elif key in RATE_METRICS and isinstance(item, (int, float)):
            output[key] = {"target": target, "meets_target": float(item) >= target}
    return output
```

- [ ] **Step 5: Run tests and commit**

Run:

```powershell
rtk proxy uv run pytest -p no:cacheprovider tests/unit/evaluation/test_metrics.py -q
rtk ruff check src/evaluation/metrics.py tests/unit/evaluation/test_metrics.py
```

Expected: all tests PASS.

Commit:

```powershell
rtk git add src/evaluation/metrics.py tests/unit/evaluation/test_metrics.py
rtk git commit -m "feat: score deterministic rag quality"
```

---

### Task 8: Staged EvaluationRunner Modes and Failure Semantics

**Files:**
- Replace: `src/evaluation/runner.py`
- Create: `tests/unit/evaluation/test_runner.py`
- Delete after replacement coverage passes: `tests/unit/evaluation/test_scoring.py`

**Interfaces:**
- Consumes: Tasks 1-7 plus injected ingestion, registry, store, chat, repository, settings snapshot, and semantic judge.
- Produces: the approved `EvaluationRunner.run(request) -> EvaluationReport` interface for all CLI modes, single-write snapshots/reports, and generation replay that inherits the saved retrieval run's complete golden/canonical selection.

- [ ] **Step 1: Write failing validate/retrieval/replay/e2e orchestration tests**

```python
# tests/unit/evaluation/test_runner.py
from pathlib import Path

import pytest
from pydantic import ValidationError

from domain.schemas import Document, DocumentStatus, SearchHit, SourceCoordinates
from evaluation.artifacts import EvaluationMode, EvaluationRequest
from evaluation.golden import load_golden_dataset
from evaluation.repository import InMemoryRunRepository
from evaluation.runner import EvaluationRunner
from generation.execution import GenerationExecution, RankedHit, RetrievalExecution
from tests.support.evaluation_fakes import make_chunk, make_retrieval_run


class ExplodingDependency:
    def __getattr__(self, name: str):
        raise AssertionError(f"runtime dependency used during validation: {name}")


class FakeRegistry:
    def __init__(self) -> None:
        self.document = Document(
            id="document-1",
            version=1,
            content_hash="raw-hash",
            source_name="01_2021_ND-CP_283247.docx",
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            status=DocumentStatus.READY,
            metadata={"canonical_doc_id": "01_2021_ND-CP_283247.md"},
        )

    def find_by_source(self, source_name: str) -> Document | None:
        return self.document if source_name == self.document.source_name else None


class FakeStore:
    def __init__(self) -> None:
        dataset = load_golden_dataset(Path("evaluation/golden_set"))
        self.chunks = [
            make_chunk(
                chunk_id=f"{case.id}-{context_index}",
                text=context.golden_truth_context,
                position=position,
                coordinates=SourceCoordinates(
                    doc_id=context.golden_metadata.doc_id,
                    chapter=context.golden_metadata.chapter,
                    article=context.golden_metadata.article,
                ),
            )
            for position, (case, context_index, context) in enumerate(
                (case, context_index, context)
                for case in dataset.cases
                for context_index, context in enumerate(case.golden_truth_contexts)
            )
        ]
        self.chunk = self.chunks[0]
        self.search_calls = 0

    def list_document_chunks(self, document_id: str, version: int | None = None):
        return self.chunks

    def search(self, query: str, limit: int = 5):
        self.search_calls += 1
        return [SearchHit(chunk=self.chunk, score=0.9)]


class FakeChat:
    def __init__(self, store: FakeStore, *, fail_first_retrieval: bool = False) -> None:
        self.store = store
        self.fail_first_retrieval = fail_first_retrieval
        self.retrieval_calls = 0

    def retrieve(self, question: str, request_id: str | None = None) -> RetrievalExecution:
        self.retrieval_calls += 1
        if self.fail_first_retrieval and self.retrieval_calls == 1:
            raise RuntimeError("controlled retrieval failure")
        hit = SearchHit(chunk=self.store.chunk, score=0.9)
        return RetrievalExecution(
            question=question,
            request_id=request_id or f"request-{self.retrieval_calls}",
            hits=[RankedHit(rank=1, hit=hit)],
            latency_ms=1.0,
        )

    def generate_from_hits(
        self,
        question: str,
        hits: list[SearchHit],
        request_id: str | None = None,
    ) -> GenerationExecution:
        return GenerationExecution(
            answer="Answer [C1].",
            citations=[],
            structured_response={"answer": "Answer [C1].", "citations": [1]},
            provider="fake",
            model="fake-model",
            prompt_version="v1",
            usage={},
            latency_ms=2.0,
        )


class FakeIngestion:
    def __init__(self) -> None:
        self.calls = 0

    def ingest_bytes(self, *args: object, **kwargs: object) -> Document:
        self.calls += 1
        return FakeRegistry().document


def _runner(tmp_path: Path, *, fail_if_runtime_used: bool = False) -> EvaluationRunner:
    repository = InMemoryRunRepository()
    if fail_if_runtime_used:
        exploding = ExplodingDependency()
        return EvaluationRunner(
            ingestion=exploding,
            registry=exploding,
            store=exploding,
            chat=exploding,
            repository=repository,
            runtime_configuration={},
            semantic_judge=None,
        )
    store = FakeStore()
    return EvaluationRunner(
        ingestion=None,
        registry=FakeRegistry(),
        store=store,
        chat=FakeChat(store),
        repository=repository,
        runtime_configuration={"qdrant_collection": "test"},
        semantic_judge=None,
    )


def _runner_with_one_retrieval_failure(tmp_path: Path) -> EvaluationRunner:
    runner = _runner(tmp_path)
    runner.chat = FakeChat(runner.store, fail_first_retrieval=True)
    return runner


def _runner_with_saved_retrieval(tmp_path: Path) -> tuple[EvaluationRunner, FakeStore]:
    runner = _runner(tmp_path)
    runner.repository.save_retrieval(make_retrieval_run())
    return runner, runner.store


def _successful_runner(tmp_path: Path) -> EvaluationRunner:
    return _runner(tmp_path)


def test_validate_mode_never_builds_runtime_dependencies(tmp_path) -> None:
    runner = _runner(tmp_path, fail_if_runtime_used=True)

    report = runner.run(EvaluationRequest(mode=EvaluationMode.VALIDATE))

    assert report.mode is EvaluationMode.VALIDATE
    assert report.evaluated_cases == 0
    assert report.status == "complete"


def test_retrieval_mode_continues_after_case_error(tmp_path) -> None:
    runner = _runner_with_one_retrieval_failure(tmp_path)

    report = runner.run(EvaluationRequest(mode=EvaluationMode.RETRIEVAL, limit=2))

    assert report.evaluated_cases == 2
    assert report.status == "incomplete"
    assert len(report.errors) == 1
    assert runner.repository.retrieval_runs


def test_generation_mode_reuses_saved_hits_without_search(tmp_path) -> None:
    runner, store = _runner_with_saved_retrieval(tmp_path)

    report = runner.run(EvaluationRequest(mode=EvaluationMode.GENERATION, from_run="retrieval-1"))

    assert report.status == "complete"
    assert store.search_calls == 0


def test_generation_request_rejects_replacement_selection() -> None:
    with pytest.raises(ValidationError, match="inherits the saved retrieval selection"):
        EvaluationRequest(
            mode=EvaluationMode.GENERATION,
            from_run="retrieval-1",
            canonical_source=Path("replacement.md"),
        )


def test_generation_inherits_full_golden_and_canonical_selection(tmp_path: Path) -> None:
    golden_dir = tmp_path / "golden"
    golden_dir.mkdir()
    for source in Path("evaluation/golden_set").glob("*.json"):
        (golden_dir / source.name).write_bytes(source.read_bytes())
    canonical_source = tmp_path / "01_2021_ND-CP_283247.md"
    canonical_source.write_bytes(
        Path("data/extracted/01_2021_ND-CP_283247.md").read_bytes()
    )
    runner, store = _runner_with_saved_retrieval(tmp_path)
    runner.repository.retrieval_runs.clear()
    runner.repository.save_retrieval(
        make_retrieval_run(
            dataset_scope="full",
            golden_dir=golden_dir,
            canonical_source=canonical_source,
        )
    )

    report = runner.run(
        EvaluationRequest(mode=EvaluationMode.GENERATION, from_run="retrieval-1")
    )

    manifest = runner.repository.manifests[report.run_id]
    assert report.status == "complete"
    assert store.search_calls == 0
    assert manifest.arguments["golden_dir"] == str(golden_dir)
    assert manifest.arguments["canonical_source"] == str(canonical_source)


def test_e2e_reuses_existing_index_unless_ingest_is_explicit(tmp_path) -> None:
    runner = _runner(tmp_path)
    ingestion = FakeIngestion()
    runner.ingestion = ingestion

    report = runner.run(EvaluationRequest(mode=EvaluationMode.E2E, limit=1))

    assert report.status == "complete"
    assert ingestion.calls == 0
    assert runner.repository.report_save_calls == 1


def test_only_full_complete_e2e_is_baseline_eligible(tmp_path) -> None:
    runner = _successful_runner(tmp_path)
    full = runner.run(EvaluationRequest(mode=EvaluationMode.E2E))
    limited = runner.run(EvaluationRequest(mode=EvaluationMode.E2E, limit=5))
    assert full.baseline_eligible is True
    assert limited.baseline_eligible is False


def test_e2e_ingestion_saves_one_immutable_snapshot(tmp_path: Path) -> None:
    source = tmp_path / "01_2021_ND-CP_283247.docx"
    source.write_bytes(b"fake-docx")
    runner = _runner(tmp_path)
    runner.ingestion = FakeIngestion()

    report = runner.run(
        EvaluationRequest(mode=EvaluationMode.E2E, ingestion_source=source, limit=1)
    )

    assert report.status == "complete"
    assert runner.repository.snapshot_save_calls == 1


@pytest.mark.parametrize("mode", [EvaluationMode.VALIDATE, EvaluationMode.GENERATION])
def test_preflight_failures_are_retained_as_reports(
    tmp_path: Path,
    mode: EvaluationMode,
) -> None:
    runner = _runner(tmp_path)
    request = (
        EvaluationRequest(mode=mode, canonical_source=tmp_path / "missing.md")
        if mode is EvaluationMode.VALIDATE
        else EvaluationRequest(mode=mode, from_run="missing-retrieval")
    )

    report = runner.run(request)

    assert report.status == "failed"
    assert report.errors[0].startswith("FileNotFoundError:")
    assert report.report_path is not None
    assert runner.repository.report_save_calls == 1
```

- [ ] **Step 2: Run tests and confirm staged runner is absent**

Run:

```powershell
rtk proxy uv run pytest -p no:cacheprovider tests/unit/evaluation/test_runner.py -q
```

Expected: FAIL because the legacy runner does not accept `EvaluationRequest`.

- [ ] **Step 3: Define the semantic judge port and runner constructor**

```python
# src/evaluation/runner.py
from typing import Protocol


class SemanticJudge(Protocol):
    def score_retrieval(self, run: RetrievalRun) -> SemanticScoreBatch:
        raise NotImplementedError

    def score_generation(
        self,
        retrieval: RetrievalRun,
        generation: GenerationRun,
    ) -> SemanticScoreBatch:
        raise NotImplementedError


class EvaluationRunner:
    def __init__(
        self,
        *,
        ingestion: IngestionService | None,
        registry: DocumentRegistry | None,
        store: ChunkStore | None,
        chat: ChatService | None,
        repository: LocalRunRepository | InMemoryRunRepository,
        runtime_configuration: dict[str, object],
        semantic_judge: SemanticJudge | None,
    ) -> None:
        self.ingestion = ingestion
        self.registry = registry
        self.store = store
        self.chat = chat
        self.repository = repository
        self.runtime_configuration = runtime_configuration
        self.semantic_judge = semantic_judge
```

- [ ] **Step 4: Implement validation, selection, and index preflight helpers**

Add these private methods to `EvaluationRunner`; they centralize ordering and make every mode validate before touching runtime dependencies:

```python
    def run(self, request: EvaluationRequest) -> EvaluationReport:
        run_id = uuid4().hex
        try:
            replay_source = (
                self.repository.load_retrieval(request.from_run)
                if request.mode is EvaluationMode.GENERATION and request.from_run is not None
                else None
            )
            effective_request = request
            if replay_source is not None:
                replay_files = [Path(path) for path in replay_source.dataset_source_files]
                effective_request = request.model_copy(update={
                    "golden_dir": replay_source.golden_dir,
                    "golden_files": replay_files if replay_source.dataset_scope == "partial" else [],
                    "canonical_source": replay_source.canonical_source,
                })
                dataset = load_golden_dataset(
                    replay_source.golden_dir,
                    files=replay_files if replay_source.dataset_scope == "partial" else None,
                )
                if dataset.source_files != replay_source.dataset_source_files:
                    raise ValueError("retrieval artifact golden source-file selection is incompatible")
            else:
                dataset = load_golden_dataset(
                    request.golden_dir,
                    files=request.golden_files or None,
                )
            self.repository.save_manifest(self._build_manifest(effective_request, dataset, run_id))
            validation = validate_golden_dataset(
                dataset,
                canonical_path=effective_request.canonical_source,
                chunks=None,
                audit_root=effective_request.golden_dir.parent,
            )
            if validation.errors:
                return self._finish_report(
                    EvaluationReport(
                        run_id=run_id,
                        mode=request.mode,
                        status="failed",
                        dataset_size=len(dataset.cases),
                        evaluated_cases=0,
                        validation=validation.model_dump(mode="json"),
                        aggregates={},
                        errors=[issue.message for issue in validation.errors],
                        artifact_ids={},
                        baseline_eligible=False,
                    )
                )
            selected = (
                []
                if request.mode in {EvaluationMode.VALIDATE, EvaluationMode.INGEST, EvaluationMode.GENERATION}
                else select_cases(
                    dataset,
                    question_types=request.question_types or None,
                    case_ids=request.case_ids or None,
                    limit=request.limit,
                )
            )
            try:
                if effective_request.mode is EvaluationMode.VALIDATE:
                    return self._run_validate(effective_request, dataset, validation, run_id)
                if effective_request.mode is EvaluationMode.INGEST:
                    return self._run_ingest(effective_request, dataset, validation, run_id)
                if effective_request.mode is EvaluationMode.RETRIEVAL:
                    return self._finish_report(
                        self._retrieval_report(effective_request, dataset, selected, validation, run_id)
                    )
                if effective_request.mode is EvaluationMode.GENERATION:
                    return self._finish_report(
                        self._generation_report(effective_request, dataset, validation, run_id)
                    )
                return self._run_e2e(effective_request, dataset, selected, validation, run_id)
            except Exception as exc:
                return self._finish_report(
                    EvaluationReport(
                        run_id=run_id,
                        mode=request.mode,
                        status="failed",
                        dataset_size=len(dataset.cases),
                        evaluated_cases=0,
                        validation=validation.model_dump(mode="json"),
                        aggregates={},
                        errors=[f"{type(exc).__name__}: {exc}"],
                        artifact_ids={},
                        baseline_eligible=False,
                    )
                )
        except Exception as exc:
            return self._finish_report(
                EvaluationReport(
                    run_id=run_id,
                    mode=request.mode,
                    status="failed",
                    dataset_size=0,
                    evaluated_cases=0,
                    validation=GoldenValidationReport(
                        errors=[],
                        warnings=[],
                        validated_cases=0,
                        full_conformance=False,
                    ).model_dump(mode="json"),
                    aggregates={},
                    errors=[f"{type(exc).__name__}: {exc}"],
                    artifact_ids={},
                    baseline_eligible=False,
                )
            )
    def _finish_report(self, report: EvaluationReport) -> EvaluationReport:
        try:
            manifest = self.repository.load_manifest(report.run_id)
        except FileNotFoundError:
            pass
        else:
            self.repository.save_manifest(
                manifest.model_copy(update={"artifact_lineage": report.artifact_ids})
            )
        path = self.repository.save_report(report)
        return report.model_copy(update={"report_path": path})

    def _build_manifest(
        self,
        request: EvaluationRequest,
        dataset: GoldenDataset,
        run_id: str,
    ) -> RunManifest:
        raw_path = request.ingestion_source or Path(
            "data/raw/01_2021_ND-CP_283247.docx"
        )
        source_fingerprints = {
            "canonical": sha256(request.canonical_source.read_bytes()).hexdigest()
        }
        if raw_path.exists():
            source_fingerprints["raw"] = sha256(raw_path.read_bytes()).hexdigest()
        try:
            ragas_version = package_version("ragas")
        except PackageNotFoundError:
            ragas_version = "not-installed"
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            check=False,
            text=True,
        )
        return RunManifest(
            run_id=run_id,
            mode=request.mode,
            arguments=request.model_dump(mode="json"),
            git_revision=revision.stdout.strip() if revision.returncode == 0 else None,
            dataset_fingerprint=fingerprint(
                [case.model_dump(mode="json") for case in dataset.cases]
            ),
            source_fingerprints=source_fingerprints,
            configuration_fingerprints={
                "runtime": fingerprint(self.runtime_configuration),
                "selection": fingerprint(
                    {
                        "golden_dir": str(request.golden_dir),
                        "files": [str(path) for path in request.golden_files],
                        "types": sorted(item.value for item in request.question_types),
                        "case_ids": sorted(request.case_ids),
                        "limit": request.limit,
                        "canonical_source": str(request.canonical_source),
                    }
                ),
            },
            dependency_versions={
                "python": platform.python_version(),
                "ragas": ragas_version,
            },
            artifact_lineage={},
        )

    def _run_validate(
        self,
        request: EvaluationRequest,
        dataset: GoldenDataset,
        validation: GoldenValidationReport,
        run_id: str,
    ) -> EvaluationReport:
        return self._finish_report(
            EvaluationReport(
                run_id=run_id,
                mode=request.mode,
                status="complete",
                dataset_size=len(dataset.cases),
                evaluated_cases=0,
                validation=validation.model_dump(mode="json"),
                aggregates={},
                errors=[],
                artifact_ids={},
                baseline_eligible=False,
            )
        )

    def _preflight_index(self, request: EvaluationRequest) -> tuple[Document, list[Chunk]]:
        if self.registry is None or self.store is None:
            raise RuntimeError("index runtime is unavailable")
        source_name = (
            request.ingestion_source.name
            if request.ingestion_source is not None
            else "01_2021_ND-CP_283247.docx"
        )
        document = self.registry.find_by_source(source_name)
        chunks = (
            []
            if document is None or document.status is not DocumentStatus.READY
            else self.store.list_document_chunks(document.id, document.version)
        )
        canonical_ids = {chunk.coordinates.doc_id for chunk in chunks}
        coordinates_valid = all(
            chunk.coordinates.article is None or chunk.coordinates.chapter is not None
            for chunk in chunks
        )
        payloads_valid = (
            all(
                chunk.text
                and chunk.content_hash
                and chunk.version == document.version
                and chunk.status is DocumentStatus.READY
                for chunk in chunks
            )
            and len({chunk.position for chunk in chunks}) == len(chunks)
        )
        if (
            document is None
            or not chunks
            or canonical_ids != {request.canonical_source.name}
            or not coordinates_valid
            or not payloads_valid
        ):
            raise RuntimeError(
                "Index is missing or incompatible. Run:\n"
                "rag-eval ingest --source data/raw/01_2021_ND-CP_283247.docx"
            )
        return document, chunks

    def _build_snapshot(
        self,
        run_id: str,
        request: EvaluationRequest,
        document: Document,
        chunks: list[Chunk],
        validation: GoldenValidationReport,
    ) -> IndexSnapshot:
        source_hash = document.content_hash
        if request.ingestion_source is not None:
            source_hash = sha256(request.ingestion_source.read_bytes()).hexdigest()
        draft = IndexSnapshot(
            run_id=run_id,
            document_id=document.id,
            document_version=document.version,
            source_name=document.source_name,
            canonical_doc_id=request.canonical_source.name,
            raw_source_hash=source_hash,
            canonical_source_hash=sha256(request.canonical_source.read_bytes()).hexdigest(),
            chunk_count=len(chunks),
            collection_name=str(self.runtime_configuration.get("qdrant_collection", "memory")),
            configuration=self.runtime_configuration,
            metadata_validation=validation.model_dump(mode="json"),
            chunks=chunks,
            snapshot_fingerprint="",
        )
        return draft.model_copy(
            update={"snapshot_fingerprint": artifact_fingerprint(draft)}
        )
```

Import `platform`, `subprocess`, `sha256`, `Path`, `uuid4`, `importlib.metadata.version as package_version`, `PackageNotFoundError`, the golden/report models, `Document`, `DocumentStatus`, `Chunk`, and `compare_to_target`, `score_retrieval_case`, `score_generation_case`, and `segment_aggregates` from `evaluation.metrics`. Standard type-filtered runs validate all 100 cases before `select_cases`; explicit `golden_files` validate only supplied files. The exact preflight recovery message is:

```text
Index is missing or incompatible. Run:
rag-eval ingest --source data/raw/01_2021_ND-CP_283247.docx
```

- [ ] **Step 5: Implement `ingest` and `retrieval` modes**

Add one shared ingestion helper and the two mode methods:

```python
    def _ingest_source(self, request: EvaluationRequest) -> tuple[Document, list[Chunk]]:
        if self.ingestion is None or self.store is None or request.ingestion_source is None:
            raise RuntimeError("ingestion runtime and source are required")
        source_path = request.ingestion_source
        document = self.ingestion.ingest_bytes(
            source_path.name,
            source_path.read_bytes(),
            {"canonical_doc_id": request.canonical_source.name},
            force=request.force_reingest,
        )
        if document.status is not DocumentStatus.READY:
            raise RuntimeError(f"ingestion ended with status {document.status}")
        chunks = self.store.list_document_chunks(document.id, document.version)
        if not chunks:
            raise RuntimeError("ingestion produced no indexed chunks")
        return document, chunks

    def _run_ingest(
        self,
        request: EvaluationRequest,
        dataset: GoldenDataset,
        validation: GoldenValidationReport,
        run_id: str,
    ) -> EvaluationReport:
        try:
            document, chunks = self._ingest_source(request)
            chunk_validation = validate_golden_dataset(
                dataset,
                request.canonical_source,
                chunks=chunks,
                audit_root=request.golden_dir.parent,
            )
            if chunk_validation.errors:
                raise ValueError("; ".join(issue.message for issue in chunk_validation.errors))
            snapshot = self._build_snapshot(run_id, request, document, chunks, chunk_validation)
            self.repository.save_snapshot(snapshot)
            return self._finish_report(
                EvaluationReport(
                    run_id=run_id,
                    mode=request.mode,
                    status="complete",
                    dataset_size=len(dataset.cases),
                    evaluated_cases=0,
                    validation=chunk_validation.model_dump(mode="json"),
                    aggregates={},
                    errors=[],
                    artifact_ids={"index_snapshot": snapshot.snapshot_fingerprint},
                    baseline_eligible=False,
                )
            )
        except Exception as exc:
            return self._finish_report(
                EvaluationReport(
                    run_id=run_id,
                    mode=request.mode,
                    status="failed",
                    dataset_size=len(dataset.cases),
                    evaluated_cases=0,
                    validation=validation.model_dump(mode="json"),
                    aggregates={},
                    errors=[f"{type(exc).__name__}: {exc}"],
                    artifact_ids={},
                    baseline_eligible=False,
                )
            )

    def _retrieval_report(
        self,
        request: EvaluationRequest,
        dataset: GoldenDataset,
        selected: list[GoldenCase],
        validation: GoldenValidationReport,
        run_id: str,
    ) -> EvaluationReport:
        if self.chat is None:
            raise RuntimeError("chat runtime is unavailable")
        document, chunks = self._preflight_index(request)
        validation = validate_golden_dataset(
            dataset,
            request.canonical_source,
            chunks=chunks,
            audit_root=request.golden_dir.parent,
        )
        if validation.errors:
            raise ValueError("; ".join(issue.message for issue in validation.errors))
        snapshot = self._build_snapshot(run_id, request, document, chunks, validation)
        self.repository.save_snapshot(snapshot)
        artifacts: list[RetrievalCaseArtifact] = []
        errors: list[str] = []
        for case in selected:
            try:
                execution = self.chat.retrieve(case.question)
                hits = [item.hit for item in execution.hits]
                artifacts.append(
                    RetrievalCaseArtifact(
                        case_id=case.id,
                        type=case.type,
                        difficulty=case.difficulty.value,
                        expected_answer=case.expected_answer,
                        golden_contexts=[
                            item.golden_truth_context for item in case.golden_truth_contexts
                        ],
                        retrieval=execution,
                        deterministic_scores=score_retrieval_case(case, hits),
                    )
                )
            except Exception as exc:
                message = f"{case.id}: {type(exc).__name__}: {exc}"
                errors.append(message)
                artifacts.append(
                    RetrievalCaseArtifact(
                        case_id=case.id,
                        type=case.type,
                        difficulty=case.difficulty.value,
                        expected_answer=case.expected_answer,
                        golden_contexts=[
                            item.golden_truth_context for item in case.golden_truth_contexts
                        ],
                        retrieval=None,
                        error=message,
                    )
                )
        draft = RetrievalRun(
            run_id=run_id,
            dataset_fingerprint=fingerprint(
                [case.model_dump(mode="json") for case in dataset.cases]
            ),
            golden_dir=request.golden_dir,
            dataset_source_files=dataset.source_files,
            dataset_scope=dataset.scope,
            canonical_source=request.canonical_source,
            index_snapshot_fingerprint=snapshot.snapshot_fingerprint,
            configuration=self.runtime_configuration,
            cases=artifacts,
            run_fingerprint="",
        )
        retrieval = draft.model_copy(
            update={"run_fingerprint": artifact_fingerprint(draft)}
        )
        semantic_scores: dict[str, dict[str, float | None]] = {}
        if request.run_ragas:
            if self.semantic_judge is None:
                errors.append("Ragas requested but semantic judge is unavailable")
            else:
                batch = self.semantic_judge.score_retrieval(retrieval)
                semantic_scores = batch.scores
                errors.extend(
                    f"{case_id}: {message}"
                    for case_id, messages in batch.errors.items()
                    for message in messages
                )
        self.repository.save_retrieval(retrieval)
        status = "complete" if not errors else "incomplete"
        successful_ids = {
            item.case_id for item in retrieval.cases if item.retrieval is not None
        }
        aggregates = segment_aggregates(
            [case for case in selected if case.id in successful_ids],
            [
                item.deterministic_scores | semantic_scores.get(item.case_id, {})
                for item in retrieval.cases
                if item.retrieval is not None
            ],
        )
        case_scores = {
            item.case_id: item.deterministic_scores | semantic_scores.get(item.case_id, {})
            for item in retrieval.cases
        }
        return EvaluationReport(
            run_id=run_id,
            mode=request.mode,
            status=status,
            dataset_size=len(dataset.cases),
            evaluated_cases=len(selected),
            validation=validation.model_dump(mode="json"),
            aggregates=aggregates,
            target_comparison=compare_to_target(aggregates),
            case_scores=case_scores,
            errors=errors,
            artifact_ids={
                "index_snapshot": snapshot.snapshot_fingerprint,
                "retrieval_run": retrieval.run_fingerprint,
            },
            baseline_eligible=False,
        )
```

- [ ] **Step 6: Implement generation replay and e2e modes**

Add generation replay exactly against saved ranked hits, followed by the composing e2e method:

```python
    def _generation_report(
        self,
        request: EvaluationRequest,
        dataset: GoldenDataset,
        validation: GoldenValidationReport,
        run_id: str,
    ) -> EvaluationReport:
        if self.chat is None or request.from_run is None:
            raise RuntimeError("generation runtime and from_run are required")
        retrieval = self.repository.load_retrieval(request.from_run)
        expected_dataset_fingerprint = fingerprint(
            [case.model_dump(mode="json") for case in dataset.cases]
        )
        if retrieval.dataset_fingerprint != expected_dataset_fingerprint:
            raise ValueError("retrieval artifact dataset fingerprint is incompatible")
        if retrieval.run_fingerprint != artifact_fingerprint(retrieval):
            raise ValueError("retrieval artifact fingerprint is invalid")
        known_ids = {case.id for case in dataset.cases}
        if {case.case_id for case in retrieval.cases} - known_ids:
            raise ValueError("retrieval artifact contains unknown case IDs")
        if retrieval.run_id != run_id:
            self.repository.save_retrieval(retrieval.model_copy(update={"run_id": run_id}))

        golden_by_id = {case.id: case for case in dataset.cases}
        generated_cases: list[GenerationCaseArtifact] = []
        errors: list[str] = []
        for source in retrieval.cases:
            golden = golden_by_id[source.case_id]
            if source.retrieval is None:
                message = f"{source.case_id}: retrieval evidence is unavailable"
                errors.append(message)
                generated_cases.append(
                    GenerationCaseArtifact(
                        case_id=source.case_id,
                        generation=None,
                        error=message,
                    )
                )
                continue
            hits = [item.hit for item in source.retrieval.hits]
            try:
                generated = self.chat.generate_from_hits(
                    source.retrieval.question,
                    hits,
                    source.retrieval.request_id,
                )
                deterministic_scores = score_generation_case(
                    golden,
                    answer=generated.answer,
                    cited_chunk_ids={item.chunk_id for item in generated.citations},
                    retrieved_chunk_ids={hit.chunk.id for hit in hits},
                    retrieval_latency_ms=source.retrieval.latency_ms,
                    generation_latency_ms=generated.latency_ms,
                )
                if deterministic_scores["citation_validity"] != 1.0:
                    errors.append(
                        f"{source.case_id}: blocking invariant failed: citation_validity"
                    )
                generated_cases.append(
                    GenerationCaseArtifact(
                        case_id=source.case_id,
                        generation=generated,
                        deterministic_scores=deterministic_scores,
                    )
                )
            except Exception as exc:
                message = f"{source.case_id}: {type(exc).__name__}: {exc}"
                errors.append(message)
                generated_cases.append(
                    GenerationCaseArtifact(
                        case_id=source.case_id,
                        generation=None,
                        error=message,
                    )
                )

        draft = GenerationRun(
            run_id=run_id,
            retrieval_run_fingerprint=retrieval.run_fingerprint,
            configuration=self.runtime_configuration,
            cases=generated_cases,
            run_fingerprint="",
        )
        generation = draft.model_copy(
            update={"run_fingerprint": artifact_fingerprint(draft)}
        )
        semantic_scores: dict[str, dict[str, float | None]] = {}
        if request.run_ragas:
            if self.semantic_judge is None:
                errors.append("Ragas requested but semantic judge is unavailable")
            else:
                batch = self.semantic_judge.score_generation(retrieval, generation)
                semantic_scores = batch.scores
                errors.extend(
                    f"{case_id}: {message}"
                    for case_id, messages in batch.errors.items()
                    for message in messages
                )
        self.repository.save_generation(generation)
        successful_ids = {
            item.case_id for item in generation.cases if item.generation is not None
        }
        aggregates = segment_aggregates(
            [case for case in dataset.cases if case.id in successful_ids],
            [
                item.deterministic_scores | semantic_scores.get(item.case_id, {})
                for item in generation.cases
                if item.generation is not None
            ],
        )
        case_scores = {
            item.case_id: item.deterministic_scores | semantic_scores.get(item.case_id, {})
            for item in generation.cases
        }
        status = "complete" if not errors else "incomplete"
        return EvaluationReport(
            run_id=run_id,
            mode=request.mode,
            status=status,
            dataset_size=len(dataset.cases),
            evaluated_cases=len(retrieval.cases),
            validation=validation.model_dump(mode="json"),
            aggregates=aggregates,
            target_comparison=compare_to_target(aggregates),
            case_scores=case_scores,
            errors=errors,
            artifact_ids={
                "retrieval_run": retrieval.run_fingerprint,
                "generation_run": generation.run_fingerprint,
            },
            baseline_eligible=False,
        )

    def _run_e2e(
        self,
        request: EvaluationRequest,
        dataset: GoldenDataset,
        selected: list[GoldenCase],
        validation: GoldenValidationReport,
        run_id: str,
    ) -> EvaluationReport:
        if request.ingestion_source is not None:
            _document, chunks = self._ingest_source(request)
            validation = validate_golden_dataset(
                dataset,
                request.canonical_source,
                chunks=chunks,
                audit_root=request.golden_dir.parent,
            )
            if validation.errors:
                raise ValueError("; ".join(issue.message for issue in validation.errors))
        retrieval_report = self._retrieval_report(
            request,
            dataset,
            selected,
            validation,
            run_id,
        )
        generation_request = request.model_copy(
            update={"mode": EvaluationMode.GENERATION, "from_run": run_id}
        )
        generation_report = self._generation_report(
            generation_request,
            dataset,
            validation,
            run_id,
        )
        errors = retrieval_report.errors + generation_report.errors
        status = "complete" if not errors else "incomplete"
        baseline_eligible = (
            status == "complete"
            and request.baseline_candidate
            and validation.full_conformance
            and len(selected) == 100
        )
        return self._finish_report(
            EvaluationReport(
                run_id=run_id,
                mode=EvaluationMode.E2E,
                status=status,
                dataset_size=len(dataset.cases),
                evaluated_cases=len(selected),
                validation=validation.model_dump(mode="json"),
                aggregates={
                    "retrieval": retrieval_report.aggregates,
                    "generation": generation_report.aggregates,
                },
                target_comparison={
                    "retrieval": retrieval_report.target_comparison,
                    "generation": generation_report.target_comparison,
                },
                case_scores={
                    case_id: retrieval_report.case_scores.get(case_id, {})
                    | generation_report.case_scores.get(case_id, {})
                    for case_id in (
                        retrieval_report.case_scores.keys()
                        | generation_report.case_scores.keys()
                    )
                },
                errors=errors,
                artifact_ids=retrieval_report.artifact_ids | generation_report.artifact_ids,
                baseline_eligible=baseline_eligible,
            )
        )
```

Per-case exceptions remain in their phase artifacts and remaining cases continue. A requested Ragas failure or missing score produces `status="incomplete"`; a score below `0.85` is stored and reported without changing status.

- [ ] **Step 7: Run staged runner tests and commit**

Delete `tests/unit/evaluation/test_scoring.py` only after Task 1's finalized-schema tests and Task 7's retrieval/citation/abstention metric tests pass; those are the direct replacements for its legacy `GoldenCase` and `score_response` coverage.

Run:

```powershell
rtk proxy uv run pytest -p no:cacheprovider tests/unit/evaluation/test_runner.py tests/unit/evaluation/test_golden.py tests/unit/evaluation/test_validation.py tests/unit/evaluation/test_metrics.py tests/unit/generation/test_execution.py -q
rtk ruff check src/evaluation/runner.py tests/unit/evaluation/test_runner.py
```

Expected: all focused tests PASS.

Commit:

```powershell
rtk git add src/evaluation/runner.py tests/unit/evaluation/test_scoring.py tests/unit/evaluation/test_runner.py
rtk git commit -m "feat: orchestrate staged offline evaluation"
```

---

### Task 9: Ragas v0.4 Report-Only Judge Adapter

**Files:**
- Create: `src/evaluation/ragas_adapter.py`
- Create: `tests/unit/evaluation/test_ragas.py`
- Modify: `src/settings.py`
- Modify: `.env.example`
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Modify: `tests/unit/test_settings.py`

**Interfaces:**
- Consumes: `RetrievalRun`, `GenerationRun`, and OpenAI-compatible judge settings.
- Produces: concrete `RagasJudge.score_retrieval(run: RetrievalRun) -> SemanticScoreBatch` and `score_generation(retrieval: RetrievalRun, generation: GenerationRun) -> SemanticScoreBatch` satisfying Task 8's `SemanticJudge` port.

- [ ] **Step 1: Write failing adapter mapping and metric-routing tests**

```python
# tests/unit/evaluation/test_ragas.py
from types import SimpleNamespace

from evaluation.ragas_adapter import RagasJudge
from tests.support.evaluation_fakes import make_generation_run, make_retrieval_run


class FakeMetric:
    def __init__(self, value: float) -> None:
        self.value = value
        self.calls: list[dict[str, object]] = []

    async def ascore(self, **kwargs: object) -> SimpleNamespace:
        self.calls.append(kwargs)
        return SimpleNamespace(value=self.value)


def _judge(**overrides: FakeMetric) -> RagasJudge:
    metrics = {
        "context_precision": FakeMetric(0.91),
        "context_recall": FakeMetric(0.82),
        "faithfulness": FakeMetric(0.73),
        "answer_relevancy": FakeMetric(0.64),
    }
    metrics.update(overrides)
    return RagasJudge.from_metrics(max_concurrency=2, **metrics)


def test_retrieval_scores_only_context_metrics() -> None:
    judge = _judge()

    batch = judge.score_retrieval(make_retrieval_run())

    assert batch.scores["DL-001"] == {"context_precision": 0.91, "context_recall": 0.82}
    assert batch.errors == {}


def test_generation_uses_saved_contexts_answer_and_reference() -> None:
    faithfulness = FakeMetric(0.9)
    relevancy = FakeMetric(0.8)
    judge = _judge(faithfulness=faithfulness, answer_relevancy=relevancy)
    retrieval = make_retrieval_run()

    batch = judge.score_generation(retrieval, make_generation_run(retrieval=retrieval))

    assert batch.scores["DL-001"] == {"faithfulness": 0.9, "answer_relevancy": 0.8}
    assert faithfulness.calls[0]["retrieved_contexts"] == ["retrieved original text"]
    assert relevancy.calls[0]["user_input"] == "golden question"
```

- [ ] **Step 2: Pin Ragas and refresh the lock file**

Keep the Ragas minor-series constraint and add `<0.4` only as a resolver probe:

```toml
eval = ["ragas>=0.4,<0.5", "langchain-community<0.4"]
```

Run:

```powershell
rtk proxy uv lock
rtk proxy uv sync --group dev --group eval
rtk proxy uv run --group eval python -c "import ragas.metrics.collections"
$resolvedLangchainCommunity = rtk proxy uv run --group eval python -c "from importlib.metadata import version; print(version('langchain-community'))"
if (-not $resolvedLangchainCommunity) { throw "langchain-community did not resolve" }
rtk proxy uv add --group eval "langchain-community==$resolvedLangchainCommunity"
rtk proxy uv lock
rtk proxy uv sync --group dev --group eval
rtk proxy uv run --group eval python -c "from importlib.metadata import version; import ragas.metrics.collections; print(version('ragas'), version('langchain-community'))"
```

Expected: the probe import must pass before its installed 0.3.x version is captured. The committed `pyproject.toml` and `uv.lock` contain `ragas>=0.4,<0.5` plus the exact equality constraint emitted from `$resolvedLangchainCommunity`; the final import/version command passes. Do not commit the unproven `<0.4` probe constraint and do not hard-code `<0.4` as if the review proved compatibility.

- [ ] **Step 3: Add explicit OpenAI-compatible judge settings**

```python
# src/settings.py
ragas_api_key: str = ""
ragas_base_url: str = "https://api.openai.com/v1"
ragas_model: str = "gpt-4.1-mini"
ragas_embedding_model: str = "text-embedding-3-small"
ragas_max_concurrency: int = Field(default=2, ge=1, le=16)
```

Add these exact entries to `.env.example`:

```dotenv
# Offline Ragas judge; used only when rag-eval receives --ragas.
RAGAS_API_KEY=
RAGAS_BASE_URL=https://api.openai.com/v1
RAGAS_MODEL=gpt-4.1-mini
RAGAS_EMBEDDING_MODEL=text-embedding-3-small
RAGAS_MAX_CONCURRENCY=2
```

The adapter may fall back to `OPENAI_API_KEY` only when `RAGAS_API_KEY` is empty; it must never print either value.

Add a settings regression test:

```python
# append to tests/unit/test_settings.py
def test_ragas_settings_are_explicit_and_bounded() -> None:
    settings = Settings(
        ragas_api_key="judge-key",
        ragas_base_url="https://judge.example/v1",
        ragas_model="judge-model",
        ragas_embedding_model="judge-embedding",
        ragas_max_concurrency=3,
    )

    assert settings.ragas_model == "judge-model"
    assert settings.ragas_embedding_model == "judge-embedding"
    assert settings.ragas_max_concurrency == 3
```

- [ ] **Step 4: Implement the v0.4 collections metrics adapter**

```python
# src/evaluation/ragas_adapter.py
from __future__ import annotations

import asyncio
from typing import Any

from openai import AsyncOpenAI
from ragas.embeddings.base import embedding_factory
from ragas.llms import llm_factory
from ragas.metrics.collections import AnswerRelevancy, ContextPrecision, ContextRecall, Faithfulness

from evaluation.artifacts import GenerationRun, RetrievalRun, SemanticScoreBatch


class RagasJudge:
    def __init__(
        self,
        context_precision: Any,
        context_recall: Any,
        faithfulness: Any,
        answer_relevancy: Any,
        *,
        max_concurrency: int,
    ) -> None:
        self.context_precision = context_precision
        self.context_recall = context_recall
        self.faithfulness = faithfulness
        self.answer_relevancy = answer_relevancy
        self.max_concurrency = max_concurrency

    @classmethod
    def from_settings(cls, settings: Any) -> "RagasJudge":
        api_key = settings.ragas_api_key or settings.openai_api_key
        if not api_key:
            raise ValueError("RAGAS_API_KEY or OPENAI_API_KEY is required for semantic evaluation")
        client = AsyncOpenAI(api_key=api_key, base_url=settings.ragas_base_url)
        llm = llm_factory(settings.ragas_model, client=client)
        embeddings = embedding_factory(
            "openai",
            model=settings.ragas_embedding_model,
            client=client,
        )
        return cls(
            ContextPrecision(llm=llm),
            ContextRecall(llm=llm),
            Faithfulness(llm=llm),
            AnswerRelevancy(llm=llm, embeddings=embeddings),
            max_concurrency=settings.ragas_max_concurrency,
        )

    @classmethod
    def from_metrics(
        cls,
        context_precision: Any,
        context_recall: Any,
        faithfulness: Any,
        answer_relevancy: Any,
        *,
        max_concurrency: int,
    ) -> "RagasJudge":
        return cls(
            context_precision,
            context_recall,
            faithfulness,
            answer_relevancy,
            max_concurrency=max_concurrency,
        )

    def score_retrieval(self, run: RetrievalRun) -> SemanticScoreBatch:
        return asyncio.run(self._score_retrieval(run))

    def score_generation(
        self,
        retrieval: RetrievalRun,
        generation: GenerationRun,
    ) -> SemanticScoreBatch:
        return asyncio.run(self._score_generation(retrieval, generation))
```

Add the concrete async implementation; it only reads captured evidence:

```python
    async def _metric_value(self, metric: Any, **kwargs: object) -> float:
        result = await metric.ascore(**kwargs)
        return float(result.value)

    async def _score_retrieval(self, run: RetrievalRun) -> SemanticScoreBatch:
        semaphore = asyncio.Semaphore(self.max_concurrency)

        async def score_case(case: Any) -> tuple[str, dict[str, float | None], list[str]]:
            if case.retrieval is None:
                return case.case_id, {"context_precision": None, "context_recall": None}, ["retrieval missing"]
            contexts = [item.hit.chunk.text for item in case.retrieval.hits]
            values: dict[str, float | None] = {}
            errors: list[str] = []
            async with semaphore:
                for name, metric in (
                    ("context_precision", self.context_precision),
                    ("context_recall", self.context_recall),
                ):
                    try:
                        values[name] = await self._metric_value(
                            metric,
                            user_input=case.retrieval.question,
                            reference=case.expected_answer,
                            retrieved_contexts=contexts,
                        )
                    except Exception as exc:
                        values[name] = None
                        errors.append(f"{name}: {type(exc).__name__}")
            return case.case_id, values, errors

        results = await asyncio.gather(*(score_case(case) for case in run.cases))
        return SemanticScoreBatch(
            scores={case_id: values for case_id, values, _ in results},
            errors={case_id: errors for case_id, _, errors in results if errors},
        )

    async def _score_generation(
        self,
        retrieval: RetrievalRun,
        generation: GenerationRun,
    ) -> SemanticScoreBatch:
        retrieval_by_id = {case.case_id: case for case in retrieval.cases}
        semaphore = asyncio.Semaphore(self.max_concurrency)

        async def score_case(case: Any) -> tuple[str, dict[str, float | None], list[str]]:
            source = retrieval_by_id[case.case_id]
            if source.retrieval is None:
                return case.case_id, {"faithfulness": None, "answer_relevancy": None}, ["retrieval missing"]
            contexts = [item.hit.chunk.text for item in source.retrieval.hits]
            values: dict[str, float | None] = {}
            errors: list[str] = []
            if case.generation is None:
                return case.case_id, {"faithfulness": None, "answer_relevancy": None}, ["generation missing"]
            async with semaphore:
                calls = (
                    (
                        "faithfulness",
                        self.faithfulness,
                        {
                            "user_input": source.retrieval.question,
                            "response": case.generation.answer,
                            "retrieved_contexts": contexts,
                        },
                    ),
                    (
                        "answer_relevancy",
                        self.answer_relevancy,
                        {
                            "user_input": source.retrieval.question,
                            "response": case.generation.answer,
                        },
                    ),
                )
                for name, metric, kwargs in calls:
                    try:
                        values[name] = await self._metric_value(metric, **kwargs)
                    except Exception as exc:
                        values[name] = None
                        errors.append(f"{name}: {type(exc).__name__}")
            return case.case_id, values, errors

        results = await asyncio.gather(*(score_case(case) for case in generation.cases))
        return SemanticScoreBatch(
            scores={case_id: values for case_id, values, _ in results},
            errors={case_id: errors for case_id, _, errors in results if errors},
        )
```

Ragas v0.4 collections metrics use `ascore(**kwargs)`; `AnswerRelevancy` requires both `llm` and `embeddings`. Do not call the application pipeline from this adapter.

- [ ] **Step 5: Run adapter tests with the eval dependency group**

Run:

```powershell
rtk proxy uv run --group eval pytest -p no:cacheprovider tests/unit/evaluation/test_ragas.py tests/unit/evaluation/test_runner.py tests/unit/test_settings.py -q
rtk ruff check src/evaluation/ragas_adapter.py tests/unit/evaluation/test_ragas.py
```

Expected: all tests PASS without network calls because tests inject fake metrics.

- [ ] **Step 6: Commit the judge adapter**

```powershell
rtk git add pyproject.toml uv.lock src/settings.py .env.example src/evaluation/ragas_adapter.py tests/unit/evaluation/test_ragas.py tests/unit/test_settings.py
rtk git commit -m "feat: add report-only ragas evaluation"
```

---

### Task 10: `rag-eval` CLI and Approved Selection Contract

**Files:**
- Create: `src/evaluation/cli.py`
- Create: `tests/component/api/test_evaluation_cli.py`
- Modify: `src/cli.py`
- Modify: `pyproject.toml`
- Modify: `tests/component/api/test_cli.py`

**Interfaces:**
- Consumes: `EvaluationRequest`, `EvaluationRunner`, application state, `LocalRunRepository`, and `RagasJudge`.
- Produces: `rag-eval validate|ingest|retrieval|generation|e2e` with type/file/case/limit and opt-in ingestion flags.

- [ ] **Step 1: Write failing parser and lazy-runtime tests**

```python
# tests/component/api/test_evaluation_cli.py
from pathlib import Path

import pytest

from evaluation.cli import CliRuntime, parse_request, run_cli
from evaluation.artifacts import EvaluationMode, EvaluationReport, EvaluationRequest
from evaluation.golden import GoldenType


class CompleteValidationRunner:
    def run(self, request: EvaluationRequest) -> EvaluationReport:
        return EvaluationReport(
            run_id="validate-1",
            mode=request.mode,
            status="complete",
            dataset_size=100,
            evaluated_cases=0,
            validation={},
            aggregates={},
            errors=[],
            artifact_ids={},
            baseline_eligible=False,
            report_path=Path("reports/rag_evaluation/validate-1/report.json"),
        )


def _validation_runner_factory():
    return lambda request, settings, repository: CliRuntime(
        runner=CompleteValidationRunner(),
        flush=None,
    )


def test_type_and_limit_map_to_request() -> None:
    request = parse_request(["retrieval", "--type", "multi_hop", "--limit", "10"])
    assert request.mode is EvaluationMode.RETRIEVAL
    assert request.question_types == {GoldenType.MULTI_HOP}
    assert request.limit == 10


def test_type_and_explicit_file_are_mutually_exclusive() -> None:
    with pytest.raises(SystemExit):
        parse_request([
            "retrieval",
            "--type", "multi_hop",
            "--golden-file", "evaluation/experiment.json",
        ])


def test_force_requires_ingestion_source() -> None:
    with pytest.raises(SystemExit):
        parse_request(["e2e", "--force-reingest"])


def test_ragas_is_explicit_opt_in() -> None:
    without_judge = parse_request(["e2e", "--limit", "5"])
    with_judge = parse_request(["e2e", "--limit", "5", "--ragas"])

    assert without_judge.run_ragas is False
    assert with_judge.run_ragas is True


def test_output_root_is_a_subcommand_option() -> None:
    request = parse_request(["retrieval", "--output-root", "tmp/eval"])
    assert request.output_root == Path("tmp/eval")


def test_generation_rejects_new_selection_flags() -> None:
    with pytest.raises(SystemExit):
        parse_request(["generation", "--from-run", "retrieval-1", "--type", "multi_hop"])


def test_generation_parser_omits_inherited_selection_fields() -> None:
    request = parse_request(["generation", "--from-run", "retrieval-1"])

    assert request.mode is EvaluationMode.GENERATION
    assert request.from_run == "retrieval-1"


def test_validate_rejects_limit_because_standard_validation_is_always_full() -> None:
    with pytest.raises(SystemExit):
        parse_request(["validate", "--limit", "1"])


def test_validate_does_not_create_fastapi_runtime(monkeypatch) -> None:
    monkeypatch.setattr("evaluation.cli.create_app", lambda settings: (_ for _ in ()).throw(AssertionError("runtime created")))
    assert run_cli(["validate"], runner_factory=_validation_runner_factory()) == 0
```

- [ ] **Step 2: Run tests and confirm the CLI module is absent**

Run:

```powershell
rtk proxy uv run pytest -p no:cacheprovider tests/component/api/test_evaluation_cli.py -q
```

Expected: FAIL during import.

- [ ] **Step 3: Implement subparsers and shared selection flags**

```python
# src/evaluation/cli.py
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from api.app import create_app
from evaluation.artifacts import EvaluationMode, EvaluationRequest
from evaluation.golden import GoldenType


def _add_selection(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--golden-dir", type=Path, default=Path("evaluation/golden_set"))
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--type", action="append", choices=[item.value for item in GoldenType], default=[])
    group.add_argument("--golden-file", action="append", type=Path, default=[])
    parser.add_argument("--case-id", action="append", default=[])
    parser.add_argument("--limit", type=int)
    parser.add_argument("--canonical-source", type=Path, default=Path("data/extracted/01_2021_ND-CP_283247.md"))


def _add_validation_scope(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--golden-dir", type=Path, default=Path("evaluation/golden_set"))
    parser.add_argument("--golden-file", action="append", type=Path, default=[])
    parser.add_argument(
        "--canonical-source",
        type=Path,
        default=Path("data/extracted/01_2021_ND-CP_283247.md"),
    )


def _add_output(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("reports/rag_evaluation"),
    )


def _add_ragas(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--ragas",
        action="store_true",
        help="Run report-only Ragas metrics using captured evidence",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rag-eval", description="Run staged offline RAG evaluation")
    subparsers = parser.add_subparsers(dest="mode", required=True)
    validate = subparsers.add_parser("validate")
    _add_validation_scope(validate)
    _add_output(validate)
    retrieval = subparsers.add_parser("retrieval")
    _add_selection(retrieval)
    _add_ragas(retrieval)
    _add_output(retrieval)
    ingest = subparsers.add_parser("ingest")
    ingest.add_argument("--source", required=True, type=Path)
    ingest.add_argument("--canonical-source", type=Path, default=Path("data/extracted/01_2021_ND-CP_283247.md"))
    ingest.add_argument("--force-reingest", action="store_true")
    _add_output(ingest)
    generation = subparsers.add_parser("generation")
    generation.add_argument("--from-run", required=True)
    _add_ragas(generation)
    _add_output(generation)
    e2e = subparsers.add_parser("e2e")
    _add_selection(e2e)
    e2e.add_argument("--ingest", type=Path)
    e2e.add_argument("--force-reingest", action="store_true")
    _add_ragas(e2e)
    _add_output(e2e)
    return parser
```

The exact contract is that `--output-root` appears **after** the subcommand, like every other mode option. Do not duplicate it on the root parser. Map parsed values with:

```python
def parse_request(argv: Sequence[str]) -> EvaluationRequest:
    parser = build_parser()
    values = vars(parser.parse_args(list(argv)))
    mode = EvaluationMode(values.pop("mode"))
    source = values.pop("source", None)
    e2e_ingest = values.pop("ingest", None)
    question_types = {
        GoldenType(value) for value in values.pop("type", [])
    }
    golden_files = values.pop("golden_file", [])
    case_ids = set(values.pop("case_id", []))
    request_values = {
        "mode": mode,
        "ingestion_source": source or e2e_ingest,
        "run_ragas": values.pop("ragas", False),
        **values,
    }
    if mode is not EvaluationMode.GENERATION:
        request_values.update(
            golden_files=golden_files,
            question_types=question_types,
            case_ids=case_ids,
        )
    try:
        return EvaluationRequest(**request_values)
    except ValidationError as exc:
        parser.error(str(exc))
        raise AssertionError("argparse.error always exits")
```

Import `ValidationError`. Pydantic rejects `--force-reingest` without `--source`/`--ingest` before application state is built. Generation exposes no type/file/case/limit flags because it inherits the saved `RetrievalRun` dataset and selection.

- [ ] **Step 4: Implement runner construction and exit behavior**

Implement the CLI adapter with explicit lazy runtime construction:

```python
# append to src/evaluation/cli.py
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass

from evaluation.repository import LocalRunRepository, RunRepository
from evaluation.runner import EvaluationRunner
from settings import Settings


@dataclass(frozen=True)
class CliRuntime:
    runner: EvaluationRunner
    flush: Callable[[], None] | None


RunnerFactory = Callable[
    [EvaluationRequest, Settings, RunRepository],
    CliRuntime,
]


def _runtime_configuration(settings: Settings) -> dict[str, object]:
    return {
        "qdrant_collection": settings.qdrant_collection,
        "embedding_model": settings.embedding_model,
        "reranker_model": settings.reranker_model,
        "retrieval_limit": settings.retrieval_limit,
        "lexical_candidate_limit": settings.lexical_candidate_limit,
        "min_dense_score": settings.min_dense_score,
        "enable_enrichment": settings.enable_enrichment,
        "generation_provider": settings.main_provider.value,
    }


def _build_runtime(
    request: EvaluationRequest,
    settings: Settings,
    repository: RunRepository,
) -> CliRuntime:
    if request.mode is EvaluationMode.VALIDATE:
        return CliRuntime(
            runner=EvaluationRunner(
                ingestion=None,
                registry=None,
                store=None,
                chat=None,
                repository=repository,
                runtime_configuration=_runtime_configuration(settings),
                semantic_judge=None,
            ),
            flush=None,
        )
    app = create_app(settings)
    judge = None
    if request.run_ragas:
        from evaluation.ragas_adapter import RagasJudge

        judge = RagasJudge.from_settings(settings)
    return CliRuntime(
        runner=EvaluationRunner(
            ingestion=app.state.ingestion,
            registry=app.state.registry,
            store=app.state.store,
            chat=app.state.chat,
            repository=repository,
            runtime_configuration=_runtime_configuration(settings),
            semantic_judge=judge,
        ),
        flush=app.state.tracer.flush,
    )


def run_cli(
    argv: Sequence[str] | None = None,
    *,
    runner_factory: RunnerFactory | None = None,
) -> int:
    request = parse_request(list(argv) if argv is not None else sys.argv[1:])
    settings = Settings()
    repository = LocalRunRepository(request.output_root)
    factory = runner_factory or _build_runtime
    runtime: CliRuntime | None = None
    report: EvaluationReport | None = None
    failure: Exception | None = None
    try:
        runtime = factory(request, settings, repository)
        report = runtime.runner.run(request)
    except Exception as exc:
        failure = exc
    finally:
        if runtime is not None and runtime.flush is not None:
            try:
                runtime.flush()
            except Exception as flush_exc:
                if failure is None:
                    failure = flush_exc
    if failure is not None:
        print(f"rag-eval failed: {type(failure).__name__}: {failure}", file=sys.stderr)
        return 1
    assert report is not None
    print(f"report: {report.report_path}")
    print(json.dumps(report.aggregates, ensure_ascii=False, sort_keys=True))
    return 0 if report.status == "complete" else 1
```

This creates no FastAPI runtime for `validate`, builds `RagasJudge` only when `--ragas` is present, flushes runtime tracing once, and never prints settings or credential values.

- [ ] **Step 5: Replace the console entrypoint and remove the obsolete function**

Change `pyproject.toml`:

```toml
[project.scripts]
company-rag-serve = "cli:serve"
company-rag-ingest = "cli:ingest"
rag-eval = "evaluation.cli:main"
```

Remove `evaluate()` and its legacy imports from `src/cli.py`. Keep existing serve/ingest behavior and tests unchanged. Add:

```python
def main() -> None:
    raise SystemExit(run_cli())
```

Refresh the lock/install metadata if required:

```powershell
rtk proxy uv lock
```

- [ ] **Step 6: Run CLI tests and command help**

Run:

```powershell
rtk proxy uv run pytest -p no:cacheprovider tests/component/api/test_evaluation_cli.py tests/component/api/test_cli.py -q
rtk proxy uv run rag-eval --help
rtk proxy uv run rag-eval retrieval --help
```

Expected: tests PASS; help lists all five subcommands and approved selection flags.

- [ ] **Step 7: Commit the CLI**

```powershell
rtk git add pyproject.toml uv.lock src/cli.py src/evaluation/cli.py tests/component/api/test_cli.py tests/component/api/test_evaluation_cli.py
rtk git commit -m "feat: add staged rag-eval cli"
```

---

### Task 11: Documentation, Full Verification, and Optional Smoke Command

**Files:**
- Modify: `README.md`
- Modify: `docs/architectures/01-system-context.md`
- Modify: `docs/architectures/02-document-loading-and-ingestion.md`
- Modify: `docs/architectures/04-retrieval-generation-and-citations.md`
- Modify: `docs/architectures/05-observability-evaluation-and-operations.md`
- Modify if needed: `RAG-ARCHITECTURE.md`

**Interfaces:**
- Consumes: all implemented commands and contracts.
- Produces: accurate operator/developer documentation and final regression evidence.

- [ ] **Step 1: Update all command and lifecycle documentation**

Replace every `company-rag-evaluate` and monolithic `evaluation/golden_set.json` example with the approved `rag-eval` commands. Document:

```powershell
rag-eval validate
rag-eval ingest --source data/raw/01_2021_ND-CP_283247.docx
rag-eval retrieval --type multi_hop --limit 10
rag-eval generation --from-run <retrieval-run-id>
rag-eval e2e --limit 10
rag-eval e2e --limit 10 --ragas
rag-eval e2e --ingest data/raw/01_2021_ND-CP_283247.docx --limit 10
```

Explain raw-versus-canonical sources, deterministic coordinates, opt-in/idempotent ingestion, phase replay, type/file/case/limit selection, artifact locations, baseline eligibility, and that report-only Ragas scores run only with `--ragas`.

- [ ] **Step 2: Run the complete offline test suite**

Run:

```powershell
rtk proxy uv run --group eval pytest -p no:cacheprovider tests -q
```

Expected: all tests PASS, including the local raw-DOCX recoverability guard; no paid or network model call occurs.

- [ ] **Step 3: Run static checks**

Run:

```powershell
rtk ruff check src tests
rtk mypy
rtk git diff --check
```

Expected: Ruff, mypy, and whitespace checks report no errors.

- [ ] **Step 4: Run deterministic CLI verification**

Run:

```powershell
rtk proxy uv run rag-eval validate
```

Expected: the reissued 100-case/130-context schema and grounding checks pass; both audit artifacts are content/hash validated, full conformance is true, and validate mode remains baseline-ineligible because only a complete full e2e run can establish a baseline.

- [ ] **Step 5: Run the external smoke only when credentials and Qdrant are available**

Run:

```powershell
rtk proxy uv run --group eval rag-eval e2e --ingest data/raw/01_2021_ND-CP_283247.docx --limit 5 --ragas
```

Expected when dependencies are configured: one case per type is selected, raw DOCX ingestion is idempotent, retrieval/generation execute once per selected case, Ragas scores are written, and `baseline_eligible=false` because the run is limited. If dependencies are unavailable, do not infer success; record the exact missing dependency/credential as an unverified optional check.

- [ ] **Step 6: Review the final diff and commit documentation**

Run:

```powershell
rtk git status --short
rtk git diff --stat
rtk git diff --check
```

Confirm the user's unrelated deleted legacy scripts remain untouched and unstaged.

Commit:

```powershell
rtk git add README.md RAG-ARCHITECTURE.md docs/architectures/01-system-context.md docs/architectures/02-document-loading-and-ingestion.md docs/architectures/04-retrieval-generation-and-citations.md docs/architectures/05-observability-evaluation-and-operations.md
rtk git commit -m "docs: document staged rag evaluation lifecycle"
```

---

## Final Review Checklist

- [ ] `rag-eval validate` reads all five finalized files and never touches runtime providers.
- [ ] Raw DOCX parsing and chunking preserve every answerable golden excerpt and its exact canonical coordinates.
- [ ] Qdrant and memory stores round-trip coordinates and expose compatible snapshot inspection.
- [ ] Public `ChatResponse` and citation-gated abstention remain unchanged.
- [ ] Retrieval and generation artifacts carry stable fingerprints and reject incompatible replay.
- [ ] `--type`, `--golden-file`, `--case-id`, and `--limit` follow approved precedence.
- [ ] E2e ingestion is opt-in; unchanged documents are hash-skipped; force requires an explicit source.
- [ ] Ragas v0.4 scores only captured evidence and never reruns the application pipeline.
- [ ] Scores below `0.85` are report-only; requested execution failures make the run incomplete.
- [ ] Only complete, full 100-case e2e runs with content/hash-valid audit artifacts can become baseline eligible.
- [ ] Default tests require no network or paid judge calls.
- [ ] Reports are ignored by Git and preserve provenance without exposing secrets.
