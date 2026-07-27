"""Simple in-process rate limiting (sliding window, per-identifier)."""

import threading
import time
from collections import deque


class RateLimitExceededError(Exception):
    """Raised when a caller exceeds the configured request rate."""


class RateLimiter:
    """Thread-safe sliding-window rate limiter.

    Not distributed -- state lives in process memory, so this bounds abuse
    from a single running instance only. A multi-instance deployment needs a
    shared store (Redis, etc).
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

    def check(self, identifier: str = "default") -> None:
        """Registers a hit and raises if the window's request budget is exhausted."""
        now = time.monotonic()
        with self._lock:
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
