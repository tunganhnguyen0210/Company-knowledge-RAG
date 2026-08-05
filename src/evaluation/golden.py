from __future__ import annotations

import json
import re
from collections import Counter, deque
from enum import StrEnum
from hashlib import sha256
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from domain.schemas import Chunk
from ingestion.structure import extract_legal_sections


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
    def validate_type_contract(self) -> GoldenCase:
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


class ValidationIssue(BaseModel):
    code: str
    message: str
    case_id: str | None = None


class GoldenValidationReport(BaseModel):
    errors: list[ValidationIssue]
    warnings: list[ValidationIssue]
    validated_cases: int
    full_conformance: bool


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
                errors.append(
                    ValidationIssue(
                        code="context_not_exact_source",
                        message="context is not an exact canonical substring",
                        case_id=case.id,
                    )
                )
            elif evidence not in article_text.get(key, ""):
                errors.append(
                    ValidationIssue(
                        code="context_coordinate_mismatch",
                        message=f"context is not inside {metadata.chapter}/{metadata.article}",
                        case_id=case.id,
                    )
                )
            if "..." in evidence or "…" in evidence:
                errors.append(
                    ValidationIssue(
                        code="context_contains_ellipsis",
                        message="context contains a forbidden omission marker",
                        case_id=case.id,
                    )
                )
    if chunks is not None:
        chunk_text: dict[tuple[str, str | None, str | None], str] = {}
        for chunk in sorted(chunks, key=lambda item: item.position):
            key = (chunk.coordinates.doc_id, chunk.coordinates.chapter, chunk.coordinates.article)
            chunk_text[key] = f"{chunk_text.get(key, '')}{chunk.text}"
        for case in dataset.cases:
            for context in case.golden_truth_contexts:
                metadata = context.golden_metadata
                key = (metadata.doc_id, metadata.chapter, metadata.article)
                if _normalized(context.golden_truth_context) not in _normalized(
                    chunk_text.get(key, "")
                ):
                    errors.append(
                        ValidationIssue(
                            code="context_not_recoverable_from_chunks",
                            message="context is not recoverable from ordered article chunks",
                            case_id=case.id,
                        )
                    )
    migration_path = audit_root / "id_migration_map.json"
    review_path = audit_root / "golden_set_grounding_review.json"
    expected_migration = {
        "schema_version": 1,
        "migration_commit": "f97292a",
        "old_to_new": {
            "1": "DL-001",
            "5": "DL-002",
            "7": "DL-003",
            "9": "DL-004",
            "13": "DL-005",
            "17": "DL-006",
            "21": "DL-007",
            "25": "DL-008",
            "29": "DL-009",
            "33": "DL-010",
            "37": "DL-011",
            "41": "DL-012",
            "45": "DL-013",
            "49": "DL-014",
            "53": "DL-015",
            "57": "DL-016",
            "61": "DL-017",
            "65": None,
            "69": "DL-018",
            "73": "DL-019",
            "77": "DL-020",
        },
        "retired": [
            {
                "old_id": "65",
                "status": "retired",
                "reason": (
                    "The question asks for a number of days while Article 35 defines "
                    "the filing-time event, so it is not a sound direct lookup."
                ),
            }
        ],
    }
    if not migration_path.exists():
        warnings.append(
            ValidationIssue(
                code="missing_id_migration_map",
                message=f"missing audit artifact: {migration_path.name}",
            )
        )
    else:
        migration = json.loads(migration_path.read_text(encoding="utf-8"))
        if migration != expected_migration:
            warnings.append(
                ValidationIssue(
                    code="invalid_id_migration_map",
                    message=(
                        "ID migration evidence does not match the issued direct-lookup namespace"
                    ),
                )
            )
    if not review_path.exists():
        warnings.append(
            ValidationIssue(
                code="missing_grounding_review",
                message=f"missing audit artifact: {review_path.name}",
            )
        )
    else:
        review = json.loads(review_path.read_text(encoding="utf-8"))
        dataset_bytes = json.dumps(
            [case.model_dump(mode="json") for case in dataset.cases],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        expected_cases = []
        for case in dataset.cases:
            expected_contexts = []
            for context_index, context in enumerate(case.golden_truth_contexts):
                evidence = context.golden_truth_context
                metadata = context.golden_metadata
                key = (metadata.doc_id, metadata.chapter, metadata.article)
                expected_contexts.append(
                    {
                        "context_index": context_index,
                        "context_sha256": sha256(evidence.encode("utf-8")).hexdigest(),
                        "exact_source": evidence in canonical,
                        "coordinate_match": evidence in article_text.get(key, ""),
                    }
                )
            expected_cases.append(
                {
                    "case_id": case.id,
                    "status": (
                        "passed"
                        if all(
                            item["exact_source"] and item["coordinate_match"]
                            for item in expected_contexts
                        )
                        else "failed"
                    ),
                    "contexts": expected_contexts,
                }
            )
        expected_review = {
            "schema_version": 1,
            "canonical_doc_id": canonical_path.name,
            "canonical_sha256": sha256(canonical.encode("utf-8")).hexdigest(),
            "dataset_sha256": sha256(dataset_bytes).hexdigest(),
            "validated_cases": len(dataset.cases),
            "validated_contexts": sum(
                len(case.golden_truth_contexts) for case in dataset.cases
            ),
            "cases": expected_cases,
        }
        if review != expected_review:
            warnings.append(
                ValidationIssue(
                    code="invalid_grounding_review",
                    message=(
                        "grounding review evidence does not match the current canonical source "
                        "and dataset"
                    ),
                )
            )
    return GoldenValidationReport(
        errors=errors,
        warnings=warnings,
        validated_cases=len(dataset.cases),
        full_conformance=not errors and not warnings,
    )


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
