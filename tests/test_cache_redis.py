"""Tests for RedisCache using fakeredis."""

import pytest

from brompt.widget import LRUCache, PromptResult, RedisCache


@pytest.fixture
def fakeredis_client():
    try:
        import fakeredis
        return fakeredis.FakeStrictRedis(decode_responses=True)
    except ImportError:
        pytest.skip("fakeredis not installed")


class TestRedisCache:
    def test_init(self, fakeredis_client):
        cache = RedisCache(fakeredis_client)
        assert cache.hit_rate == 0.0

    def test_set_and_get(self, fakeredis_client):
        cache = RedisCache(fakeredis_client)
        result = PromptResult(
            user_input="hello",
            generated_prompt="say hello back",
            response="hi there",
            template_id="default",
            model="gpt-4",
        )
        cache.set("hello", "default", "gpt-4", None, result)

        cached = cache.get("hello", "default", "gpt-4", None)
        assert cached is not None
        assert cached.response == "hi there"
        assert cached.cached is True

    def test_cache_miss(self, fakeredis_client):
        cache = RedisCache(fakeredis_client)
        result = cache.get("nonexistent", "default", "gpt-4", None)
        assert result is None

    def test_diff_model_differs(self, fakeredis_client):
        cache = RedisCache(fakeredis_client)
        result = PromptResult(
            user_input="hello",
            generated_prompt="say hello",
            response="hi",
            template_id="default",
            model="gpt-4",
        )
        cache.set("hello", "default", "gpt-4", None, result)
        cached_gpt4 = cache.get("hello", "default", "gpt-4", None)
        cached_other = cache.get("hello", "default", "claude", None)

        assert cached_gpt4 is not None
        assert cached_other is None

    def test_hit_rate(self, fakeredis_client):
        cache = RedisCache(fakeredis_client)
        result = PromptResult(
            user_input="hit1",
            generated_prompt="",
            response="hit1 response",
            template_id="t1",
            model="gpt-4",
        )
        cache.set("hit1", "t1", "gpt-4", None, result)

        cache.get("hit1", "t1", "gpt-4", None)
        cache.get("miss", "t1", "gpt-4", None)
        cache.get("miss2", "t1", "gpt-4", None)

        assert cache.hit_rate == pytest.approx(1 / 3, rel=0.01)

    def test_clear(self, fakeredis_client):
        cache = RedisCache(fakeredis_client)
        result = PromptResult(
            user_input="x",
            generated_prompt="",
            response="y",
            template_id="t",
            model="gpt-4",
        )
        cache.set("x", "t", "gpt-4", None, result)
        assert cache.get("x", "t", "gpt-4", None) is not None
        cache.clear()
        assert cache.get("x", "t", "gpt-4", None) is None

    def test_ttl_expiry(self, fakeredis_client):
        cache = RedisCache(fakeredis_client, default_ttl=1)
        result = PromptResult(
            user_input="temp",
            generated_prompt="",
            response="temp response",
            template_id="t",
            model="gpt-4",
        )
        cache.set("temp", "t", "gpt-4", None, result)

        import time
        time.sleep(1.1)
        fakeredis_client.time = lambda: None

        cached = cache.get("temp", "t", "gpt-4", None)
        assert cached is None

    def test_lru_cache_signature(self):
        lru = LRUCache(max_entries=10, ttl_seconds=60)
        result = PromptResult(
            user_input="test", generated_prompt="", response="test response",
            template_id="t", model="gpt-4",
        )
        lru.set("test", "t", None, result)
        cached = lru.get("test", "t", None)
        assert cached is not None
        assert cached.response == "test response"
