# Research Report: Authentication & ACL Removal Analysis

**Date**: 2026-08-04  
**Target Application**: Company Knowledge RAG  
**Objective**: Analyze all authentication and Role-Based Access Control (RBAC/ACL) components across the codebase, and outline a refactoring strategy to transform the application into a single-user / open workspace RAG service (similar to a local Codex/Claude Cowork assistant).

---

## 1. Executive Summary

The current system enforces multi-tenant Role-Based Access Control (RBAC) at three critical control points:
1. **HTTP API Layer**: `X-API-Key` headers are parsed into a `Principal` carrying a set of `roles`.
2. **Ingestion & Metadata Layer**: Documents and chunks require `allowed_roles`.
3. **Retrieval Layer**: Qdrant vector search and BM25 lexical search apply mandatory pre-filtering for `allowed_roles INTERSECT principal_roles != EMPTY`.

Transitioning to a **single-user / open workspace model** requires eliminating API key verification, making `allowed_roles` optional or obsolete, removing Qdrant vector ACL pre-filters, and simplifying service function signatures across the pipeline.

---

## 2. Primary Source Analysis & Codebase Touchpoints

### A. Domain Schemas (`src/company_knowledge_rag/domain/schemas.py`)
- **`Principal` Model**: Holds `subject: str` and `roles: set[str]`. Passed into `ChatService.answer()` and `ChunkStore.search()`.
- **`Document` & `Chunk` Schemas**: Contain `allowed_roles: set[str]`.
- **Impact**: Removing or defaulting `allowed_roles` to `None` / `set()` decouples schemas from mandatory authorization tags.

### B. Authentication Middleware & Settings (`src/company_knowledge_rag/api/auth.py` & `settings.py`)
- **`auth.py`**: Exports `require_principal()` which enforces `X-API-Key` header and raises `401 Unauthorized` if missing or invalid.
- **`settings.py`**: Maintains `api_keys` JSON config and `principal_for_key()`.
- **Impact**: Deleting `require_principal` dependency from FastAPI routes or replacing it with an optional/no-op guest principal allows unauthenticated REST access.

### C. API Endpoints (`src/company_knowledge_rag/api/app.py`)
- **Upload Route (`POST /v1/documents`)**: Requires `allowed_roles: str = Form(...)` and validates `roles.issubset(principal.roles)`.
- **Document Management (`GET/DELETE/POST /v1/documents/{id}`)**: Checks `document.allowed_roles & principal.roles`.
- **Chat Route (`POST /v1/chat`)**: Requires `Depends(require_principal)` and passes `Principal` to `ChatService`.
- **Impact**: Removing `allowed_roles` form parameter requirement and removing `require_principal` dependencies allows open file uploads and querying.

### D. Ingestion Service & Chunker (`src/company_knowledge_rag/ingestion/`)
- **`IngestionService` (`service.py`)**: Requires `allowed_roles: set[str]` and validates `actor_roles`.
- **`chunk_document` (`chunker.py`)**: Attaches `allowed_roles` metadata to every chunk payload.
- **Impact**: `allowed_roles` can default to `{"*"}` or be omitted, making ingestion role-agnostic.

### E. Vector Retrieval Store (`src/company_knowledge_rag/retrieval/`)
- **`QdrantChunkStore` (`qdrant_store.py`)**: Adds a mandatory Qdrant `FieldCondition` on `allowed_roles` in `models.Filter`. Returns empty results if `principal.roles` is empty.
- **`MemoryChunkStore` (`memory_store.py`)**: Filters chunks via `chunk.allowed_roles & principal.roles`.
- **Impact**: Removing the `allowed_roles` filter condition enables Qdrant to search all `ready` chunks in the vector collection regardless of roles.

### F. Chat & Answer Service (`src/company_knowledge_rag/generation/service.py`)
- **`ChatService.answer()`**: Takes `principal: Principal`, logs `roles` in telemetry, and calls `store.search(question, principal)`.
- **Impact**: Removing `principal` requirement simplifies the chat signature to `answer(question: str)`.

### G. Evaluation Suite & Tests (`src/company_knowledge_rag/evaluation/` & `tests/`)
- **`runner.py`**: Constructs `Principal(subject="evaluation", roles=case.roles)`.
- **Unit & Integration Tests**: `test_settings.py`, `test_retrieval.py`, `test_generation.py`, `test_qdrant_acl.py`.
- **Impact**: Test assertions expecting `401 Unauthorized` or role filtering failures must be removed or updated to verify open search.

---

## 3. Proposed Refactoring Strategy (Phased Approach)

### Phase 1: Domain Schemas & Ingestion Simplification
1. Update `Principal` to have a default value (e.g. `Principal(subject="single-user", roles={"*"})`).
2. Make `allowed_roles` optional across `Document`, `Chunk`, and `IngestionService.ingest_document()`, defaulting to `{"*"}`.

### Phase 2: Vector Search ACL Removal
1. Remove `allowed_roles` matching condition in `QdrantChunkStore.search()`.
2. Ensure Qdrant queries filter solely on `status == "ready"`.
3. Update `MemoryChunkStore.search()` to match all `ready` chunks.

### Phase 3: API & Auth Removal
1. Remove `require_principal` from `POST /v1/documents`, `POST /v1/chat`, and document management routes in `api/app.py`.
2. Make `allowed_roles` optional in file upload form data.
3. Remove `api_keys` validation requirements from `settings.py`.

### Phase 4: Test Suite & Architecture Documentation Update
1. Update test files (`test_retrieval.py`, `test_generation.py`, `test_api.py`) for unauthenticated operation.
2. Update `RAG-ARCHITECTURE.md` and `docs/architectures/` to document the single-user / open workspace architecture model.

---

## 4. Primary Source Citations

- [`src/company_knowledge_rag/api/auth.py`](file:///e:/VIN-INTERNSHIP/Company-knowledge-RAG/src/company_knowledge_rag/api/auth.py)
- [`src/company_knowledge_rag/api/app.py`](file:///e:/VIN-INTERNSHIP/Company-knowledge-RAG/src/company_knowledge_rag/api/app.py#L93-L175)
- [`src/company_knowledge_rag/retrieval/qdrant_store.py`](file:///e:/VIN-INTERNSHIP/Company-knowledge-RAG/src/company_knowledge_rag/retrieval/qdrant_store.py#L120-L135)
- [`src/company_knowledge_rag/ingestion/service.py`](file:///e:/VIN-INTERNSHIP/Company-knowledge-RAG/src/company_knowledge_rag/ingestion/service.py#L34-L70)
- [`src/company_knowledge_rag/settings.py`](file:///e:/VIN-INTERNSHIP/Company-knowledge-RAG/src/company_knowledge_rag/settings.py#L89-L97)
