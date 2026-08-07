from __future__ import annotations

import logging
import time
from collections.abc import Callable
from functools import partial
from hashlib import sha256
from threading import Lock
from typing import Any, TypeVar

from pydantic import ValidationError
from qdrant_client import QdrantClient, models
from qdrant_client.grpc import PointId
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse

from domain.schemas import Chunk, SearchHit
from providers.base import EmbeddingProvider, ProviderError
from retrieval.hierarchical import DEFAULT_EXPANSION, ExpansionConfig, expand_with_siblings
from retrieval.hybrid import (
    filter_by_min_score,
    lexical_rank,
    reciprocal_rank_fusion,
)

logger = logging.getLogger(__name__)

MAX_READ_ATTEMPTS = 3
BASE_RETRY_DELAY_SECONDS = 0.5
MAX_RETRY_DELAY_SECONDS = 4.0

T = TypeVar("T")


def _is_transient_qdrant_error(exc: BaseException) -> bool:
    """Connection drops and 5xx deserve another try; 4xx means the request itself is wrong."""
    if isinstance(exc, ResponseHandlingException):
        # Wraps the httpx transport failure (connect reset, read timeout, DNS).
        return True
    if isinstance(exc, UnexpectedResponse):
        return exc.status_code is None or exc.status_code >= 500
    return isinstance(exc, (ConnectionError, TimeoutError, OSError))


def _read_with_retry(operation: Callable[[], T], description: str) -> T:
    """Retry an idempotent Qdrant read past transient disconnects.

    Qdrant Cloud drops connections often enough that a single blip used to fail a
    whole evaluation case. Reads carry no side effects, so replaying them is safe;
    writes are deliberately left alone.
    """
    last_error: BaseException | None = None
    for attempt in range(MAX_READ_ATTEMPTS):
        try:
            return operation()
        except Exception as exc:
            if not _is_transient_qdrant_error(exc):
                raise
            last_error = exc
            if attempt + 1 < MAX_READ_ATTEMPTS:
                delay = min(BASE_RETRY_DELAY_SECONDS * (2.0**attempt), MAX_RETRY_DELAY_SECONDS)
                logger.warning(
                    "Qdrant %s failed (%s), retrying in %.1fs", description, type(exc).__name__, delay
                )
                time.sleep(delay)
    raise RuntimeError(
        f"Qdrant {description} failed after {MAX_READ_ATTEMPTS} attempts: {last_error}"
    ) from last_error


def _chunk_payload(chunk: Chunk) -> dict[str, object]:
    payload = chunk.model_dump(mode="json")
    payload.update(chunk.coordinates.model_dump())
    return payload


def _chunk_from_payload(payload: dict[str, object] | None) -> Chunk:
    try:
        return Chunk.model_validate(payload)
    except ValidationError as exc:
        if isinstance(payload, dict) and "coordinates" not in payload:
            raise RuntimeError(
                "Qdrant chunk payload lacks required source coordinates; re-index the corpus"
            ) from exc
        raise


class QdrantChunkStore:
    def __init__(
        self,
        url: str,
        api_key: str,
        collection: str,
        vector_size: int,
        embedder: EmbeddingProvider,
        lexical_candidate_limit: int = 500,
        min_dense_score: float = 0.35,
        reranker: Any | None = None,
        rerank_candidate_limit: int = 50,
        expansion: ExpansionConfig = DEFAULT_EXPANSION,
    ) -> None:
        self.client = QdrantClient(url=url, api_key=api_key or None, timeout=10)
        self.collection = collection
        self.vector_size = vector_size
        self.embedder = embedder
        self.lexical_candidate_limit = lexical_candidate_limit
        self.min_dense_score = min_dense_score
        self.reranker = reranker
        self.rerank_candidate_limit = rerank_candidate_limit
        self.expansion = expansion
        self._init_lock = Lock()
        self._initialized = False

    def ensure_collection(self) -> None:
        if self._initialized:
            return
        with self._init_lock:
            if self._initialized:
                return
            if not self.client.collection_exists(self.collection):
                try:
                    self.client.create_collection(
                        self.collection,
                        vectors_config=models.VectorParams(
                            size=self.vector_size,
                            distance=models.Distance.COSINE,
                        ),
                    )
                except Exception:
                    if not self.client.collection_exists(self.collection):
                        raise
            info = self.client.get_collection(self.collection)
            vectors_config = info.config.params.vectors
            actual_size = getattr(vectors_config, "size", None)
            if actual_size != self.vector_size:
                raise RuntimeError(
                    f"Qdrant vector size is {actual_size}; expected {self.vector_size}"
                )
            payload_schema = info.payload_schema or {}
            for field in ("document_id", "status", "doc_id", "chapter", "article", "version"):
                if field in payload_schema:
                    continue
                schema = (
                    models.PayloadSchemaType.INTEGER
                    if field == "version"
                    else models.PayloadSchemaType.KEYWORD
                )
                self.client.create_payload_index(self.collection, field, schema, wait=True)
            self._initialized = True

    def replace_document(self, document_id: str, chunks: list[Chunk]) -> None:
        self.ensure_collection()
        if not chunks:
            self.client.delete(
                self.collection,
                points_selector=models.FilterSelector(
                    filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="document_id",
                                match=models.MatchValue(value=document_id),
                            )
                        ]
                    )
                ),
                wait=True,
            )
            return
        vectors = self.embedder.embed_documents([chunk.retrieval_text or chunk.text for chunk in chunks])
        points = [
            models.PointStruct(id=_point_id(chunk.id), vector=vector, payload=_chunk_payload(chunk))
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
        self.client.upsert(self.collection, points=points, wait=True)
        active_version = chunks[0].version
        self.client.delete(
            self.collection,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="document_id",
                            match=models.MatchValue(value=document_id),
                        )
                    ],
                    must_not=[
                        models.FieldCondition(
                            key="version",
                            match=models.MatchValue(value=active_version),
                        )
                    ],
                )
            ),
            wait=True,
        )

    def search(self, query: str, limit: int = 5) -> list[SearchHit]:
        self.ensure_collection()
        query_filter = models.Filter(
            must=[
                models.FieldCondition(key="status", match=models.MatchValue(value="ready")),
            ]
        )
        candidate_limit = (
            max(self.rerank_candidate_limit, limit)
            if self.reranker
            else max(limit * 4, limit)
        )
        query_vector = self.embedder.embed_query(query)
        dense_response = _read_with_retry(
            lambda: self.client.query_points(
                collection_name=self.collection,
                query=query_vector,
                query_filter=query_filter,
                limit=candidate_limit,
                with_payload=True,
            ),
            "dense query",
        )
        dense = filter_by_min_score(
            [
                SearchHit(chunk=_chunk_from_payload(point.payload), score=float(point.score))
                for point in dense_response.points
            ],
            self.min_dense_score,
        )
        records, _ = _read_with_retry(
            lambda: self.client.scroll(
                collection_name=self.collection,
                scroll_filter=query_filter,
                limit=self.lexical_candidate_limit,
                with_payload=True,
                with_vectors=False,
            ),
            "lexical scroll",
        )
        lexical_chunks = [_chunk_from_payload(record.payload) for record in records]
        lexical = lexical_rank(query, lexical_chunks, candidate_limit)
        fused = reciprocal_rank_fusion(dense, lexical, candidate_limit)
        top = fused[:limit]
        if self.reranker and fused:
            try:
                top = self.reranker.rerank(query, fused, top_n=limit)
            except ProviderError:
                top = fused[:limit]
        # `lexical_chunks` is the scroll already fetched above for BM25 and holds
        # every ready chunk in the collection, so sibling expansion needs no
        # additional round trip.
        return expand_with_siblings(
            top,
            sibling_pool=lexical_chunks,
            ranking_pool=fused,
            config=self.expansion,
        )

    def list_document_chunks(
        self,
        document_id: str,
        version: int | None = None,
    ) -> list[Chunk]:
        self.ensure_collection()
        must = [
            models.FieldCondition(
                key="document_id",
                match=models.MatchValue(value=document_id),
            )
        ]
        if version is not None:
            must.append(
                models.FieldCondition(
                    key="version",
                    match=models.MatchValue(value=version),
                )
            )
        output: list[Chunk] = []
        offset: models.ExtendedPointId | PointId | None = None
        while True:
            records, next_offset = _read_with_retry(
                partial(
                    self.client.scroll,
                    collection_name=self.collection,
                    scroll_filter=models.Filter(must=must),
                    limit=256,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False,
                ),
                "document scroll",
            )
            output.extend(_chunk_from_payload(record.payload) for record in records)
            if next_offset is None:
                break
            offset = next_offset
        return sorted(output, key=lambda chunk: chunk.position)

    def list_indexed_documents(self) -> dict[str, int]:
        """document_id -> chunk count, across the whole collection."""
        self.ensure_collection()
        counts: dict[str, int] = {}
        offset: models.ExtendedPointId | PointId | None = None
        while True:
            records, next_offset = _read_with_retry(
                partial(
                    self.client.scroll,
                    collection_name=self.collection,
                    limit=256,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False,
                ),
                "collection scroll",
            )
            for record in records:
                payload = record.payload or {}
                document_id = str(payload.get("document_id", ""))
                if document_id:
                    counts[document_id] = counts.get(document_id, 0) + 1
            if next_offset is None:
                break
            offset = next_offset
        return counts

    def purge_documents(self, document_ids: list[str]) -> int:
        """Delete every chunk of the given documents. Returns chunks removed."""
        if not document_ids:
            return 0
        self.ensure_collection()
        indexed = self.list_indexed_documents()
        removed = sum(indexed.get(document_id, 0) for document_id in document_ids)
        self.client.delete(
            self.collection,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="document_id",
                            match=models.MatchAny(any=list(document_ids)),
                        )
                    ]
                )
            ),
            wait=True,
        )
        return removed

    def ready(self) -> bool:
        try:
            self.ensure_collection()
            return True
        except Exception:
            return False


def _point_id(value: str) -> int:
    return int.from_bytes(sha256(value.encode("utf-8")).digest()[:8], "big", signed=False) & ((1 << 63) - 1)
