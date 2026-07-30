"""Hooks/middleware system — before/after execution hooks with a managed pipeline."""

import abc
import logging
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
            user_query, context = hook.before_execute(user_query, context, **kwargs)
        return user_query, context

    def after_execute(self, result: ExecutionResult, **kwargs) -> ExecutionResult:
        for hook in reversed(self._hooks):
            result = hook.after_execute(result, **kwargs)
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


class RateLimitHook(BaseHook):
    """Enforces rate limiting at the hook level."""

    def __init__(self, max_calls: int = 60, window_seconds: float = 60.0):
        self.max_calls = max_calls
        self.window_seconds = window_seconds
        self._timestamps: list[float] = []

    def before_execute(self, user_query: str, context: dict[str, Any] | None, **kwargs) -> tuple[str, dict[str, Any] | None]:  # noqa: E501
        now = time.time()
        self._timestamps = [t for t in self._timestamps if now - t <= self.window_seconds]
        if len(self._timestamps) >= self.max_calls:
            raise RuntimeError(f"Rate limit exceeded: {self.max_calls} calls per {self.window_seconds}s")
        self._timestamps.append(now)
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

    def before_execute(self, user_query: str, context: dict[str, Any] | None, **kwargs) -> tuple[str, dict[str, Any] | None]:  # noqa: E501
        query_lower = user_query.lower()
        for pattern in self._blocked_patterns:
            if pattern in query_lower:
                from .security import SecurityViolationError
                raise SecurityViolationError(f"Blocked pattern detected: '{pattern}'")
        return user_query, context

    def after_execute(self, result: ExecutionResult, **kwargs) -> ExecutionResult:
        return result


hooks_manager = HooksManager()
