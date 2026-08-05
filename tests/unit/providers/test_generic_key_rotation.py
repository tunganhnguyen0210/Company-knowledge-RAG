import pytest

from providers.key_pool import ApiKeyLease, ApiKeyPool, ApiKeysExhausted


def test_generic_key_pool_discovery():
    env = {
        "JINA_API_KEY": "jina-key-1",
        "JINA_API_FALLBACK_KEY": "jina-key-2",
        "JINA_API_FALLBACK_KEY2": "jina-key-3",
        "OTHER_VAR": "value",
    }
    pool = ApiKeyPool.from_environment("JINA", env)
    assert pool.key_count == 3
    leases = [pool.next_key().api_key for _ in range(4)]
    assert leases == ["jina-key-1", "jina-key-2", "jina-key-3", "jina-key-1"]


def test_lease_repr_and_str_mask_key():
    lease = ApiKeyLease(position=0, api_key="secret-token-12345", provider_name="jina")
    assert "secret-token" not in repr(lease)
    assert "secret-token" not in str(lease)
    assert "***" in repr(lease)
    assert "provider='jina'" in repr(lease)


def test_cooldown_and_failover():
    now = [100.0]
    pool = ApiKeyPool.from_environment(
        "OPENAI",
        {"OPENAI_API_KEY": "key-1", "OPENAI_API_FALLBACK_KEY": "key-2"},
        clock=lambda: now[0],
        cooldown_seconds=30.0,
    )
    first = pool.next_key()
    assert first.api_key == "key-1"
    pool.mark_quota_limited(first)

    # Key 1 is on cooldown, key 2 returned
    second = pool.next_key()
    assert second.api_key == "key-2"

    # Both key 1 and key 2 (after rotation) check: if we mark key 2 on cooldown as well
    pool.mark_quota_limited(second)

    # All keys on cooldown -> ApiKeysExhausted
    with pytest.raises(ApiKeysExhausted):
        pool.next_key()

    # Fast forward clock past 30 seconds
    now[0] += 31.0
    assert pool.next_key().api_key == "key-1"


def test_empty_pool_raises():
    pool = ApiKeyPool.from_environment("CUSTOM", {})
    assert pool.key_count == 0
    with pytest.raises(ApiKeysExhausted):
        pool.next_key()
