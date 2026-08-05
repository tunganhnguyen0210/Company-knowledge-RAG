from __future__ import annotations

import json
import time
from contextlib import asynccontextmanager
from pathlib import Path
from statistics import median
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse
from starlette.concurrency import run_in_threadpool

from domain.schemas import (
    ChatRequest,
    ChatResponse,
    Chunk,
    ChunkPage,
    ChunkPreview,
    ChunkStats,
    Document,
    DocumentStatus,
    RankedHit,
    SearchRequest,
    SearchResponse,
)
from generation.service import ChatService
from ingestion.chunker import chunk_document
from ingestion.enrichment import LLMChunkEnricher
from ingestion.parser import UnsupportedDocumentError, parse_document
from ingestion.service import CHUNK_MAX_CHARS, IngestionService
from observability.tracing import Tracer
from providers.base import GenerationProvider, ProviderError
from providers.gemini import GeminiEmbeddingProvider, GeminiProvider
from providers.jina import JinaEmbeddingProvider, JinaReranker
from providers.openai import OpenAIProvider
from providers.openrouter import OpenRouterProvider
from providers.probe import probe_generation
from providers.router import ProviderRouter
from retrieval.base import ChunkStore
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
    if store is None:
        store = MemoryChunkStore() if provider is not None else _build_qdrant_store(settings)
    provider = provider or _build_provider(settings)
    registry = DocumentRegistry(settings.registry_path)
    enricher = LLMChunkEnricher(provider) if settings.enable_enrichment else None
    tracer = Tracer(settings)
    ingestion = IngestionService(registry, store, settings.upload_dir, enricher, tracer)
    chat = ChatService(store, provider, tracer, settings.retrieval_limit)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
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

    @app.post(
        "/v1/documents/preview-chunks",
        response_model=ChunkPreview,
        tags=["inspection"],
        summary="Parse and chunk a file without indexing it",
    )
    async def preview_chunks(
        file: UploadFile = File(...),
        max_chars: int = Form(CHUNK_MAX_CHARS),
    ) -> ChunkPreview:
        """Dry run of the ingest pipeline: shows exactly what every chunk would contain.

        Nothing is embedded, indexed or written to the registry, so it is safe to call
        repeatedly while tuning `max_chars`.
        """
        content = await file.read(settings.max_upload_bytes + 1)
        if len(content) > settings.max_upload_bytes:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "File is too large")
        if not 100 <= max_chars <= 10_000:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "max_chars must be 100..10000")
        source_name = Path(file.filename or "upload").name
        try:
            text, mime_type = parse_document(source_name, content)
        except UnsupportedDocumentError as exc:
            raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, str(exc)) from exc
        document_status = DocumentStatus.READY if text.strip() else DocumentStatus.FAILED
        preview_document = Document(
            id="preview",
            version=0,
            content_hash="preview",
            source_name=source_name,
            mime_type=mime_type,
            status=document_status,
        )
        chunks = chunk_document(preview_document, text, max_chars=max_chars)
        return ChunkPreview(
            source_name=source_name,
            mime_type=mime_type,
            status=document_status,
            parsed_characters=len(text),
            max_chars=max_chars,
            stats=_chunk_stats(chunks, max_chars),
            chunks=chunks,
        )

    @app.get("/v1/documents", response_model=list[Document], tags=["inspection"])
    def list_documents() -> list[Document]:
        return registry.list()

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

    @app.get(
        "/v1/documents/{document_id}/chunks",
        response_model=ChunkPage,
        tags=["inspection"],
        summary="Read back the chunks stored for a document",
    )
    def list_document_chunks(
        document_id: str,
        offset: int = Query(0, ge=0),
        limit: int = Query(20, ge=1, le=200),
    ) -> ChunkPage:
        document = registry.get(document_id)
        if document is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
        chunks = store.list_chunks(document_id)
        return ChunkPage(
            document_id=document_id,
            source_name=document.source_name,
            version=document.version,
            total=len(chunks),
            offset=offset,
            limit=limit,
            chunks=chunks[offset : offset + limit],
        )

    @app.post(
        "/v1/search",
        response_model=SearchResponse,
        tags=["inspection"],
        summary="Run retrieval only and return the chunks with their scores",
    )
    def search(body: SearchRequest) -> SearchResponse:
        """Same retrieval path /v1/chat uses, minus the LLM call.

        Use it to check whether the right chunks come back before blaming the answer.
        """
        limit = body.limit or settings.retrieval_limit
        started = time.perf_counter()
        hits = store.search(body.query, limit=limit)
        latency_ms = (time.perf_counter() - started) * 1000
        return SearchResponse(
            query=body.query,
            limit=limit,
            result_count=len(hits),
            latency_ms=latency_ms,
            hits=[
                RankedHit(rank=rank, score=hit.score, chunk=hit.chunk)
                for rank, hit in enumerate(hits, start=1)
            ],
        )

    @app.post("/v1/chat", response_model=ChatResponse)
    def ask(body: ChatRequest) -> ChatResponse:
        try:
            return chat.answer(body.question)
        except ProviderError as exc:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

    return app


def _chunk_stats(chunks: list[Chunk], max_chars: int) -> ChunkStats:
    lengths = [len(chunk.text) for chunk in chunks]
    if not lengths:
        return ChunkStats(
            chunk_count=0,
            total_chars=0,
            min_chars=0,
            median_chars=0,
            max_chars=0,
            sections_detected=0,
            chunks_without_section=0,
            chunks_at_max_chars=0,
        )
    return ChunkStats(
        chunk_count=len(chunks),
        total_chars=sum(lengths),
        min_chars=min(lengths),
        median_chars=int(median(lengths)),
        max_chars=max(lengths),
        sections_detected=len({chunk.section for chunk in chunks if chunk.section}),
        chunks_without_section=sum(1 for chunk in chunks if chunk.section is None),
        # A chunk sitting exactly on the cap was cut by character count, not by structure.
        chunks_at_max_chars=sum(1 for length in lengths if length == max_chars),
    )


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


def _build_qdrant_store(settings: Settings) -> QdrantChunkStore:
    if settings.jina_api_key and settings.embedding_model.startswith("jina-"):
        embedder: Any = JinaEmbeddingProvider(
            api_key=settings.jina_api_key,
            model=settings.embedding_model,
            output_dimension=settings.vector_size,
            timeout_seconds=settings.provider_timeout_seconds,
        )
    else:
        embedder = GeminiEmbeddingProvider(
            settings.build_gemini_key_pool(),
            settings.embedding_model,
            settings.vector_size,
            settings.provider_timeout_seconds,
        )

    reranker = None
    if settings.jina_api_key and settings.reranker_model:
        reranker = JinaReranker(
            api_key=settings.jina_api_key,
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
    )


def app_factory() -> FastAPI:
    """Uvicorn factory that validates provider configuration at startup."""
    return create_app()
