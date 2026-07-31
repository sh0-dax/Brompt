"""Rate limiting: in-process (single instance) and Redis-backed (distributed).

Both implementations expose the same ``check(identifier)`` interface and
raise ``RateLimitExceededError``, so ``BromptEngine`` can be handed either
one interchangeably.
"""

import threading
import time
from collections import deque
from typing import Protocol


class RateLimitExceededError(Exception):
    """Raised when a caller exceeds the configured request rate."""


class RateLimiterBackend(Protocol):
    """Interface shared by in-process and distributed rate limiters."""

    def check(self, identifier: str = "default") -> None: ...


class RateLimiter:
    """Thread-safe sliding-window rate limiter, in-process only.

    State lives in this process's memory, so this bounds abuse from a
    single running instance. A multi-instance deployment needs shared
    state -- use ``RedisRateLimiter`` for that case.
    """

    def __init__(self, max_requests: int = 30, window_seconds: float = 60.0):
        if max_requests < 1:
            raise ValueError("max_requests must be >= 1")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be > 0")
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()
        self._last_cleanup = 0.0

    def check(self, identifier: str = "default") -> None:
        """Registers a hit and raises if the window's request budget is exhausted."""
        now = time.monotonic()
        with self._lock:
            if now - self._last_cleanup >= self.window_seconds:
                self._last_cleanup = now
                cutoff = now - self.window_seconds
                for key in list(self._hits):
                    q = self._hits[key]
                    while q and q[0] < cutoff:
                        q.popleft()
                    if not q:
                        del self._hits[key]
            window = self._hits.setdefault(identifier, deque())
            cutoff = now - self.window_seconds
            while window and window[0] < cutoff:
                window.popleft()
            if len(window) >= self.max_requests:
                raise RateLimitExceededError(
                    f"Rate limit exceeded: {self.max_requests} requests "
                    f"per {self.window_seconds:.0f}s for '{identifier}'."
                )
            window.append(now)


# Atomically: drop expired entries, count what's left, admit or reject
# -- all in one round trip so concurrent requests from different instances
# can't race past the limit.
_SLIDING_WINDOW_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member = ARGV[4]

redis.call('ZREMRANGEBYSCORE', key, '-inf', now - window)
local count = redis.call('ZCARD', key)
if count >= limit then
    return 0
end
redis.call('ZADD', key, now, member)
redis.call('EXPIRE', key, math.ceil(window))
return 1
"""


class RedisRateLimiter:
    """Distributed sliding-window rate limiter backed by Redis.

    Safe across multiple replicas because the check-and-increment happens
    atomically inside a single Lua script executed by the Redis server.

    Requires the ``redis`` package (``pip install brompt-engine[redis]``)
    and a reachable Redis server.
    """

    def __init__(
        self,
        redis_client,
        max_requests: int = 30,
        window_seconds: float = 60.0,
        key_prefix: str = "brompt:ratelimit:",
    ):
        if max_requests < 1:
            raise ValueError("max_requests must be >= 1")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be > 0")
        self._redis = redis_client
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.key_prefix = key_prefix
        self._script = redis_client.register_script(_SLIDING_WINDOW_LUA)

    def check(self, identifier: str = "default") -> None:
        now = time.time()
        key = f"{self.key_prefix}{identifier}"
        member = f"{now}:{threading.get_ident()}"
        admitted = self._script(keys=[key], args=[now, self.window_seconds, self.max_requests, member])
        if not admitted:
            raise RateLimitExceededError(
                f"Rate limit exceeded: {self.max_requests} requests "
                f"per {self.window_seconds:.0f}s for '{identifier}' (distributed)."
            )
