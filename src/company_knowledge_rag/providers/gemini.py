from __future__ import annotations

from company_knowledge_rag.providers.base import (
    GenerationRequest,
    GenerationResult,
    ProviderError,
)


class GeminiProvider:
    name = "gemini"

    def __init__(self, api_key: str, model: str, timeout_seconds: float = 30.0) -> None:
        if not api_key:
            raise ValueError("Gemini API key is required")
        from google import genai
        from google.genai import types

        self.model = model
        self._types = types
        self._client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=int(timeout_seconds * 1000)),
        )

    def generate(self, request: GenerationRequest) -> GenerationResult:
        try:
            response = self._client.models.generate_content(
                model=self.model,
                contents=request.user_prompt,
                config=self._types.GenerateContentConfig(
                    system_instruction=request.system_instruction,
                    temperature=request.temperature,
                    max_output_tokens=request.max_output_tokens,
                ),
            )
            if not response.text:
                raise ProviderError("Gemini returned an empty response", transient=False)
            usage_metadata = response.usage_metadata
            usage = {
                "input_tokens": int(getattr(usage_metadata, "prompt_token_count", 0) or 0),
                "output_tokens": int(getattr(usage_metadata, "candidates_token_count", 0) or 0),
            }
            return GenerationResult(response.text, self.name, self.model, usage)
        except ProviderError:
            raise
        except Exception as exc:
            status = getattr(exc, "status_code", 0)
            transient = status in {408, 429, 500, 502, 503, 504} or isinstance(exc, TimeoutError)
            raise ProviderError(f"Gemini request failed: {exc}", transient=transient) from exc


class GeminiEmbeddingProvider:
    def __init__(self, api_key: str, model: str) -> None:
        if not api_key:
            raise ValueError("Gemini API key is required for embeddings")
        from google import genai

        self.model = model
        self._client = genai.Client(api_key=api_key)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        response = self._client.models.embed_content(model=self.model, contents=texts)
        return [list(embedding.values or []) for embedding in response.embeddings or []]

    def embed_query(self, text: str) -> list[float]:
        vectors = self.embed_documents([text])
        if not vectors:
            raise ProviderError("Gemini returned no embedding", transient=False)
        return vectors[0]
