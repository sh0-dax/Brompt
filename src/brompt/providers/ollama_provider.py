"""Ollama provider — local LLM inference via Ollama."""

import logging
from typing import Any

from .base import LLMProvider

logger = logging.getLogger("brompt.providers.ollama")


class OllamaProvider(LLMProvider):
    """Ollama local provider."""

    def __init__(self, model: str = "llama3.2", base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self._client = None

    def _ensure_client(self):
        if self._client is not None:
            return
        try:
            import ollama
            self._client = ollama.Client(host=self.base_url)
        except ImportError:
            raise ImportError("ollama not installed. Install with: pip install brompt-engine[ollama]")
        except Exception as exc:
            logger.error("Failed to init Ollama client: %s", exc)
            raise

    def generate(self, messages: list[dict], system: str | None = None, **kwargs) -> str:
        self._ensure_client()
        try:
            msgs = []
            if system:
                msgs.append({"role": "system", "content": system})
            for msg in messages:
                msgs.append({"role": msg["role"], "content": msg["content"]})
            response = self._client.chat(
                model=self.model,
                messages=msgs,
                options={
                    "temperature": kwargs.get("temperature", 0.7),
                    "num_predict": kwargs.get("max_tokens", 4096),
                },
            )
            return response["message"]["content"]
        except Exception as exc:
            logger.error("Ollama generation failed: %s", exc)
            raise

    async def agenerate(self, messages: list[dict], system: str | None = None, **kwargs) -> str:
        self._ensure_client()
        try:
            msgs = []
            if system:
                msgs.append({"role": "system", "content": system})
            for msg in messages:
                msgs.append({"role": msg["role"], "content": msg["content"]})
            response = await self._client.chat(
                model=self.model,
                messages=msgs,
                options={
                    "temperature": kwargs.get("temperature", 0.7),
                    "num_predict": kwargs.get("max_tokens", 4096),
                },
            )
            return response["message"]["content"]
        except Exception as exc:
            logger.error("Ollama async generation failed: %s", exc)
            raise

    @property
    def model_name(self) -> str:
        return self.model


