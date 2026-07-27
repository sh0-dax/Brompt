"""Unit tests for the distributed (Redis-backed) rate limiter.

Uses fakeredis (with real Lua execution via the 'lua' extra) so these
tests exercise the actual atomic script without requiring a live Redis.
"""

import pytest

fakeredis = pytest.importorskip("fakeredis")

from brompt.ratelimit import RateLimitExceededError, RedisRateLimiter


class TestRedisRateLimiter:
    def _client(self):
        return fakeredis.FakeStrictRedis()

    def test_allows_within_budget(self):
        rl = RedisRateLimiter(self._client(), max_requests=3, window_seconds=60)
        rl.check("user1")
        rl.check("user1")
        rl.check("user1")

    def test_blocks_over_budget(self):
        rl = RedisRateLimiter(self._client(), max_requests=2, window_seconds=60)
        rl.check("user1")
        rl.check("user1")
        with pytest.raises(RateLimitExceededError):
            rl.check("user1")

    def test_isolated_per_identifier(self):
        rl = RedisRateLimiter(self._client(), max_requests=1, window_seconds=60)
        rl.check("user1")
        rl.check("user2")

    def test_shared_across_two_limiter_instances_same_redis(self):
        """Two separate RedisRateLimiter objects sharing one Redis
        must share the same budget."""
        client = self._client()
        rl_a = RedisRateLimiter(client, max_requests=2, window_seconds=60)
        rl_b = RedisRateLimiter(client, max_requests=2, window_seconds=60)
        rl_a.check("shared-user")
        rl_b.check("shared-user")
        with pytest.raises(RateLimitExceededError):
            rl_a.check("shared-user")

    def test_invalid_max_requests(self):
        with pytest.raises(ValueError):
            RedisRateLimiter(self._client(), max_requests=0)

    def test_invalid_window(self):
        with pytest.raises(ValueError):
            RedisRateLimiter(self._client(), window_seconds=0)
