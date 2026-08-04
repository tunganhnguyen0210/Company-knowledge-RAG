from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from langchain_core.runnables import Runnable, RunnableLambda

from providers.base import GenerationRequest
from providers.gemini import GeminiEmbeddingProvider, GeminiProvider
from providers.gemini_key_pool import GeminiKeyLease, GeminiKeyPool, GeminiKeysExhausted
from providers.llm_rotation import GeminiRotatingRunnable


def test_round_robin_key_rotation() -> None:
    pool = GeminiKeyPool.from_environment({
        "GEMINI_API_KEY": "key-1",
        "GEMINI_API_FALLBACK_KEY": "key-2",
        "GEMINI_API_FALLBACK_KEY2": "key-3",
    })
    leases = [pool.next_key().api_key for _ in range(4)]
    assert leases == ["key-1", "key-2", "key-3", "key-1"]


def test_quota_cooldown_failover() -> None:
    now = [100.0]
    pool = GeminiKeyPool.from_environment(
        {"GEMINI_API_KEY": "key-1", "GEMINI_API_FALLBACK_KEY": "key-2"},
        clock=lambda: now[0],
        cooldown_seconds=60,
    )
    first = pool.next_key()
    assert first.api_key == "key-1"
    pool.mark_quota_limited(first)

    # Should skip key-1 and return key-2
    assert pool.next_key().api_key == "key-2"

    # Advance clock past cooldown -> key-1 is healthy again
    now[0] += 61.0
    assert pool.next_key().api_key == "key-1"


def test_environment_key_discovery() -> None:
    env = {
        "GEMINI_API_FALLBACK_KEY10": "key-10",
        "GEMINI_API_KEY": "key-primary",
        "GEMINI_API_FALLBACK_KEY": "key-fallback-1",
        "GEMINI_API_FALLBACK_KEY2": "key-fallback-2",
        "OTHER_VAR": "ignored",
    }
    pool = GeminiKeyPool.from_environment(env)
    assert pool.key_count == 4
    keys = [pool.next_key().api_key for _ in range(4)]
    assert keys == ["key-primary", "key-fallback-1", "key-fallback-2", "key-10"]


def test_key_lease_security() -> None:
    lease = GeminiKeyLease(0, "secret-api-key-12345")
    assert "secret-api-key-12345" not in repr(lease)
    assert "secret-api-key-12345" not in str(lease)
    assert "***" in repr(lease)


def test_all_keys_exhausted_raises_exception() -> None:
    pool = GeminiKeyPool.from_environment({"GEMINI_API_KEY": "key-1"})
    pool.mark_quota_limited(pool.next_key())

    with pytest.raises(GeminiKeysExhausted):
        pool.next_key()


def test_runnable_automatically_retries_next_key_on_429() -> None:
    pool = GeminiKeyPool.from_environment({
        "GEMINI_API_KEY": "key-1",
        "GEMINI_API_FALLBACK_KEY": "key-2",
    })
    used_keys: list[str] = []

    class MockModel:
        def __init__(self, api_key: str) -> None:
            self.api_key = api_key

        def invoke(self, prompt: str, **kwargs: Any) -> str:
            used_keys.append(self.api_key)
            if self.api_key == "key-1":
                raise RuntimeError("429 RESOURCE_EXHAUSTED: Rate limit exceeded")
            return "Success response"

    runnable = GeminiRotatingRunnable(pool, lambda key: MockModel(key))
    result = runnable.invoke("Test prompt")

    assert result == "Success response"
    assert used_keys == ["key-1", "key-2"]


def test_rotating_runnable_composes_in_lcel_chains() -> None:
    """Guards the real base class: an ImportError fallback once made this a plain object."""
    pool = GeminiKeyPool.from_environment({"GEMINI_API_KEY": "key-1"})

    class MockModel:
        def __init__(self, api_key: str) -> None:
            pass

        def invoke(self, prompt: str, config: Any = None, **kwargs: Any) -> str:
            return f"answer:{prompt}"

    runnable = GeminiRotatingRunnable(pool, lambda key: MockModel(key))

    assert isinstance(runnable, Runnable)
    assert (runnable | RunnableLambda(lambda text: text.upper())).invoke("hi") == "ANSWER:HI"
    # batch() is inherited, not implemented here; it only exists on a real Runnable.
    assert runnable.batch(["a", "b"]) == ["answer:a", "answer:b"]


def test_runnable_fallback_provider() -> None:
    pool = GeminiKeyPool.from_environment({"GEMINI_API_KEY": "key-1"})

    class FailingModel:
        def __init__(self, api_key: str) -> None:
            pass

        def invoke(self, prompt: str, **kwargs: Any) -> str:
            raise RuntimeError("429 RESOURCE_EXHAUSTED")

    class FallbackModel:
        def invoke(self, prompt: str, **kwargs: Any) -> str:
            return "Fallback success"

    runnable = GeminiRotatingRunnable(
        pool,
        model_factory=lambda key: FailingModel(key),
        fallback_factory=lambda: FallbackModel(),
    )
    result = runnable.invoke("Test prompt")
    assert result == "Fallback success"


def test_gemini_provider_key_pool_failover(monkeypatch: pytest.MonkeyPatch) -> None:
    pool = GeminiKeyPool.from_environment({
        "GEMINI_API_KEY": "key-1",
        "GEMINI_API_FALLBACK_KEY": "key-2",
    })
    provider = GeminiProvider(pool, model="gemini-3.5-flash")

    used_keys: list[str] = []

    def mock_get_client(key: str) -> Any:
        client = MagicMock()

        def mock_generate(*args: Any, **kwargs: Any) -> Any:
            used_keys.append(key)
            if key == "key-1":
                raise RuntimeError("429 RESOURCE_EXHAUSTED: Quota limit reached")
            resp = MagicMock()
            resp.text = "Rotated answer"
            resp.usage_metadata.prompt_token_count = 10
            resp.usage_metadata.candidates_token_count = 20
            return resp

        client.models.generate_content.side_effect = mock_generate
        return client

    monkeypatch.setattr(provider, "_get_client", mock_get_client)

    result = provider.generate(GenerationRequest(system_instruction="sys", user_prompt="Hello"))
    assert result.text == "Rotated answer"
    assert used_keys == ["key-1", "key-2"]


def test_gemini_embedding_provider_key_pool_failover(monkeypatch: pytest.MonkeyPatch) -> None:
    pool = GeminiKeyPool.from_environment({
        "GEMINI_API_KEY": "key-1",
        "GEMINI_API_FALLBACK_KEY": "key-2",
    })
    embedder = GeminiEmbeddingProvider(pool, model="gemini-embedding-001", output_dimension=3)

    used_keys: list[str] = []

    def mock_get_client(key: str) -> Any:
        client = MagicMock()

        def mock_embed(*args: Any, **kwargs: Any) -> Any:
            used_keys.append(key)
            if key == "key-1":
                raise RuntimeError("429 Rate limit exceeded")
            emb = MagicMock()
            emb.values = [1.0, 0.0, 0.0]
            resp = MagicMock()
            resp.embeddings = [emb]
            return resp

        client.models.embed_content.side_effect = mock_embed
        return client

    monkeypatch.setattr(embedder, "_get_client", mock_get_client)

    vec = embedder.embed_query("test query")
    assert len(vec) == 3
    assert used_keys == ["key-1", "key-2"]
