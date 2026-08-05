from __future__ import annotations

import json
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
