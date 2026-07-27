"""Unit tests for the rate limiter."""

import pytest

from brompt.ratelimit import RateLimiter, RateLimitExceededError


class TestRateLimiter:
    def test_allows_within_budget(self):
        rl = RateLimiter(max_requests=3, window_seconds=60)
        rl.check("user1")
        rl.check("user1")
        rl.check("user1")

    def test_blocks_over_budget(self):
        rl = RateLimiter(max_requests=2, window_seconds=60)
        rl.check("user1")
        rl.check("user1")
        with pytest.raises(RateLimitExceededError):
            rl.check("user1")

    def test_isolated_per_identifier(self):
        rl = RateLimiter(max_requests=1, window_seconds=60)
        rl.check("user1")
        rl.check("user2")

    def test_invalid_max_requests(self):
        with pytest.raises(ValueError):
            RateLimiter(max_requests=0)

    def test_invalid_window(self):
        with pytest.raises(ValueError):
            RateLimiter(window_seconds=0)
