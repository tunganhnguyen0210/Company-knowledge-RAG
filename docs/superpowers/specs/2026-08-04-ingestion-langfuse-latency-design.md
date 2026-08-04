# Ingestion Langfuse Latency Export

## Goal

Make the batch ingestion CLI reliably export the existing per-step ingestion latency spans to Langfuse, including when a document fails.

## Scope

The ingestion service already creates Langfuse observations for `parse`, `chunking`, `indexing`, and `registry`, each with a `latency_ms` metadata field. The change is limited to ensuring the CLI flushes its shared tracer on shutdown. No local timing table, new metrics backend, provider retry policy, or document-processing behavior is added.

## Design

`src.cli.ingest` will retain the application instance it creates and wrap the directory-processing loop in `try`/`finally`. The `finally` clause will call the application tracer's `flush()` method.

This flush is deliberately at CLI-process scope rather than per document. It preserves normal batching while ensuring completed spans are sent after a successful run and spans from work completed before an exception are sent before the process exits.

The existing ingestion observation remains the parent span. Its children form a per-document timeline in Langfuse:

1. `parse` — document parsing time and MIME/character metadata.
2. `chunking` — splitting time and chunk count.
3. `indexing` — embedding plus Qdrant replacement time and chunk count.
4. `registry` — local registry write time.

Langfuse calculates parent and child observation duration from start/end timestamps; the explicit `latency_ms` fields provide the same values in queryable metadata.

## Failure Handling

The CLI will not swallow ingestion errors. It will flush first, then allow the original exception to propagate and retain its non-zero exit code. This makes partial progress and the failed document's preceding spans observable without changing failure semantics.

## Verification

Tests will prove that the tracer flushes once after a successful CLI ingest and once when ingestion raises. Existing ingestion tracing tests continue to prove that step spans carry their latency metadata. A live seed ingestion retry will then be checked in Langfuse for visible observations named `parse`, `chunking`, `indexing`, and `registry`.
