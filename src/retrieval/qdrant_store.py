from __future__ import annotations

from hashlib import sha256
from threading import Lock

from qdrant_client import QdrantClient, models

from domain.schemas import Chunk, SearchHit
from providers.base import EmbeddingProvider
from retrieval.hybrid import (
    filter_by_min_score,
    lexical_rank,
    reciprocal_rank_fusion,
)


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
    ) -> None:
        self.client = QdrantClient(url=url, api_key=api_key or None, timeout=10)
        self.collection = collection
        self.vector_size = vector_size
        self.embedder = embedder
        self.lexical_candidate_limit = lexical_candidate_limit
        self.min_dense_score = min_dense_score
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
            for field in ("document_id", "status", "version"):
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
            models.PointStruct(id=_point_id(chunk.id), vector=vector, payload=chunk.model_dump(mode="json"))
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
        dense_response = self.client.query_points(
            collection_name=self.collection,
            query=self.embedder.embed_query(query),
            query_filter=query_filter,
            limit=max(limit * 4, limit),
            with_payload=True,
        )
        dense = filter_by_min_score(
            [
                SearchHit(chunk=Chunk.model_validate(point.payload), score=float(point.score))
                for point in dense_response.points
            ],
            self.min_dense_score,
        )
        records, _ = self.client.scroll(
            collection_name=self.collection,
            scroll_filter=query_filter,
            limit=self.lexical_candidate_limit,
            with_payload=True,
            with_vectors=False,
        )
        lexical_chunks = [Chunk.model_validate(record.payload) for record in records]
        lexical = lexical_rank(query, lexical_chunks, max(limit * 4, limit))
        return reciprocal_rank_fusion(dense, lexical, limit)

    def ready(self) -> bool:
        try:
            self.ensure_collection()
            return True
        except Exception:
            return False


def _point_id(value: str) -> int:
    return int.from_bytes(sha256(value.encode("utf-8")).digest()[:8], "big", signed=False) & ((1 << 63) - 1)
