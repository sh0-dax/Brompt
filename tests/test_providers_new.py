"""Tests for the new async provider retry helper and provider instantiation."""

import pytest

from brompt.providers.base import is_rate_limit_error


class TestIsRateLimitError:
    def test_detects_429_in_message(self):
        assert is_rate_limit_error(RuntimeError("429 Too Many Requests"))

    def test_detects_resource_exhausted(self):
        assert is_rate_limit_error(RuntimeError("resource_exhausted"))

    def test_detects_code_attribute(self):
        exc = RuntimeError("some error")
        exc.code = 429
        assert is_rate_limit_error(exc)

    def test_detects_status_code_attribute(self):
        exc = RuntimeError("some error")
        exc.status_code = 429
        assert is_rate_limit_error(exc)

    def test_unrelated_error_not_flagged(self):
        assert not is_rate_limit_error(RuntimeError("invalid api key"))
        assert not is_rate_limit_error(ValueError("bad value"))


class TestRetryAsyncCall:
    @pytest.mark.asyncio
    async def test_succeeds_first_try_no_retry(self):
        from brompt.providers.base import retry_async_call

        call_count = 0

        async def ok():
            nonlocal call_count
            call_count += 1
            return "done"

        result = await retry_async_call(ok, "TestProvider")
        assert result == "done"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retries_on_rate_limit_then_succeeds(self):
        from brompt.providers.base import retry_async_call

        call_count = 0

        async def flaky():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                exc = RuntimeError("429 rate_limit")
                raise exc
            return "done"

        result = await retry_async_call(flaky, "TestProvider")
        assert result == "done"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_non_rate_limit_error_raises_immediately(self):
        from brompt.providers.base import retry_async_call

        async def fail():
            raise RuntimeError("invalid credentials")

        with pytest.raises(RuntimeError, match="invalid credentials"):
            await retry_async_call(fail, "TestProvider")

    @pytest.mark.asyncio
    async def test_exhausts_retries_and_raises(self):
        from brompt.providers.base import _MAX_RETRIES, retry_async_call

        call_count = 0

        async def always_429():
            nonlocal call_count
            call_count += 1
            raise RuntimeError("429 rate_limit")

        with pytest.raises(RuntimeError, match="429 rate_limit"):
            await retry_async_call(always_429, "TestProvider")

        assert call_count == _MAX_RETRIES + 1

    @pytest.mark.asyncio
    async def test_toomanyrequests_detected(self):
        from brompt.providers.base import retry_async_call

        call_count = 0

        async def flaky():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("toomanyrequests")
            return "ok"

        result = await retry_async_call(flaky, "TestProvider")
        assert result == "ok"
        assert call_count == 2
