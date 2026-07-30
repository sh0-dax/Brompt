"""Mistral AI provider — async provider using mistralai SDK."""

import time
from typing import Optional, AsyncIterator

from .base import LLMProvider, ProviderResult, ProviderOutcome, retry_async_call


class MistralProvider(LLMProvider):
    def _setup_client(self):
        try:
            from mistralai import Mistral
            self._client = Mistral(api_key=self.api_key)
        except ImportError:
            raise ImportError("pip install mistralai")
        except Exception as e:
            raise RuntimeError(f"Mistral client init failed: {e}")

    async def generate(self, prompt: str, **kwargs) -> ProviderResult:
        start_time = time.time()
        try:
            msgs = [{"role": "user", "content": prompt}]
            system = kwargs.get("system")
            if system:
                msgs.insert(0, {"role": "system", "content": system})
            response = await retry_async_call(
                lambda: self._client.chat.complete_async(
                    model=self.model,
                    messages=msgs,
                    temperature=kwargs.get("temperature", 0.7),
                    max_tokens=kwargs.get("max_tokens", 4096),
                    top_p=kwargs.get("top_p", 1.0),
                ),
                "Mistral",
            )
            latency_ms = (time.time() - start_time) * 1000
            choice = response.choices[0]
            usage = response.usage
            return ProviderResult(
                text=choice.message.content or "",
                model=self.model,
                outcome=ProviderOutcome.SUCCESS,
                tokens_used=usage.total_tokens if usage else 0,
                prompt_tokens=usage.prompt_tokens if usage else 0,
                completion_tokens=usage.completion_tokens if usage else 0,
                latency_ms=latency_ms,
                finish_reason=choice.finish_reason,
            )
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            error_str = str(e).lower()
            if "rate_limit" in error_str:
                outcome = ProviderOutcome.RATE_LIMITED
            elif "content_filter" in error_str:
                outcome = ProviderOutcome.CONTENT_FILTERED
            elif "timeout" in error_str:
                outcome = ProviderOutcome.TIMEOUT
            else:
                outcome = ProviderOutcome.ERROR
            return ProviderResult(
                text="", model=self.model, outcome=outcome,
                latency_ms=latency_ms, error=str(e),
            )

    async def stream(self, prompt: str, **kwargs) -> AsyncIterator[str]:
        try:
            msgs = [{"role": "user", "content": prompt}]
            system = kwargs.get("system")
            if system:
                msgs.insert(0, {"role": "system", "content": system})
            stream = await self._client.chat.stream_async(
                model=self.model,
                messages=msgs,
                temperature=kwargs.get("temperature", 0.7),
                max_tokens=kwargs.get("max_tokens", 4096),
            )
            async for chunk in stream:
                if chunk.data.choices[0].delta.content:
                    yield chunk.data.choices[0].delta.content
        except Exception as e:
            yield f"[Error: {e}]"

    async def validate_api_key(self) -> bool:
        try:
            await self._client.chat.complete_async(
                model=self.model, messages=[{"role": "user", "content": "hi"}], max_tokens=1
            )
            return True
        except Exception:
            return False
