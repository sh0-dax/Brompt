"""Tests for the CircuitBreaker pattern."""

import asyncio
import time

import pytest

from brompt.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError, CircuitState


class TestCircuitBreaker:
    def test_closed_by_default(self):
        cb = CircuitBreaker()
        assert cb.state == CircuitState.CLOSED
        assert not cb.is_open
        assert cb.failure_count == 0

    def test_invalid_params(self):
        with pytest.raises(ValueError):
            CircuitBreaker(failure_threshold=0)
        with pytest.raises(ValueError):
            CircuitBreaker(recovery_timeout=0)
        with pytest.raises(ValueError):
            CircuitBreaker(half_open_max_calls=0)

    @pytest.mark.asyncio
    async def test_successful_call_resets_failures(self):
        cb = CircuitBreaker(failure_threshold=3)

        async def ok():
            return "ok"

        result = await cb.call(ok())
        assert result == "ok"
        assert cb.failure_count == 0
        assert cb.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_failures_trip_open(self):
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=60)

        async def fail():
            raise ValueError("boom")

        for _ in range(3):
            with pytest.raises(ValueError):
                await cb.call(fail())

        assert cb.state == CircuitState.OPEN
        assert cb.failure_count == 3

    @pytest.mark.asyncio
    async def test_open_circuit_rejects_fast(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=60)
        cb.state = CircuitState.OPEN
        cb.failure_count = 2
        cb.last_failure_time = time.monotonic()

        async def ok():
            return "should not reach"

        with pytest.raises(CircuitBreakerOpenError):
            await cb.call(ok())

    @pytest.mark.asyncio
    async def test_open_circuit_returns_fallback(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=60)
        cb.state = CircuitState.OPEN
        cb.failure_count = 2
        cb.last_failure_time = time.monotonic()

        async def ok():
            return "should not reach"

        result = await cb.call(ok(), fallback="fallback_value")
        assert result == "fallback_value"

    @pytest.mark.asyncio
    async def test_recovery_probe_on_timeout(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.05)

        async def fail():
            raise ValueError("first call fails")

        async def succeed():
            return "recovered"

        with pytest.raises(ValueError):
            await cb.call(fail())
        assert cb.state == CircuitState.OPEN

        await asyncio.sleep(0.06)

        result = await cb.call(succeed())
        assert result == "recovered"
        assert cb.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_half_open_limits_concurrent_probes(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.05, half_open_max_calls=1)

        async def fail():
            raise ValueError("fail")

        with pytest.raises(ValueError):
            await cb.call(fail())

        await asyncio.sleep(0.06)

        async def slow():
            await asyncio.sleep(0.1)
            return "ok"

        results = []
        errors = []

        async def call_one():
            try:
                r = await cb.call(slow())
                results.append(r)
            except CircuitBreakerOpenError:
                errors.append("rejected")

        await asyncio.gather(call_one(), call_one())
        assert len(results) == 1
        assert len(errors) == 1

    def test_call_sync_success(self):
        cb = CircuitBreaker(failure_threshold=3)

        def ok():
            return "sync_ok"

        result = cb.call_sync(ok)
        assert result == "sync_ok"
        assert cb.state == CircuitState.CLOSED

    def test_call_sync_trips_open(self):
        cb = CircuitBreaker(failure_threshold=2)

        def fail():
            raise RuntimeError("sync fail")

        with pytest.raises(RuntimeError):
            cb.call_sync(fail)
        with pytest.raises(RuntimeError):
            cb.call_sync(fail)
        assert cb.state == CircuitState.OPEN

    def test_call_sync_fallback(self):
        cb = CircuitBreaker(failure_threshold=1)

        def fail():
            raise RuntimeError("fail")

        result = cb.call_sync(fail, fallback="sync_fallback")
        assert result == "sync_fallback"

    def test_reset(self):
        cb = CircuitBreaker(failure_threshold=1)
        cb.state = CircuitState.OPEN
        cb.failure_count = 5
        cb.last_failure_time = time.monotonic()
        cb.half_open_calls = 2

        cb.reset()
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0
        assert cb.last_failure_time is None
        assert cb.half_open_calls == 0

    def test_repr(self):
        cb = CircuitBreaker()
        r = repr(cb)
        assert "CircuitBreaker" in r
        assert "CLOSED" in r
