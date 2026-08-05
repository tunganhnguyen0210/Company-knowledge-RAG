from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from api.app import create_app
from generation.service import GroundedAnswer
from providers.base import GenerationRequest, ProviderError, StructuredResult
from providers.probe import ProbeResult
from settings import Settings


class AnswerProvider:
    name = "stub"
    model = "stub-model"

    def generate_structured(
        self, request: GenerationRequest, response_model: type[Any]
    ) -> StructuredResult[Any]:
        if response_model is ProbeResult:
            return StructuredResult(ProbeResult(status="ready"), "stub", "stub-model")
        answer = GroundedAnswer(answer="Nhân viên được nghỉ 15 ngày [C1].", citations=[1])
        return StructuredResult(answer, "stub", "stub-model")


def _client(tmp_path: Path) -> TestClient:
    settings = Settings(
        gemini_api_key="unused",
        registry_path=tmp_path / "registry.json",
        upload_dir=tmp_path / "uploads",
    )
    return TestClient(create_app(settings=settings, provider=AnswerProvider()))


def test_chat_without_api_key_succeeds(tmp_path: Path) -> None:
    response = _client(tmp_path).post("/v1/chat", json={"question": "Nghỉ phép?"})

    assert response.status_code == 200


def test_health_reports_active_model(tmp_path: Path) -> None:
    response = _client(tmp_path).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "active_model": "stub-model"}


def test_development_docs_endpoint_returns_swagger_ui(tmp_path: Path) -> None:
    response = _client(tmp_path).get("/docs")

    assert response.status_code == 200


def test_upload_then_chat_returns_source_citation(tmp_path: Path) -> None:
    client = _client(tmp_path)
    upload = client.post(
        "/v1/documents",
        files={"file": ("policy.md", b"Nhan vien duoc nghi phep 15 ngay.", "text/markdown")},
    )

    response = client.post("/v1/chat", json={"question": "Nghỉ phép?"})

    assert upload.status_code == 201
    assert response.status_code == 200
    assert response.json()["citations"][0]["source_name"] == "policy.md"


def test_ready_reports_provider_and_store_state(tmp_path: Path) -> None:
    response = _client(tmp_path).get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "probed_model": "stub-model"}


def test_ready_fails_when_the_live_probe_cannot_reach_the_model(tmp_path: Path) -> None:
    class UnreachableProvider(AnswerProvider):
        def generate_structured(
            self, request: GenerationRequest, response_model: type[Any]
        ) -> StructuredResult[Any]:
            raise ProviderError("Error code: 404 - no allowed providers", transient=False)

    settings = Settings(
        gemini_api_key="unused",
        registry_path=tmp_path / "registry.json",
        upload_dir=tmp_path / "uploads",
    )
    client = TestClient(create_app(settings=settings, provider=UnreachableProvider()))

    response = client.get("/ready")

    assert response.status_code == 503
    # A misrouted model passes every local check, so the cause has to reach the caller.
    assert "no allowed providers" in response.json()["detail"]


def test_ready_fails_when_provider_reports_not_ready(tmp_path: Path) -> None:
    class NotReadyProvider(AnswerProvider):
        def ready(self) -> bool:
            return False

    settings = Settings(
        gemini_api_key="unused",
        registry_path=tmp_path / "registry.json",
        upload_dir=tmp_path / "uploads",
    )
    client = TestClient(create_app(settings=settings, provider=NotReadyProvider()))

    response = client.get("/ready")

    assert response.status_code == 503


SECTIONED_MARKDOWN = (
    b"# Chuong I\n\n"
    b"Quy dinh chung cua tai lieu.\n\n"
    b"## Dieu 1. Nghi phep\n\n"
    b"Nhan vien duoc nghi phep 15 ngay mot nam.\n\n"
    b"## Dieu 2. Cong tac phi\n\n"
    b"Cong tac phi duoc thanh toan trong 30 ngay.\n"
)


def test_preview_chunks_returns_every_chunk_without_indexing(tmp_path: Path) -> None:
    client = _client(tmp_path)

    response = client.post(
        "/v1/documents/preview-chunks",
        files={"file": ("policy.md", SECTIONED_MARKDOWN, "text/markdown")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["stats"]["chunk_count"] == len(body["chunks"])
    assert [chunk["section"] for chunk in body["chunks"]] == [
        "Chuong I",
        "Dieu 1. Nghi phep",
        "Dieu 2. Cong tac phi",
    ]
    assert "15 ngay" in body["chunks"][1]["text"]
    # A dry run must not leave the document behind.
    assert client.get("/v1/documents").json() == []


def test_preview_chunks_reports_splits_forced_by_the_character_cap(tmp_path: Path) -> None:
    client = _client(tmp_path)

    response = client.post(
        "/v1/documents/preview-chunks",
        files={"file": ("long.md", ("a" * 900).encode("utf-8"), "text/markdown")},
        data={"max_chars": "300"},
    )

    body = response.json()
    assert body["stats"]["chunk_count"] == 3
    assert body["stats"]["chunks_at_max_chars"] == 3
    assert body["stats"]["chunks_without_section"] == 3


def test_preview_chunks_rejects_an_unsupported_extension(tmp_path: Path) -> None:
    response = _client(tmp_path).post(
        "/v1/documents/preview-chunks",
        files={"file": ("data.csv", b"a,b", "text/csv")},
    )

    assert response.status_code == 415


def test_document_chunks_endpoint_pages_stored_chunks(tmp_path: Path) -> None:
    client = _client(tmp_path)
    document_id = client.post(
        "/v1/documents",
        files={"file": ("policy.md", SECTIONED_MARKDOWN, "text/markdown")},
    ).json()["id"]

    response = client.get(f"/v1/documents/{document_id}/chunks", params={"offset": 1, "limit": 1})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert len(body["chunks"]) == 1
    assert body["chunks"][0]["position"] == 1
    assert body["chunks"][0]["section"] == "Dieu 1. Nghi phep"


def test_document_chunks_endpoint_404s_for_an_unknown_document(tmp_path: Path) -> None:
    response = _client(tmp_path).get("/v1/documents/missing/chunks")

    assert response.status_code == 404


def test_search_endpoint_returns_ranked_chunks_without_calling_the_model(tmp_path: Path) -> None:
    class ExplodingProvider(AnswerProvider):
        def generate_structured(
            self, request: GenerationRequest, response_model: type[Any]
        ) -> StructuredResult[Any]:
            raise AssertionError("retrieval preview must not call the model")

    settings = Settings(
        gemini_api_key="unused",
        registry_path=tmp_path / "registry.json",
        upload_dir=tmp_path / "uploads",
    )
    client = TestClient(create_app(settings=settings, provider=ExplodingProvider()))
    client.post(
        "/v1/documents",
        files={"file": ("policy.md", SECTIONED_MARKDOWN, "text/markdown")},
    )

    response = client.post("/v1/search", json={"query": "nghi phep", "limit": 2})

    assert response.status_code == 200
    body = response.json()
    assert body["result_count"] == 2
    assert [hit["rank"] for hit in body["hits"]] == [1, 2]
    assert "15 ngay" in body["hits"][0]["chunk"]["text"]
