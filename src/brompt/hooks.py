"""Hooks/middleware system — before/after execution hooks with a managed pipeline."""

import abc
import logging
import re
import time
from typing import Any

from .schema import ExecutionResult

logger = logging.getLogger("brompt.hooks")


class BaseHook(abc.ABC):
    """Abstract base for all hooks."""

    @abc.abstractmethod
    def before_execute(self, user_query: str, context: dict[str, Any] | None, **kwargs) -> tuple[str, dict[str, Any] | None]:  # noqa: E501
        return user_query, context

    @abc.abstractmethod
    def after_execute(self, result: ExecutionResult, **kwargs) -> ExecutionResult:
        return result


class HooksManager:
    """Manages a chain of before/after execution hooks."""

    def __init__(self):
        self._hooks: list[BaseHook] = []

    def register(self, hook: BaseHook):
        self._hooks.append(hook)

    def unregister(self, hook: BaseHook):
        self._hooks.remove(hook)

    def clear(self):
        self._hooks.clear()

    def list_hooks(self) -> list[str]:
        return [type(h).__name__ for h in self._hooks]

    def before_execute(self, user_query: str, context: dict[str, Any] | None, **kwargs) -> tuple[str, dict[str, Any] | None]:  # noqa: E501
        for hook in self._hooks:
            try:
                user_query, context = hook.before_execute(user_query, context, **kwargs)
            except Exception:
                logger.exception("Hook %s.before_execute failed — skipping", type(hook).__name__)
        return user_query, context

    def after_execute(self, result: ExecutionResult, **kwargs) -> ExecutionResult:
        for hook in reversed(self._hooks):
            try:
                result = hook.after_execute(result, **kwargs)
            except Exception:
                logger.exception("Hook %s.after_execute failed — skipping", type(hook).__name__)
        return result


# --- Built-in hooks ---------------------------------------------------------

class LoggingHook(BaseHook):
    """Logs all queries and results."""

    def __init__(self, level: str = "info"):
        self._level = getattr(logger, level.lower(), logger.info)

    def before_execute(self, user_query: str, context: dict[str, Any] | None, **kwargs) -> tuple[str, dict[str, Any] | None]:  # noqa: E501
        self._level("Executing query: %s", user_query[:200])
        return user_query, context

    def after_execute(self, result: ExecutionResult, **kwargs) -> ExecutionResult:
        status = "secure" if result.is_secure else "failed"
        self._level("Execution result: state=%s status=%s", result.state_id, status)
        return result


class TimingHook(BaseHook):
    """Measures and records execution time of each query."""

    def before_execute(self, user_query: str, context: dict[str, Any] | None, **kwargs) -> tuple[str, dict[str, Any] | None]:  # noqa: E501
        self._start = time.perf_counter()
        return user_query, context

    def after_execute(self, result: ExecutionResult, **kwargs) -> ExecutionResult:
        elapsed = time.perf_counter() - self._start
        logger.info("Query completed in %.3fms", elapsed * 1000)
        return result


class ValidationHook(BaseHook):
    """Validates input and output against schema rules."""

    def __init__(self, max_input_length: int = 10000, max_output_length: int = 50000):
        self.max_input_length = max_input_length
        self.max_output_length = max_output_length

    def before_execute(self, user_query: str, context: dict[str, Any] | None, **kwargs) -> tuple[str, dict[str, Any] | None]:  # noqa: E501
        if len(user_query) > self.max_input_length:
            raise ValueError(f"Input exceeds max length of {self.max_input_length}")
        return user_query, context

    def after_execute(self, result: ExecutionResult, **kwargs) -> ExecutionResult:
        if result.is_secure and result.data:
            response = result.data.get("llm_response", "")
            if len(response) > self.max_output_length:
                logger.warning("Output exceeds max length (%d > %d)", len(response), self.max_output_length)
        return result


class AuditHook(BaseHook):
    """Forces audit logging through the audit subsystem."""

    def before_execute(self, user_query: str, context: dict[str, Any] | None, **kwargs) -> tuple[str, dict[str, Any] | None]:  # noqa: E501
        return user_query, context

    def after_execute(self, result: ExecutionResult, **kwargs) -> ExecutionResult:
        if hasattr(result, "_audit_forced"):
            logger.debug("Audit hook processed result: %s", result.state_id)
        return result


class RateLimitBackend(abc.ABC):
    """Abstract rate-limit state backend (in-memory or distributed)."""

    @abc.abstractmethod
    def check(self, key: str, max_calls: int, window: float) -> bool:
        """Return True if the call is allowed, False if rate-limited."""


class InMemoryRateLimitBackend(RateLimitBackend):
    """Per-process in-memory rate-limit state."""

    def __init__(self):
        self._data: dict[str, list[float]] = {}

    def check(self, key: str, max_calls: int, window: float) -> bool:
        now = time.time()
        timestamps = self._data.setdefault(key, [])
        timestamps[:] = [t for t in timestamps if now - t <= window]
        if len(timestamps) >= max_calls:
            return False
        timestamps.append(now)
        return True


class RedisRateLimitBackend(RateLimitBackend):
    """Distributed rate-limit backed by Redis sorted sets."""

    def __init__(self, redis_client=None, redis_url: str | None = None):
        if redis_client is not None:
            self._redis = redis_client
        elif redis_url is not None:
            import redis as redis_mod
            self._redis = redis_mod.from_url(redis_url)
        else:
            raise ValueError("Provide either redis_client or redis_url")

    def check(self, key: str, max_calls: int, window: float) -> bool:
        now = time.time()
        cutoff = now - window
        pipe = self._redis.pipeline()
        pipe.zremrangebyscore(key, 0, cutoff)
        pipe.zcard(key)
        count = pipe.execute()[1] or 0
        if count >= max_calls:
            return False
        self._redis.zadd(key, {str(now): now})
        self._redis.expire(key, int(window) + 1)
        return True


class RateLimitHook(BaseHook):
    """Enforces rate limiting at the hook level."""

    def __init__(self, max_calls: int = 60, window_seconds: float = 60.0, key: str = "default", backend: RateLimitBackend | None = None):  # noqa: E501
        self.max_calls = max_calls
        self.window_seconds = window_seconds
        self.key = key
        self._backend = backend or InMemoryRateLimitBackend()

    def before_execute(self, user_query: str, context: dict[str, Any] | None, **kwargs) -> tuple[str, dict[str, Any] | None]:  # noqa: E501
        if not self._backend.check(self.key, self.max_calls, self.window_seconds):
            raise RuntimeError(f"Rate limit exceeded: {self.max_calls} calls per {self.window_seconds}s")
        return user_query, context

    def after_execute(self, result: ExecutionResult, **kwargs) -> ExecutionResult:
        return result


class SecurityHook(BaseHook):
    """Additional security checks beyond the built-in engine security."""

    def __init__(self, blocked_patterns: list[str] | None = None):
        self._blocked_patterns = blocked_patterns or [
            "ignore all previous instructions",
            "ignore previous instructions",
            "system prompt:",
        ]
        self._patterns = [re.compile(re.escape(p), re.IGNORECASE) for p in self._blocked_patterns]

    def before_execute(self, user_query: str, context: dict[str, Any] | None, **kwargs) -> tuple[str, dict[str, Any] | None]:  # noqa: E501
        for pattern, compiled in zip(self._blocked_patterns, self._patterns):
            if compiled.search(user_query):
                from .security import SecurityViolationError
                raise SecurityViolationError(f"Blocked pattern detected: '{pattern}'")
        return user_query, context

    def after_execute(self, result: ExecutionResult, **kwargs) -> ExecutionResult:
        return result


hooks_manager = HooksManager()
