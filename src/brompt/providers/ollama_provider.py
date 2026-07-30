"""Ollama provider — local LLM inference via Ollama, async support."""

import time
from typing import AsyncIterator

from .base import LLMProvider, ProviderOutcome, ProviderResult


class OllamaProvider(LLMProvider):
    def _setup_client(self):
        try:
            import ollama
            host = self.kwargs.get("base_url", "http://localhost:11434")
            self._sync_client = ollama.Client(host=host)
            self._client = ollama.AsyncClient(host=host)
        except ImportError:
            raise ImportError("pip install ollama")
        except Exception as e:
            raise RuntimeError(f"Ollama client init failed: {e}")

    async def generate(self, prompt: str, **kwargs) -> ProviderResult:
        start_time = time.time()
        try:
            msgs = [{"role": "user", "content": prompt}]
            system = kwargs.get("system")
            if system:
                msgs.insert(0, {"role": "system", "content": system})
            response = await self._client.chat(
                model=self.model,
                messages=msgs,
                options={
                    "temperature": kwargs.get("temperature", 0.7),
                    "num_predict": kwargs.get("max_tokens", 4096),
                    "top_p": kwargs.get("top_p", 1.0),
                },
            )
            latency_ms = (time.time() - start_time) * 1000
            text = response["message"]["content"]
            return ProviderResult(
                text=text,
                model=self.model,
                outcome=ProviderOutcome.SUCCESS,
                tokens_used=0,
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
            msgs = [{"role": "user", "content": prompt}]
            system = kwargs.get("system")
            if system:
                msgs.insert(0, {"role": "system", "content": system})
            stream = await self._client.chat(
                model=self.model,
                messages=msgs,
                options={"temperature": kwargs.get("temperature", 0.7)},
                stream=True,
            )
            async for chunk in stream:
                if chunk["message"]["content"]:
                    yield chunk["message"]["content"]
        except Exception as e:
            yield f"[Error: {e}]"

    async def validate_api_key(self) -> bool:
        try:
            await self._client.chat(
                model=self.model, messages=[{"role": "user", "content": "hi"}],
                options={"num_predict": 1},
            )
            return True
        except Exception:
            return False
