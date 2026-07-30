"""OpenAI Provider."""

import time
from typing import AsyncIterator

from .base import LLMProvider, ProviderOutcome, ProviderResult, retry_async_call


class OpenAIProvider(LLMProvider):
    def _setup_client(self):
        try:
            from openai import AsyncOpenAI
            self._client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.kwargs.get("base_url"),
                organization=self.kwargs.get("organization_id"),
            )
        except ImportError:
            raise ImportError("pip install openai")
        except Exception as e:
            raise RuntimeError(f"OpenAI client init failed: {e}")

    async def generate(self, prompt: str, **kwargs) -> ProviderResult:
        start_time = time.time()
        try:
            response = await retry_async_call(
                lambda: self._client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=kwargs.get("temperature", 0.7),
                    max_tokens=kwargs.get("max_tokens", 2000),
                    top_p=kwargs.get("top_p", 1.0),
                    frequency_penalty=kwargs.get("frequency_penalty", 0.0),
                    presence_penalty=kwargs.get("presence_penalty", 0.0),
                    stop=kwargs.get("stop_sequences") or None,
                ),
                "OpenAI",
            )
            latency_ms = (time.time() - start_time) * 1000
            choice = response.choices[0]
            return ProviderResult(
                text=choice.message.content or "",
                model=response.model,
                outcome=ProviderOutcome.SUCCESS,
                tokens_used=response.usage.total_tokens if response.usage else 0,
                prompt_tokens=response.usage.prompt_tokens if response.usage else 0,
                completion_tokens=response.usage.completion_tokens if response.usage else 0,
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
            stream = await self._client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=kwargs.get("temperature", 0.7),
                max_tokens=kwargs.get("max_tokens", 2000),
                stream=True,
            )
            async for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            yield f"[Error: {e}]"

    async def validate_api_key(self) -> bool:
        try:
            await self._client.models.list()
            return True
        except Exception:
            return False
