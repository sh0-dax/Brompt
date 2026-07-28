"""Anthropic (Claude) Provider."""

import time
from typing import Optional, AsyncIterator

from .base import LLMProvider, ProviderResult, ProviderOutcome


class AnthropicProvider(LLMProvider):
    def _setup_client(self):
        try:
            from anthropic import AsyncAnthropic
            self._client = AsyncAnthropic(api_key=self.api_key)
        except ImportError:
            raise ImportError("pip install anthropic")
        except Exception as e:
            raise RuntimeError(f"Anthropic client init failed: {e}")

    async def generate(self, prompt: str, **kwargs) -> ProviderResult:
        start_time = time.time()
        try:
            response = await self._client.messages.create(
                model=self.model,
                max_tokens=kwargs.get("max_tokens", 2000),
                temperature=kwargs.get("temperature", 0.7),
                messages=[{"role": "user", "content": prompt}],
            )
            latency_ms = (time.time() - start_time) * 1000
            return ProviderResult(
                text=response.content[0].text if response.content else "",
                model=response.model,
                outcome=ProviderOutcome.SUCCESS,
                tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                prompt_tokens=response.usage.input_tokens,
                completion_tokens=response.usage.output_tokens,
                latency_ms=latency_ms,
                finish_reason=response.stop_reason,
            )
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            return ProviderResult(
                text="", model=self.model, outcome=ProviderOutcome.ERROR,
                latency_ms=latency_ms, error=str(e),
            )

    async def stream(self, prompt: str, **kwargs) -> AsyncIterator[str]:
        try:
            async with self._client.messages.stream(
                model=self.model,
                max_tokens=kwargs.get("max_tokens", 2000),
                temperature=kwargs.get("temperature", 0.7),
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                async for text in stream.text_stream:
                    yield text
        except Exception as e:
            yield f"[Error: {e}]"

    async def validate_api_key(self) -> bool:
        try:
            await self.generate("test", max_tokens=1)
            return True
        except Exception:
            return False
