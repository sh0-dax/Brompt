"""Google Gemini provider — async provider using google-genai SDK."""

import time
from typing import AsyncIterator

from .base import LLMProvider, ProviderOutcome, ProviderResult, retry_async_call


class GoogleProvider(LLMProvider):
    def _setup_client(self):
        try:
            from google import genai
            from google.genai import types
            self._types = types
            self._sync_client = genai.Client(api_key=self.api_key)
            self._client = self._sync_client.aio
        except ImportError:
            raise ImportError("pip install google-genai")
        except Exception as e:
            raise RuntimeError(f"Gemini client init failed: {e}")

    async def generate(self, prompt: str, **kwargs) -> ProviderResult:
        start_time = time.time()
        try:
            config = {
                "temperature": kwargs.get("temperature", 0.7),
                "max_output_tokens": kwargs.get("max_tokens", 4096),
                "top_p": kwargs.get("top_p", 1.0),
            }
            system = kwargs.get("system")
            if system:
                response = await retry_async_call(
                    lambda: self._client.models.generate_content(
                        model=self.model,
                        contents=prompt,
                        config=self._types.GenerateContentConfig(
                            system_instruction=system,
                            temperature=config["temperature"],
                            max_output_tokens=config["max_output_tokens"],
                        ),
                    ),
                    "Google",
                )
            else:
                response = await retry_async_call(
                    lambda: self._client.models.generate_content(
                        model=self.model,
                        contents=prompt,
                    ),
                    "Google",
                )
            latency_ms = (time.time() - start_time) * 1000
            text = response.text or ""
            usage = response.usage_metadata
            return ProviderResult(
                text=text,
                model=self.model,
                outcome=ProviderOutcome.SUCCESS,
                tokens_used=usage.total_token_count if usage else 0,
                prompt_tokens=usage.prompt_token_count if usage else 0,
                completion_tokens=usage.candidates_token_count if usage else 0,
                latency_ms=latency_ms,
                finish_reason="stop",
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
            response = await self._client.models.generate_content_stream(
                model=self.model,
                contents=prompt,
            )
            async for chunk in response:
                if chunk.text:
                    yield chunk.text
        except Exception as e:
            yield f"[Error: {e}]"

    async def validate_api_key(self) -> bool:
        try:
            await self._client.models.list()
            return True
        except Exception:
            return False
