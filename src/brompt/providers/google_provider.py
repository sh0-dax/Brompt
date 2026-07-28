"""Google Gemini provider — async-compatible LLM provider."""

import logging
from typing import Any

from .base import LLMProvider
logger = logging.getLogger("brompt.providers.google")


class GoogleProvider(LLMProvider):
    """Google Gemini provider."""

    def __init__(self, model: str = "gemini-2.0-flash", api_key: str | None = None):
        self.model = model
        self.api_key = api_key
        self._client = None

    def _ensure_client(self):
        if self._client is not None:
            return
        try:
            from google import genai
            self._client = genai.Client(api_key=self.api_key) if self.api_key else genai.Client()
        except ImportError:
            raise ImportError("google-genai not installed. Install with: pip install brompt-engine[gemini]")
        except Exception as exc:
            logger.error("Failed to init Google client: %s", exc)
            raise

    def generate(self, messages: list[dict], system: str | None = None, **kwargs) -> str:
        self._ensure_client()
        try:
            contents = []
            for msg in messages:
                role = "model" if msg["role"] == "assistant" else "user"
                contents.append({"role": role, "parts": [{"text": msg["content"]}]})
            config = {"temperature": kwargs.get("temperature", 0.7)}
            if system:
                config["system_instruction"] = system
            response = self._client.models.generate_content(
                model=self.model,
                contents=contents,
                config=config,
            )
            return response.text
        except Exception as exc:
            logger.error("Google generation failed: %s", exc)
            raise

    async def agenerate(self, messages: list[dict], system: str | None = None, **kwargs) -> str:
        self._ensure_client()
        try:
            contents = []
            for msg in messages:
                role = "model" if msg["role"] == "assistant" else "user"
                contents.append({"role": role, "parts": [{"text": msg["content"]}]})
            config = {"temperature": kwargs.get("temperature", 0.7)}
            if system:
                config["system_instruction"] = system
            response = await self._client.aio.models.generate_content(
                model=self.model,
                contents=contents,
                config=config,
            )
            return response.text
        except Exception as exc:
            logger.error("Google async generation failed: %s", exc)
            raise

    @property
    def model_name(self) -> str:
        return self.model


