"""Reconcile the vector index against the document registry.

`ChunkStore.replace_document` only deletes chunks for a document_id the caller
already holds, so any document that leaves the registry -- a reset registry, a
renamed source file, an ingest under a second filename -- strands its chunks in
the index. Nothing reaches them again: they are not listed, not replaced, not
deleted, and they keep competing for candidate slots on every query.

This module names that condition (orphan) and makes it actionable.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from retrieval.base import ChunkStore
from storage.registry import DocumentRegistry


@dataclass(frozen=True)
class ReconcileReport:
    indexed: dict[str, int] = field(default_factory=dict)
    """document_id -> chunk count, as found in the index."""
    registered: dict[str, str] = field(default_factory=dict)
    """document_id -> source_name, as found in the registry."""
    orphans: dict[str, int] = field(default_factory=dict)
    """In the index but not the registry: unreachable, safe to purge."""
    missing: dict[str, str] = field(default_factory=dict)
    """In the registry but not the index: needs re-ingest, never purge."""

    @property
    def orphan_chunk_count(self) -> int:
        return sum(self.orphans.values())

    @property
    def is_clean(self) -> bool:
        return not self.orphans and not self.missing


def reconcile(registry: DocumentRegistry, store: ChunkStore) -> ReconcileReport:
    indexed = store.list_indexed_documents()
    registered = {document.id: document.source_name for document in registry.list()}
    return ReconcileReport(
        indexed=indexed,
        registered=registered,
        orphans={
            document_id: count
            for document_id, count in indexed.items()
            if document_id not in registered
        },
        missing={
            document_id: source_name
            for document_id, source_name in registered.items()
            if document_id not in indexed
        },
    )


def purge_orphans(registry: DocumentRegistry, store: ChunkStore) -> tuple[ReconcileReport, int]:
    """Delete only chunks whose document is absent from the registry.

    Re-reads the report immediately before deleting so a stale caller-held
    report can never widen the blast radius.
    """
    report = reconcile(registry, store)
    if not report.orphans:
        return report, 0
    removed = store.purge_documents(list(report.orphans))
    return report, removed
