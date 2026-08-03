from __future__ import annotations

from hashlib import sha256

from qdrant_client import QdrantClient, models

from company_knowledge_rag.domain.schemas import Chunk, Principal, SearchHit
from company_knowledge_rag.providers.base import EmbeddingProvider
from company_knowledge_rag.retrieval.hybrid import lexical_rank, reciprocal_rank_fusion


class QdrantChunkStore:
    def __init__(
        self,
        url: str,
        api_key: str,
        collection: str,
        vector_size: int,
        embedder: EmbeddingProvider,
        lexical_candidate_limit: int = 500,
    ) -> None:
        self.client = QdrantClient(url=url, api_key=api_key or None, timeout=10)
        self.collection = collection
        self.vector_size = vector_size
        self.embedder = embedder
        self.lexical_candidate_limit = lexical_candidate_limit

    def ensure_collection(self) -> None:
        if not self.client.collection_exists(self.collection):
            self.client.create_collection(
                self.collection,
                vectors_config=models.VectorParams(size=self.vector_size, distance=models.Distance.COSINE),
            )
            for field in ("document_id", "status", "allowed_roles", "version"):
                schema = models.PayloadSchemaType.INTEGER if field == "version" else models.PayloadSchemaType.KEYWORD
                self.client.create_payload_index(self.collection, field, schema, wait=True)

    def replace_document(self, document_id: str, chunks: list[Chunk]) -> None:
        self.ensure_collection()
        self.client.delete(
            self.collection,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[models.FieldCondition(key="document_id", match=models.MatchValue(value=document_id))]
                )
            ),
            wait=True,
        )
        if not chunks:
            return
        vectors = self.embedder.embed_documents([chunk.retrieval_text or chunk.text for chunk in chunks])
        points = [
            models.PointStruct(id=_point_id(chunk.id), vector=vector, payload=chunk.model_dump(mode="json"))
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
        self.client.upsert(self.collection, points=points, wait=True)

    def search(self, query: str, principal: Principal, limit: int = 5) -> list[SearchHit]:
        if not principal.roles:
            return []
        self.ensure_collection()
        query_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="allowed_roles", match=models.MatchAny(any=sorted(principal.roles))
                ),
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
        dense = [
            SearchHit(chunk=Chunk.model_validate(point.payload), score=float(point.score))
            for point in dense_response.points
        ]
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
            self.client.get_collections()
            return True
        except Exception:
            return False


def _point_id(value: str) -> int:
    return int.from_bytes(sha256(value.encode("utf-8")).digest()[:8], "big", signed=False) & ((1 << 63) - 1)
