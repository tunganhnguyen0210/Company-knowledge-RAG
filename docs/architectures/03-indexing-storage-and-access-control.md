# Indexing & Storage Layer

## Fresher AI Engineer Key Concepts

> [!NOTE]
> **What is Multi-Tiered Storage in RAG?**  
> RAG applications rely on multiple storage mechanisms tailored to different speeds and query types:
> 1. **Raw File Store**: Retains exact uploaded source bytes on disk so documents can be re-parsed or reindexed when algorithms improve.
> 2. **Document Registry**: A lightweight JSON database managing document metadata, version history, and status flags.
> 3. **Vector Database**: High-performance nearest-neighbor search index (Qdrant) filtering on `status == "ready"`.

## Storage Components Matrix

| Storage Subsystem | Location / Engine | Purpose | Key Module |
| --- | --- | --- | --- |
| **Document Registry** | `data/registry.json` | Tracks document versions, content hashes, and processing statuses. | [`src/storage/registry.py`](../../src/storage/registry.py) |
| **Source File Retainer** | `data/uploads/` | Stores raw uploaded bytes (`<doc_id>.v<ver>.<ext>`) for reindexing. | [`src/ingestion/service.py`](../../src/ingestion/service.py) |
| **Vector Database** | Qdrant (`http://localhost:6333`) | Stores 1024d dense embeddings and chunk payload metadata. | [`src/retrieval/qdrant_store.py`](../../src/retrieval/qdrant_store.py) |
| **In-Memory Store** | Python List (MemoryChunkStore) | Fast fallback vector/lexical store for unit tests and local dev. | [`src/retrieval/memory_store.py`](../../src/retrieval/memory_store.py) |

## Vector Indexing Strategy

### Collection Configuration (`QdrantChunkStore`)
- **Collection Name**: Configurable via `QDRANT_COLLECTION` (defaults to `"company_knowledge"`).
- **Vector Parameters**: 1024 dimensions, Cosine distance similarity.
- **Payload Indexing**: Qdrant payload indexes are created on six fields at collection initialization (`qdrant_store.py:87`):

  | Field | Type | Purpose |
  | --- | --- | --- |
  | `status` | KEYWORD | **Active retrieval gate** — all search queries filter on `status = "ready"` |
  | `document_id` | KEYWORD | Document lifecycle — used to delete/replace chunks on reindex |
  | `version` | INTEGER | Version cleanup — preserves newest version, purges older chunks |
  | `doc_id` | KEYWORD | Pre-indexed for future per-coordinate filtering (not yet queried) |
  | `chapter` | KEYWORD | Pre-indexed for future per-coordinate filtering (not yet queried) |
  | `article` | KEYWORD | Pre-indexed for future per-coordinate filtering (not yet queried) |

### Status-Based Vector Filtering
In the single-user open workspace model, vector queries search across all processed documents by enforcing a simple, robust status filter:

```json
{
  "must": [
    { "key": "status", "match": { "value": "ready" } }
  ]
}
```

This ensures that partially uploaded, processing, or failed documents are never retrieved, while all valid documents remain globally searchable.
