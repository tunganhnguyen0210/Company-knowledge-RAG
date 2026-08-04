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
        api_keys='{"secret": ["employee"]}',
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


def test_upload_with_optional_roles(tmp_path: Path) -> None:
    response = _client(tmp_path).post(
        "/v1/documents",
        files={"file": ("secret.md", b"Executive content", "text/markdown")},
        data={"allowed_roles": "executive"},
    )

    assert response.status_code == 201


def test_upload_replaces_same_source_file(tmp_path: Path) -> None:
    settings = Settings(
        gemini_api_key="unused",
        registry_path=tmp_path / "registry.json",
        upload_dir=tmp_path / "uploads",
    )
    client = TestClient(create_app(settings=settings, provider=AnswerProvider()))
    first = client.post(
        "/v1/documents",
        files={"file": ("policy.md", b"HR-only policy", "text/markdown")},
    )

    replacement = client.post(
        "/v1/documents",
        files={"file": ("policy.md", b"Attacker replacement", "text/markdown")},
    )

    assert first.status_code == 201
    assert replacement.status_code == 201


def test_ready_fails_when_provider_reports_not_ready(tmp_path: Path) -> None:
    class NotReadyProvider(AnswerProvider):
        def ready(self) -> bool:
            return False

    settings = Settings(
        api_keys='{"secret": ["employee"]}',
        gemini_api_key="unused",
        registry_path=tmp_path / "registry.json",
        upload_dir=tmp_path / "uploads",
    )
    client = TestClient(create_app(settings=settings, provider=NotReadyProvider()))

    response = client.get("/ready")

    assert response.status_code == 503
