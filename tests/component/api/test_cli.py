from __future__ import annotations

from types import SimpleNamespace

import pytest

import cli
from tests.support.tracing import RecordingTracer


class RecordingIngestion:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error

    def ingest_bytes(self, filename: str, content: bytes) -> SimpleNamespace:
        if self.error is not None:
            raise self.error
        return SimpleNamespace(source_name=filename, status="ready", version=1, id="doc-1")


def _app(ingestion: RecordingIngestion, tracer: RecordingTracer) -> SimpleNamespace:
    return SimpleNamespace(state=SimpleNamespace(ingestion=ingestion, tracer=tracer))


def test_ingest_flushes_tracer_after_success(tmp_path, monkeypatch) -> None:
    seed = tmp_path / "policy.md"
    seed.write_text("Policy text", encoding="utf-8")
    tracer = RecordingTracer()
    monkeypatch.setattr(cli, "Settings", lambda: object())
    monkeypatch.setattr(cli, "create_app", lambda settings: _app(RecordingIngestion(), tracer))
    monkeypatch.setattr("sys.argv", ["company-rag-ingest", str(seed)])

    cli.ingest()

    assert tracer.flush_calls == 1


def test_ingest_flushes_tracer_before_reraising_ingestion_error(tmp_path, monkeypatch) -> None:
    seed = tmp_path / "policy.md"
    seed.write_text("Policy text", encoding="utf-8")
    tracer = RecordingTracer()
    error = RuntimeError("embedding rate limited")
    monkeypatch.setattr(cli, "Settings", lambda: object())
    monkeypatch.setattr(cli, "create_app", lambda settings: _app(RecordingIngestion(error), tracer))
    monkeypatch.setattr("sys.argv", ["company-rag-ingest", str(seed)])

    with pytest.raises(RuntimeError, match="embedding rate limited"):
        cli.ingest()

    assert tracer.flush_calls == 1


def test_ingest_flushes_tracer_when_directory_enumeration_fails(tmp_path, monkeypatch) -> None:
    tracer = RecordingTracer()

    def raise_enumeration_error(path):
        raise OSError("directory unavailable")

    monkeypatch.setattr(cli, "Settings", lambda: object())
    monkeypatch.setattr(cli, "create_app", lambda settings: _app(RecordingIngestion(), tracer))
    monkeypatch.setattr(cli.Path, "iterdir", raise_enumeration_error)
    monkeypatch.setattr("sys.argv", ["company-rag-ingest", str(tmp_path)])

    with pytest.raises(OSError, match="directory unavailable"):
        cli.ingest()

    assert tracer.flush_calls == 1


def test_ingest_preserves_ingestion_error_when_tracer_flush_fails(tmp_path, monkeypatch) -> None:
    seed = tmp_path / "policy.md"
    seed.write_text("Policy text", encoding="utf-8")
    tracer = RecordingTracer(RuntimeError("flush failed"))
    ingestion_error = RuntimeError("embedding rate limited")
    monkeypatch.setattr(cli, "Settings", lambda: object())
    monkeypatch.setattr(cli, "create_app", lambda settings: _app(RecordingIngestion(ingestion_error), tracer))
    monkeypatch.setattr("sys.argv", ["company-rag-ingest", str(seed)])

    with pytest.raises(RuntimeError, match="embedding rate limited"):
        cli.ingest()

    assert tracer.flush_calls == 1
