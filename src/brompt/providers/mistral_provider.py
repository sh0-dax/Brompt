"""Mistral AI provider — async-compatible LLM provider."""

import logging
from typing import Any

from .base import LLMProvider

logger = logging.getLogger("brompt.providers.mistral")


class MistralProvider(LLMProvider):
    """Mistral AI provider."""

    def __init__(self, model: str = "mistral-large-latest", api_key: str | None = None):
        self.model = model
        self.api_key = api_key
        self._client = None

    def _ensure_client(self):
        if self._client is not None:
            return
        try:
            from mistralai import Mistral
            self._client = Mistral(api_key=self.api_key) if self.api_key else Mistral()
        except ImportError:
            raise ImportError("mistralai not installed. Install with: pip install brompt-engine[mistral]")
        except Exception as exc:
            logger.error("Failed to init Mistral client: %s", exc)
            raise

    def generate(self, messages: list[dict], system: str | None = None, **kwargs) -> str:
        self._ensure_client()
        try:
            msgs = []
            if system:
                msgs.append({"role": "system", "content": system})
            for msg in messages:
                msgs.append({"role": msg["role"], "content": msg["content"]})
            response = self._client.chat.complete(
                model=self.model,
                messages=msgs,
                temperature=kwargs.get("temperature", 0.7),
                max_tokens=kwargs.get("max_tokens", 4096),
            )
            return response.choices[0].message.content
        except Exception as exc:
            logger.error("Mistral generation failed: %s", exc)
            raise

    async def agenerate(self, messages: list[dict], system: str | None = None, **kwargs) -> str:
        self._ensure_client()
        try:
            msgs = []
            if system:
                msgs.append({"role": "system", "content": system})
            for msg in messages:
                msgs.append({"role": msg["role"], "content": msg["content"]})
            response = await self._client.chat.complete_async(
                model=self.model,
                messages=msgs,
                temperature=kwargs.get("temperature", 0.7),
                max_tokens=kwargs.get("max_tokens", 4096),
            )
            return response.choices[0].message.content
        except Exception as exc:
            logger.error("Mistral async generation failed: %s", exc)
            raise

    @property
    def model_name(self) -> str:
        return self.model


