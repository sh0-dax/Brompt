"""Unit tests for the shared retry-with-backoff helper used by every cloud
provider (Anthropic, OpenAI, Gemini, Azure OpenAI, Mistral) -- previously
this logic only existed inside GeminiProvider."""

import pytest

from brompt.providers import _is_rate_limit_error, _retry_async, _retry_sync


class FakeRateLimitError(Exception):
    def __init__(self):
        super().__init__("429 Too Many Requests")


class TestIsRateLimitError:
    def test_detects_429_in_message(self):
        assert _is_rate_limit_error(Exception("Error: 429 rate limited")) is True

    def test_detects_resource_exhausted(self):
        assert _is_rate_limit_error(Exception("RESOURCE_EXHAUSTED")) is True

    def test_detects_code_attribute(self):
        exc = Exception("boom")
        exc.code = 429
        assert _is_rate_limit_error(exc) is True

    def test_detects_status_code_attribute(self):
        exc = Exception("boom")
        exc.status_code = 429
        assert _is_rate_limit_error(exc) is True

    def test_unrelated_error_not_flagged(self):
        assert _is_rate_limit_error(Exception("connection refused")) is False


class TestRetrySync:
    def test_succeeds_first_try_no_retry(self):
        calls = []

        def call():
            calls.append(1)
            return "ok"

        assert _retry_sync(call, "TestProvider") == "ok"
        assert len(calls) == 1

    def test_retries_on_rate_limit_then_succeeds(self, monkeypatch):
        monkeypatch.setattr("brompt.providers.time.sleep", lambda _: None)
        attempts = {"n": 0}

        def call():
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise FakeRateLimitError()
            return "recovered"

        assert _retry_sync(call, "TestProvider") == "recovered"
        assert attempts["n"] == 3

    def test_non_rate_limit_error_raises_immediately(self):
        calls = []

        def call():
            calls.append(1)
            raise ValueError("not a rate limit issue")

        with pytest.raises(ValueError):
            _retry_sync(call, "TestProvider")
        assert len(calls) == 1

    def test_exhausts_retries_and_raises(self, monkeypatch):
        monkeypatch.setattr("brompt.providers.time.sleep", lambda _: None)

        def call():
            raise FakeRateLimitError()

        with pytest.raises(FakeRateLimitError):
            _retry_sync(call, "TestProvider")


class TestRetryAsync:
    @pytest.mark.asyncio
    async def test_succeeds_first_try_no_retry(self):
        calls = []

        async def call():
            calls.append(1)
            return "ok"

        assert await _retry_async(call, "TestProvider") == "ok"
        assert len(calls) == 1

    @pytest.mark.asyncio
    async def test_retries_on_rate_limit_then_succeeds(self, monkeypatch):
        async def fake_sleep(_):
            return None

        monkeypatch.setattr("brompt.providers.asyncio.sleep", fake_sleep)
        attempts = {"n": 0}

        async def call():
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise FakeRateLimitError()
            return "recovered"

        assert await _retry_async(call, "TestProvider") == "recovered"
        assert attempts["n"] == 3

    @pytest.mark.asyncio
    async def test_non_rate_limit_error_raises_immediately(self):
        async def call():
            raise ValueError("not a rate limit issue")

        with pytest.raises(ValueError):
            await _retry_async(call, "TestProvider")
