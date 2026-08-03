from pathlib import Path

from fastapi.testclient import TestClient

from company_knowledge_rag.api.app import create_app
from company_knowledge_rag.providers.base import GenerationRequest, GenerationResult
from company_knowledge_rag.settings import Settings


class AnswerProvider:
    name = "stub"
    model = "stub-model"

    def generate(self, request: GenerationRequest) -> GenerationResult:
        return GenerationResult("Nhân viên được nghỉ 15 ngày [C1].", "stub", "stub-model")


def _client(tmp_path: Path) -> TestClient:
    settings = Settings(
        api_keys='{"secret": ["employee"]}',
        gemini_api_key="unused",
        registry_path=tmp_path / "registry.json",
        upload_dir=tmp_path / "uploads",
    )
    return TestClient(create_app(settings=settings, provider=AnswerProvider()))


def test_chat_requires_api_key(tmp_path: Path) -> None:
    response = _client(tmp_path).post("/v1/chat", json={"question": "Nghỉ phép?"})

    assert response.status_code == 401


def test_health_reports_active_model(tmp_path: Path) -> None:
    response = _client(tmp_path).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "active_model": "stub-model"}


def test_upload_then_chat_returns_source_citation(tmp_path: Path) -> None:
    client = _client(tmp_path)
    headers = {"X-API-Key": "secret"}
    upload = client.post(
        "/v1/documents",
        headers=headers,
        files={"file": ("policy.md", b"Nhan vien duoc nghi phep 15 ngay.", "text/markdown")},
        data={"allowed_roles": "employee"},
    )

    response = client.post("/v1/chat", headers=headers, json={"question": "Nghỉ phép?"})

    assert upload.status_code == 201
    assert response.status_code == 200
    assert response.json()["citations"][0]["source_name"] == "policy.md"


def test_ready_reports_provider_and_store_state(tmp_path: Path) -> None:
    response = _client(tmp_path).get("/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"


def test_upload_cannot_assign_roles_not_owned_by_caller(tmp_path: Path) -> None:
    response = _client(tmp_path).post(
        "/v1/documents",
        headers={"X-API-Key": "secret"},
        files={"file": ("secret.md", b"Executive content", "text/markdown")},
        data={"allowed_roles": "executive"},
    )

    assert response.status_code == 403


def test_upload_cannot_replace_same_source_owned_by_another_role(tmp_path: Path) -> None:
    settings = Settings(
        api_keys='{"hr-secret": ["hr"], "employee-secret": ["employee"]}',
        gemini_api_key="unused",
        registry_path=tmp_path / "registry.json",
        upload_dir=tmp_path / "uploads",
    )
    client = TestClient(create_app(settings=settings, provider=AnswerProvider()))
    first = client.post(
        "/v1/documents",
        headers={"X-API-Key": "hr-secret"},
        files={"file": ("policy.md", b"HR-only policy", "text/markdown")},
        data={"allowed_roles": "hr"},
    )

    replacement = client.post(
        "/v1/documents",
        headers={"X-API-Key": "employee-secret"},
        files={"file": ("policy.md", b"Attacker replacement", "text/markdown")},
        data={"allowed_roles": "employee"},
    )

    assert first.status_code == 201
    assert replacement.status_code == 403


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
