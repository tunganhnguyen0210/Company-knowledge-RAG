from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

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
    if path.exists():
        raise FileExistsError(f"artifact already exists: {path}")
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    if temporary.exists():
        raise FileExistsError(f"temporary artifact already exists: {temporary}")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)
    return path


def _json(model: BaseModel) -> str:
    return json.dumps(model.model_dump(mode="json"), ensure_ascii=False, indent=2)


def _jsonl_body(
    header: dict[str, Any],
    cases: list[dict[str, Any]],
) -> str:
    records: list[dict[str, Any]] = [{"record_type": "header", "value": header}]
    records.extend({"record_type": "case", "value": case} for case in cases)
    return "\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n"


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
        return _atomic_write(
            self._path(snapshot.run_id, "index_snapshot.json"), _json(snapshot)
        )

    def save_retrieval(self, run: RetrievalRun) -> Path:
        header = run.model_dump(mode="json", exclude={"cases"})
        cases = [case.model_dump(mode="json") for case in run.cases]
        body = _jsonl_body(header, cases)
        return _atomic_write(self._path(run.run_id, "retrieval.jsonl"), body)

    def load_retrieval(self, run_id: str) -> RetrievalRun:
        records = [
            json.loads(line)
            for line in self._path(run_id, "retrieval.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
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
        cases = [case.model_dump(mode="json") for case in run.cases]
        body = _jsonl_body(header, cases)
        return _atomic_write(self._path(run.run_id, "generation.jsonl"), body)

    def save_report(self, report: EvaluationReport) -> Path:
        return _atomic_write(self._path(report.run_id, "report.json"), _json(report))


class InMemoryRunRepository:
    def __init__(self) -> None:
        self.manifests: dict[str, RunManifest] = {}
        self.manifest_save_calls = 0
        self.snapshots: dict[str, IndexSnapshot] = {}
        self.snapshot_save_calls = 0
        self.retrieval_runs: dict[str, RetrievalRun] = {}
        self.retrieval_save_calls = 0
        self.generation_runs: dict[str, GenerationRun] = {}
        self.generation_save_calls = 0
        self.reports: dict[str, EvaluationReport] = {}
        self.report_save_calls = 0

    def save_manifest(self, manifest: RunManifest) -> Path:
        if manifest.run_id in self.manifests:
            raise FileExistsError(f"manifest already exists: {manifest.run_id}")
        self.manifests[manifest.run_id] = manifest
        self.manifest_save_calls += 1
        return Path(manifest.run_id) / "manifest.json"

    def load_manifest(self, run_id: str) -> RunManifest:
        try:
            return self.manifests[run_id]
        except KeyError as exc:
            raise FileNotFoundError(f"manifest not found: {run_id}") from exc

    def save_snapshot(self, snapshot: IndexSnapshot) -> Path:
        if snapshot.run_id in self.snapshots:
            raise FileExistsError(f"snapshot already exists: {snapshot.run_id}")
        self.snapshots[snapshot.run_id] = snapshot
        self.snapshot_save_calls += 1
        return Path(snapshot.run_id) / "index_snapshot.json"

    def save_retrieval(self, run: RetrievalRun) -> Path:
        if run.run_id in self.retrieval_runs:
            raise FileExistsError(f"retrieval run already exists: {run.run_id}")
        self.retrieval_runs[run.run_id] = run
        self.retrieval_save_calls += 1
        return Path(run.run_id) / "retrieval.jsonl"

    def load_retrieval(self, run_id: str) -> RetrievalRun:
        try:
            return self.retrieval_runs[run_id]
        except KeyError as exc:
            raise FileNotFoundError(f"retrieval run not found: {run_id}") from exc

    def save_generation(self, run: GenerationRun) -> Path:
        if run.run_id in self.generation_runs:
            raise FileExistsError(f"generation run already exists: {run.run_id}")
        self.generation_runs[run.run_id] = run
        self.generation_save_calls += 1
        return Path(run.run_id) / "generation.jsonl"

    def save_report(self, report: EvaluationReport) -> Path:
        if report.run_id in self.reports:
            raise FileExistsError(f"report already exists: {report.run_id}")
        self.reports[report.run_id] = report
        self.report_save_calls += 1
        return Path(report.run_id) / "report.json"
