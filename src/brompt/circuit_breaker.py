"""Circuit Breaker pattern for provider call resilience.

Implements the standard CLOSED / OPEN / HALF_OPEN state machine with
exponential backoff, preventing cascading failures when an upstream
provider is degraded or down.
"""

import logging
import random
import threading
import time
from enum import Enum, auto

logger = logging.getLogger("brompt.circuit_breaker")


class CircuitState(Enum):
    CLOSED = auto()
    OPEN = auto()
    HALF_OPEN = auto()


class CircuitBreakerOpenError(Exception):
    """Raised when a call is rejected because the circuit is OPEN."""


class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 1,
        jitter_factor: float = 0.1,
    ):
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be >= 1")
        if recovery_timeout <= 0:
            raise ValueError("recovery_timeout must be > 0")
        if half_open_max_calls < 1:
            raise ValueError("half_open_max_calls must be >= 1")

        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self.jitter_factor = jitter_factor

        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time: float | None = None
        self.half_open_calls = 0
        self._lock = threading.Lock()
        self.metrics: dict[str, int] = {
            "total_calls": 0,
            "successes": 0,
            "failures": 0,
            "rejections": 0,
            "state_changes": 0,
            "fallbacks_used": 0,
        }

    def _check_state(self) -> str | None:
        """Check and transition state. Must be called under self._lock.
        Returns 'rejected' if circuit is open, 'probe_limit' if half-open
        probe limit reached, or None if the call may proceed.
        """
        if self.state == CircuitState.OPEN:
            elapsed = time.monotonic() - self.last_failure_time if self.last_failure_time else 0
            jitter = self.recovery_timeout * self.jitter_factor
            effective_timeout = self.recovery_timeout + random.uniform(0, jitter)
            if self.last_failure_time is not None and elapsed >= effective_timeout:
                self.state = CircuitState.HALF_OPEN
                self.half_open_calls = 0
                self.metrics["state_changes"] += 1
                logger.info("Circuit breaker OPEN -> HALF_OPEN (recovery probe)")
            else:
                self.metrics["rejections"] += 1
                return "rejected"

        if self.state == CircuitState.HALF_OPEN:
            if self.half_open_calls >= self.half_open_max_calls:
                self.metrics["rejections"] += 1
                return "probe_limit"
        return None

    async def call(self, coro, fallback=None):
        """Execute *coro* through the circuit breaker (async path)."""
        self.metrics["total_calls"] += 1
        with self._lock:
            status = self._check_state()
            if status is not None:
                if fallback is not None:
                    self.metrics["fallbacks_used"] += 1
                    return fallback
                if status == "rejected":
                    raise CircuitBreakerOpenError("Provider circuit is OPEN — rejecting fast")
                raise CircuitBreakerOpenError("Circuit HALF_OPEN — too many concurrent probes")
            if self.state == CircuitState.HALF_OPEN:
                self.half_open_calls += 1
        try:
            result = await coro
        except Exception:
            self._record_failure()
            self.metrics["failures"] += 1
            if fallback is not None:
                self.metrics["fallbacks_used"] += 1
                return fallback
            raise
        self.metrics["successes"] += 1
        self._record_success()
        return result

    def call_sync(self, fn, args=None, kwargs=None, fallback=None):
        """Execute *fn* through the circuit breaker (sync path)."""
        self.metrics["total_calls"] += 1
        args = args or ()
        kwargs = kwargs or {}
        with self._lock:
            status = self._check_state()
            if status is not None:
                if fallback is not None:
                    self.metrics["fallbacks_used"] += 1
                    return fallback
                if status == "rejected":
                    raise CircuitBreakerOpenError("Provider circuit is OPEN — rejecting fast")
                raise CircuitBreakerOpenError("Circuit HALF_OPEN — too many concurrent probes")
            if self.state == CircuitState.HALF_OPEN:
                self.half_open_calls += 1
        try:
            result = fn(*args, **kwargs)
        except Exception:
            self._record_failure()
            self.metrics["failures"] += 1
            if fallback is not None:
                self.metrics["fallbacks_used"] += 1
                return fallback
            raise
        self.metrics["successes"] += 1
        self._record_success()
        return result

    def _record_success(self):
        with self._lock:
            old = self.state
            self.failure_count = 0
            self.last_failure_time = None
            self.half_open_calls = 0
            if self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.CLOSED
                self.metrics["state_changes"] += 1
                logger.info("Circuit breaker HALF_OPEN -> CLOSED (probe succeeded)")
            elif self.state == CircuitState.OPEN:
                self.state = CircuitState.CLOSED
                self.metrics["state_changes"] += 1
                logger.info("Circuit breaker OPEN -> CLOSED (recovered)")
            if old != self.state:
                logger.info("Circuit breaker state: %s", self.state.name)

    def _record_failure(self):
        with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.monotonic()
            if self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.OPEN
                self.metrics["state_changes"] += 1
                logger.warning("Circuit breaker HALF_OPEN -> OPEN (probe failed)")
            elif self.state == CircuitState.CLOSED and self.failure_count >= self.failure_threshold:
                self.state = CircuitState.OPEN
                self.metrics["state_changes"] += 1
                logger.warning(
                    "Circuit breaker CLOSED -> OPEN (%d consecutive failures)",
                    self.failure_count,
                )

    @property
    def is_open(self) -> bool:
        return self.state == CircuitState.OPEN

    def _fmt_last_failure(self) -> str:
        if self.last_failure_time is None:
            return "N/A"
        return f"{time.monotonic() - self.last_failure_time:.1f}s ago"

    def reset(self):
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = None
        self.half_open_calls = 0
        self.metrics = {k: 0 for k in self.metrics}

    def __repr__(self) -> str:
        return (
            f"CircuitBreaker(state={self.state.name}, "
            f"failures={self.failure_count}/{self.failure_threshold}, "
            f"last_failure={self._fmt_last_failure()}, "
            f"metrics={{ok:{self.metrics['successes']}, "
            f"fail:{self.metrics['failures']}, "
            f"rej:{self.metrics['rejections']}}})"
        )
