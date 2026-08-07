from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile, status
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse
from starlette.concurrency import run_in_threadpool

from domain.schemas import ChatRequest, ChatResponse, Document
from generation.service import ChatService
from ingestion.chunker import ChunkingConfig
from ingestion.enrichment import LLMChunkEnricher
from ingestion.parser import UnsupportedDocumentError
from ingestion.raptor import RaptorConfig
from ingestion.service import CHUNK_MAX_CHARS, IngestionService
from observability.tracing import Tracer
from providers.base import EmbeddingProvider, GenerationProvider, ProviderError
from providers.gemini import GeminiEmbeddingProvider, GeminiProvider
from providers.jina import JinaEmbeddingProvider, JinaReranker
from providers.openai import OpenAIProvider
from providers.openrouter import OpenRouterProvider
from providers.probe import probe_generation
from providers.router import ProviderRouter
from retrieval.base import ChunkStore
from retrieval.hierarchical import ExpansionConfig
from retrieval.memory_store import MemoryChunkStore
from retrieval.qdrant_store import QdrantChunkStore
from settings import MainProvider, Settings
from storage.registry import DocumentRegistry


def create_app(
    settings: Settings | None = None,
    provider: GenerationProvider | None = None,
    store: ChunkStore | None = None,
) -> FastAPI:
    settings = settings or Settings()
    expansion = _build_expansion_config(settings)
    if store is None:
        store = (
            MemoryChunkStore(expansion)
            if provider is not None
            else _build_qdrant_store(settings, expansion)
        )
    provider = provider or _build_provider(settings)
    registry = DocumentRegistry(settings.registry_path)
    mrl_embedder = _build_mrl_embedder(settings) if settings.enrich_mrl_enabled else None
    enricher = (
        LLMChunkEnricher(provider, mrl_embedder=mrl_embedder) if settings.enable_enrichment else None
    )
    tracer = Tracer(settings)
    chunking_config = _build_chunking_config(settings)
    raptor_config = RaptorConfig(
        enabled=settings.raptor_enabled,
        cluster_size=settings.raptor_cluster_size,
        max_depth=settings.raptor_max_depth,
        provider=provider if settings.raptor_enabled else None,
    )
    ingestion = IngestionService(
        registry,
        store,
        settings.upload_dir,
        enricher,
        tracer,
        chunking_config=chunking_config,
        raptor_config=raptor_config,
    )
    chat = ChatService(store, provider, tracer, settings.retrieval_limit)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        tracer.flush()

    app = FastAPI(
        title="Company Knowledge RAG",
        version="0.1.0",
        description="Single-user open workspace RAG API for internal company documents",
        docs_url=None,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.store = store
    app.state.provider = provider
    app.state.registry = registry
    app.state.tracer = tracer
    app.state.ingestion = ingestion
    app.state.chat = chat

    @app.get("/docs", include_in_schema=False)
    def swagger_docs() -> HTMLResponse:
        if app.openapi_url is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OpenAPI schema is disabled")
        return get_swagger_ui_html(
            openapi_url=app.openapi_url,
            title=f"{app.title} - Swagger UI",
            swagger_ui_parameters={"persistAuthorization": True},
        )

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
        try:
            probed_model = probe_generation(current_provider)
        except ProviderError as exc:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, f"Provider probe failed: {exc}"
            ) from exc
        return {"status": "ready", "probed_model": probed_model}

    @app.post("/v1/documents", response_model=Document, status_code=status.HTTP_201_CREATED)
    async def upload_document(
        file: UploadFile = File(...),
        metadata: str = Form("{}"),
    ) -> Document:
        content = await file.read(settings.max_upload_bytes + 1)
        if len(content) > settings.max_upload_bytes:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "File is too large")
        source_name = Path(file.filename or "upload").name
        try:
            parsed_metadata = json.loads(metadata)
            if not isinstance(parsed_metadata, dict):
                raise ValueError
            return await run_in_threadpool(
                ingestion.ingest_bytes,
                source_name,
                content,
                {str(key): str(value) for key, value in parsed_metadata.items()},
            )
        except UnsupportedDocumentError as exc:
            raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, str(exc)) from exc
        except (json.JSONDecodeError, ValueError) as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "metadata must be an object") from exc

    @app.get("/v1/documents/{document_id}", response_model=Document)
    def get_document(document_id: str) -> Document:
        document = registry.get(document_id)
        if document is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
        return document

    @app.post("/v1/documents/{document_id}/reindex", response_model=Document)
    def reindex_document(document_id: str) -> Document:
        document = registry.get(document_id)
        if document is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
        source_path = settings.upload_dir / (
            f"{document.id}.v{document.version}{Path(document.source_name).suffix.lower()}"
        )
        if not source_path.exists():
            raise HTTPException(status.HTTP_409_CONFLICT, "Source file is unavailable")
        return ingestion.ingest_bytes(
            document.source_name,
            source_path.read_bytes(),
            document.metadata,
            force=True,
        )

    @app.post("/v1/chat", response_model=ChatResponse)
    def ask(body: ChatRequest) -> ChatResponse:
        try:
            return chat.answer(body.question)
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
            key_pool = settings.build_gemini_key_pool()
            return GeminiProvider(
                key_pool,
                settings.gemini_model,
                settings.provider_timeout_seconds,
                settings.structured_max_retries,
            )
        case MainProvider.OPENROUTER:
            return OpenRouterProvider(
                settings.openrouter_api_key,
                settings.openrouter_model,
                settings.openrouter_allowed_models,
                settings.provider_timeout_seconds,
                settings.structured_max_retries,
            )
        case MainProvider.OPENAI:
            return OpenAIProvider(
                settings.openai_api_key,
                settings.openai_model,
                settings.provider_timeout_seconds,
                settings.structured_max_retries,
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


def _build_embedding_provider(settings: Settings, output_dimension: int) -> EmbeddingProvider:
    """Shared embedder builder so chunking/enrichment (MRL) and Qdrant search
    use the same provider selection logic, just with a different output size."""
    jina_pool = settings.build_jina_key_pool()
    if jina_pool.key_count > 0 and settings.embedding_model.startswith("jina-"):
        return JinaEmbeddingProvider(
            api_key=jina_pool,
            model=settings.embedding_model,
            output_dimension=output_dimension,
            timeout_seconds=settings.provider_timeout_seconds,
        )
    return GeminiEmbeddingProvider(
        settings.build_gemini_key_pool(),
        settings.embedding_model,
        output_dimension,
        settings.provider_timeout_seconds,
    )


def _build_chunking_config(settings: Settings) -> ChunkingConfig:
    embedder = (
        _build_embedding_provider(settings, settings.vector_size)
        if settings.chunk_semantic_enabled
        else None
    )
    return ChunkingConfig(
        max_chars=CHUNK_MAX_CHARS,
        semantic_enabled=settings.chunk_semantic_enabled,
        semantic_threshold=settings.chunk_semantic_threshold,
        embedder=embedder,
        parent_child_enabled=settings.chunk_parent_child_enabled,
        parent_max_chars=settings.chunk_parent_max_chars,
    )


def _build_mrl_embedder(settings: Settings) -> EmbeddingProvider:
    return _build_embedding_provider(settings, settings.enrich_mrl_dimensions)


def _build_expansion_config(settings: Settings) -> ExpansionConfig:
    return ExpansionConfig(
        enabled=settings.hierarchical_expansion_enabled,
        max_parents=settings.hierarchical_max_parents,
        char_budget=settings.hierarchical_char_budget,
        max_parent_chars=settings.hierarchical_max_parent_chars,
        min_pool_coverage=settings.hierarchical_min_pool_coverage,
    )


def _build_qdrant_store(
    settings: Settings, expansion: ExpansionConfig | None = None
) -> QdrantChunkStore:
    embedder = _build_embedding_provider(settings, settings.vector_size)
    jina_pool = settings.build_jina_key_pool()
    reranker = None
    if jina_pool.key_count > 0 and settings.reranker_model:
        reranker = JinaReranker(
            api_key=jina_pool,
            model=settings.reranker_model,
            timeout_seconds=settings.provider_timeout_seconds,
        )

    return QdrantChunkStore(
        settings.qdrant_url,
        settings.qdrant_api_key,
        settings.qdrant_collection,
        settings.vector_size,
        embedder,
        settings.lexical_candidate_limit,
        settings.min_dense_score,
        reranker=reranker,
        rerank_candidate_limit=settings.rerank_candidate_limit,
        expansion=expansion if expansion is not None else _build_expansion_config(settings),
    )


def app_factory() -> FastAPI:
    """Uvicorn factory that validates provider configuration at startup."""
    return create_app()
