# Main provider configuration design

## Goal

Use unprefixed environment variable names and select exactly one generation
provider through `MAIN_PROVIDER`. The supported values are `gemini`,
`openrouter`, and `openai`.

## Configuration

`Settings` no longer uses the `RAG_` environment prefix. Existing `RAG_*`
variables are intentionally unsupported so deployment configuration has one
clear naming convention.

`MAIN_PROVIDER` defaults to `gemini`. Provider-specific configuration uses
unprefixed names, including `GEMINI_API_KEY`, `GEMINI_MODEL`,
`OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, `OPENAI_API_KEY`, and
`OPENAI_MODEL`. Qdrant, authentication, tracing, retrieval, and storage
variables are likewise renamed without the `RAG_` prefix.

## Provider selection

Generation uses exactly the provider selected by `MAIN_PROVIDER`. Gemini
continues to supply embeddings regardless of the selected generation provider.

Add an `OpenAIProvider` for direct OpenAI requests. Keep the existing
`GeminiProvider` and `OpenRouterProvider`. The application factory selects one
provider with an explicit match on `MAIN_PROVIDER`.

There is deliberately no fallback or cross-provider retry. Transient or
non-transient provider failures surface through the existing `ProviderError`
to the API as HTTP 502. A code comment beside selection documents that this is
intentional: callers must see failures from their selected provider promptly.

## Validation and documentation

Settings validation rejects unknown `MAIN_PROVIDER` values and validates only
the credentials/model requirements of the selected provider at provider
construction time. `.env.example`, Docker Compose variables, and the README
show the new variable names and selected-provider behavior.

## Tests

Tests prove unprefixed settings load correctly, prefixed settings do not alter
configuration, all supported provider choices instantiate the expected
provider, and a provider error does not invoke any fallback.

## Scope

This does not add configurable embedding providers, provider failover,
OpenAI-compatible custom base URLs, or runtime provider switching without an
application restart.
