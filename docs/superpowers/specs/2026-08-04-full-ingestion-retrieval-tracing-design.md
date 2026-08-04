# Full ingestion, retrieval, and answer tracing

## Goal

Expose the complete RAG lifecycle in Langfuse when `TRACE_MODE=full`: document
ingestion and chunking, retrieval Top-K, generation prompts, and the final
grounded answer.  The same ingestion telemetry must cover both the HTTP upload
endpoint and the CLI because both route through `IngestionService`.

## Privacy modes

`off` creates no Langfuse client or observations. `metadata-only` records only
operational metadata such as identifiers, counts, scores, durations, provider,
model, and token usage. It never records document text, question text, prompt
text, chunk text, or answer text.

`full` requires `ALLOW_SENSITIVE_TRACING=true`. It records the complete
document text produced by parsing, complete chunk records, question, retrieval
Top-K content, prompts, context, and final answer. This mode is intended only
for a Langfuse deployment with suitable access controls and retention.

## Trace shape

### Ingestion

The service creates one root `ingestion` observation. Its nested observations
are:

1. `parse`: source name, file size, MIME type, parse status, and parsed text in
   full mode.
2. `chunking`: document ID/version, chunking configuration, total chunks, and
   ordered chunk records (`id`, `position`, `section`, `content_hash`, and
   `text` in full mode).
3. `enrichment`: emitted only when enrichment is enabled; records count,
   provider/model/usage when available, and enriched values in full mode.
4. `indexing`: document ID/version, chunk count written to the store, and
   elapsed time.
5. `registry`: document ID/version/status and elapsed time for persistence.

The existing idempotent early return is still traced. It records that ingestion
was skipped, along with the existing document identity, but performs no parse,
chunking, indexing, or registry child observation.

### Chat

The existing root `rag-request` keeps the nested `retrieval` and `generation`
observations.

`retrieval` is updated before it closes with latency, result count, and a
ranked Top-K list. Each list item contains rank, retrieval score, chunk ID,
document ID, version, source name, section, position, content hash, and chunk
text in full mode.

`generation` stores the rendered system instruction and user prompt, question,
context chunks, prompt version, provider/model/token usage, the structured
model response, validated citations, and the final answer returned by
`ChatService`. In metadata-only mode the sensitive text fields are removed.

## Tracer interface and errors

`Tracer` remains a no-op when unavailable, so unit tests and deployments
without Langfuse behave as before. It gains a central helper for recursively
redacting sensitive keys in metadata-only mode and accepts safe updates to an
active observation. Updates happen before each context manager exits.

Errors remain visible through Langfuse's context-manager error handling; where
the application handles a meaningful outcome (such as no search hits), the
observation metadata records that outcome.

## Configuration

Settings continue to consume `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`,
`LANGFUSE_HOST`, `TRACE_MODE`, and `ALLOW_SENSITIVE_TRACING`. The optional
Docker compose overlay must pass those exact environment variable names rather
than the currently unused `RAG_*` names.

## Tests

Add unit tests covering no client/off behavior, recursive metadata redaction,
full payload preservation, Top-K ordering and fields, final answer/citations,
ingestion child span names and metadata, the idempotent path, and preservation
of existing ingestion/chat behavior. Tests use a recording tracer and avoid a
network Langfuse dependency.
