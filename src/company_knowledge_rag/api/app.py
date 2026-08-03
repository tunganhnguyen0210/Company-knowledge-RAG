from __future__ import annotations

import json
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile, status
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse
from starlette.concurrency import run_in_threadpool

from company_knowledge_rag.api.auth import require_principal
from company_knowledge_rag.domain.schemas import ChatRequest, ChatResponse, Document, Principal
from company_knowledge_rag.generation.service import ChatService
from company_knowledge_rag.ingestion.enrichment import LLMChunkEnricher
from company_knowledge_rag.ingestion.parser import UnsupportedDocumentError
from company_knowledge_rag.ingestion.service import IngestionService
from company_knowledge_rag.observability.tracing import Tracer
from company_knowledge_rag.providers.base import GenerationProvider, ProviderError
from company_knowledge_rag.providers.gemini import GeminiEmbeddingProvider, GeminiProvider
from company_knowledge_rag.providers.openai import OpenAIProvider
from company_knowledge_rag.providers.openrouter import OpenRouterProvider
from company_knowledge_rag.providers.router import ProviderRouter
from company_knowledge_rag.retrieval.base import ChunkStore
from company_knowledge_rag.retrieval.memory_store import MemoryChunkStore
from company_knowledge_rag.retrieval.qdrant_store import QdrantChunkStore
from company_knowledge_rag.settings import MainProvider, Settings
from company_knowledge_rag.storage.registry import DocumentRegistry


def create_app(
    settings: Settings | None = None,
    provider: GenerationProvider | None = None,
    store: ChunkStore | None = None,
) -> FastAPI:
    settings = settings or Settings()
    if store is None:
        store = MemoryChunkStore() if provider is not None else _build_qdrant_store(settings)
    provider = provider or _build_provider(settings)
    registry = DocumentRegistry(settings.registry_path)
    enricher = LLMChunkEnricher(provider) if settings.enable_enrichment else None
    ingestion = IngestionService(registry, store, settings.upload_dir, enricher)
    chat = ChatService(store, provider, Tracer(settings), settings.retrieval_limit)

    app = FastAPI(
        title="Company Knowledge RAG",
        version="0.1.0",
        description="ACL-aware RAG API for internal company documents",
        docs_url=None,
    )
    app.state.settings = settings
    app.state.store = store
    app.state.provider = provider
    app.state.registry = registry
    app.state.ingestion = ingestion
    app.state.chat = chat

    @app.get("/docs", include_in_schema=False)
    def swagger_docs() -> HTMLResponse:
        response = get_swagger_ui_html(
            openapi_url=app.openapi_url,
            title=f"{app.title} - Swagger UI",
            swagger_ui_parameters={"persistAuthorization": True},
        )
        default_api_key = settings.swagger_default_api_key()
        if default_api_key is None:
            return response
        html = response.body.decode("utf-8")
        html = html.replace("const ui = SwaggerUIBundle(", "window.ui = SwaggerUIBundle(")
        authorization = (
            "<script>window.addEventListener(\"load\", () => "
            f"window.ui.preauthorizeApiKey(\"ApiKeyAuth\", {json.dumps(default_api_key)}));</script>"
        )
        return HTMLResponse(html.replace("</body>", f"{authorization}</body>"))

    @app.get("/health", tags=["operations"])
    def health(request: Request) -> dict[str, str]:
        provider = request.app.state.provider
        primary = getattr(provider, "primary", provider)
        active_model = str(getattr(primary, "model", getattr(primary, "name", "unknown")))
        return {"status": "ok", "active_model": active_model}

    @app.get("/ready", tags=["operations"])
    def ready(request: Request) -> dict[str, str]:
        current_provider = request.app.state.provider
        provider_ready = getattr(current_provider, "ready", lambda: current_provider is not None)()
        if not request.app.state.store.ready() or not provider_ready:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Dependencies unavailable")
        return {"status": "ready"}

    @app.post("/v1/documents", response_model=Document, status_code=status.HTTP_201_CREATED)
    async def upload_document(
        file: UploadFile = File(...),
        allowed_roles: str = Form(...),
        metadata: str = Form("{}"),
        principal: Principal = Depends(require_principal),
    ) -> Document:
        content = await file.read(settings.max_upload_bytes + 1)
        if len(content) > settings.max_upload_bytes:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "File is too large")
        roles = {role.strip() for role in allowed_roles.split(",") if role.strip()}
        if not roles:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "allowed_roles is required")
        if not roles.issubset(principal.roles):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Cannot assign document roles outside the caller's roles",
            )
        source_name = Path(file.filename or "upload").name
        existing = registry.find_by_source(source_name)
        if existing is not None and (
            existing.allowed_roles != roles
            or not existing.allowed_roles.issubset(principal.roles)
        ):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Existing document ACL cannot be changed through upload",
            )
        try:
            parsed_metadata = json.loads(metadata)
            if not isinstance(parsed_metadata, dict):
                raise ValueError
            return await run_in_threadpool(
                ingestion.ingest_bytes,
                source_name,
                content,
                roles,
                {str(key): str(value) for key, value in parsed_metadata.items()},
                actor_roles=principal.roles,
            )
        except PermissionError as exc:
            raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
        except UnsupportedDocumentError as exc:
            raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, str(exc)) from exc
        except (json.JSONDecodeError, ValueError) as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "metadata must be an object") from exc

    @app.get("/v1/documents/{document_id}", response_model=Document)
    def get_document(
        document_id: str, principal: Principal = Depends(require_principal)
    ) -> Document:
        document = registry.get(document_id)
        if document is None or not document.allowed_roles & principal.roles:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
        return document

    @app.post("/v1/documents/{document_id}/reindex", response_model=Document)
    def reindex_document(
        document_id: str, principal: Principal = Depends(require_principal)
    ) -> Document:
        document = registry.get(document_id)
        if document is None or not document.allowed_roles & principal.roles:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
        source_path = settings.upload_dir / (
            f"{document.id}.v{document.version}{Path(document.source_name).suffix.lower()}"
        )
        if not source_path.exists():
            raise HTTPException(status.HTTP_409_CONFLICT, "Source file is unavailable")
        return ingestion.ingest_bytes(
            document.source_name,
            source_path.read_bytes(),
            document.allowed_roles,
            document.metadata,
            force=True,
        )

    @app.post("/v1/chat", response_model=ChatResponse)
    def ask(
        body: ChatRequest, principal: Principal = Depends(require_principal)
    ) -> ChatResponse:
        try:
            return chat.answer(body.question, principal)
        except ProviderError as exc:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

    return app


def _build_provider(settings: Settings) -> GenerationProvider:
    primary = _build_configured_provider(settings, settings.main_provider)
    fallback = _build_fallback_provider(settings)
    return ProviderRouter(primary, fallback, max_attempts=settings.provider_max_attempts)


def _build_configured_provider(settings: Settings, provider: MainProvider) -> GenerationProvider:
    match provider:
        case MainProvider.GEMINI:
            return GeminiProvider(
                settings.gemini_api_key,
                settings.gemini_model,
                settings.provider_timeout_seconds,
            )
        case MainProvider.OPENROUTER:
            return OpenRouterProvider(
                settings.openrouter_api_key,
                settings.openrouter_model,
                settings.openrouter_allowed_models,
                settings.provider_timeout_seconds,
            )
        case MainProvider.OPENAI:
            return OpenAIProvider(
                settings.openai_api_key,
                settings.openai_model,
                settings.provider_timeout_seconds,
            )
    raise AssertionError(f"Unsupported main provider: {provider}")


def _build_fallback_provider(settings: Settings) -> GenerationProvider | None:
    # MAIN_PROVIDER always remains primary; only configured alternatives handle transient failures.
    for provider in MainProvider:
        if provider is settings.main_provider:
            continue
        try:
            return _build_configured_provider(settings, provider)
        except ValueError:
            continue
    return None


def _build_qdrant_store(settings: Settings) -> QdrantChunkStore:
    embedder = GeminiEmbeddingProvider(
        settings.gemini_api_key,
        settings.embedding_model,
        settings.vector_size,
    )
    return QdrantChunkStore(
        settings.qdrant_url,
        settings.qdrant_api_key,
        settings.qdrant_collection,
        settings.vector_size,
        embedder,
        settings.lexical_candidate_limit,
        settings.min_dense_score,
    )


def app_factory() -> FastAPI:
    """Uvicorn factory that validates provider configuration at startup."""
    return create_app()
