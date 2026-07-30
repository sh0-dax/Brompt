"""Upstream LLM provider integrations.

Supports 6 providers: Anthropic, OpenAI, Ollama, Google Gemini,
Azure OpenAI, Mistral, and LM Studio (OpenAI-compatible).

Each provider is an optional dependency -- install only what you need:
    pip install 'brompt-engine[anthropic]'
    pip install 'brompt-engine[openai]'
    pip install 'brompt-engine[ollama]'
    pip install 'brompt-engine[gemini]'
    pip install 'brompt-engine[mistral]'
    pip install 'brompt-engine[all]'
"""

import asyncio
import logging
import os
import random
import time
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

logger = logging.getLogger("brompt.providers")


class ProviderError(RuntimeError):
    """Raised when the upstream provider call fails or is unavailable."""


# ---------------------------------------------------------------------------
# Shared retry-with-backoff helper (used by every cloud provider below).
# Previously this logic existed only inside GeminiProvider -- a 429 from
# Anthropic, OpenAI, Mistral, or Azure OpenAI would fail immediately with
# no retry. Centralizing it here means one fix/tuning applies everywhere.
# ---------------------------------------------------------------------------

_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 1.0


def _is_rate_limit_error(exc: Exception) -> bool:
    """Return True when *exc* represents a HTTP 429 / rate-limit response."""
    if getattr(exc, "code", None) == 429:
        return True
    if getattr(exc, "status_code", None) == 429:
        return True
    msg = str(exc).lower()
    return "429" in msg or "resource_exhausted" in msg or "toomanyrequests" in msg or "rate_limit" in msg


def _retry_sync(call, provider_name: str):
    """Runs a zero-arg callable, retrying with exponential backoff + jitter
    on rate-limit errors only. Any other exception propagates immediately.
    On final failure, re-raises the *original* exception unchanged so the
    caller's existing ``except Exception as exc: raise ProviderError(...)``
    wrapping still applies."""
    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES + 1):
        try:
            return call()
        except Exception as exc:
            last_exc = exc
            if _is_rate_limit_error(exc) and attempt < _MAX_RETRIES:
                delay = _RETRY_BASE_DELAY * (2 ** attempt) + random.uniform(0, 0.5)
                logger.warning(
                    "%s rate-limited (429), retrying in %.1fs (attempt %d/%d)",
                    provider_name, delay, attempt + 1, _MAX_RETRIES,
                )
                time.sleep(delay)
                continue
            raise
    raise last_exc  # pragma: no cover -- loop always returns or raises above


async def _retry_async(call, provider_name: str):
    """Async counterpart of :func:`_retry_sync`; ``call`` is an async
    zero-arg callable (``await call()``)."""
    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES + 1):
        try:
            return await call()
        except Exception as exc:
            last_exc = exc
            if _is_rate_limit_error(exc) and attempt < _MAX_RETRIES:
                delay = _RETRY_BASE_DELAY * (2 ** attempt) + random.uniform(0, 0.5)
                logger.warning(
                    "%s rate-limited (429), retrying in %.1fs (attempt %d/%d)",
                    provider_name, delay, attempt + 1, _MAX_RETRIES,
                )
                await asyncio.sleep(delay)
                continue
            raise
    raise last_exc  # pragma: no cover


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class LLMProvider(ABC):
    @abstractmethod
    def generate(self, messages: list[dict[str, str]], system: str | None = None) -> str:
        """Given bounded turn history, returns the model's text response.

        Implementations must raise ``ProviderError`` on failure rather
        than leaking raw SDK exceptions.
        """
        raise NotImplementedError

    async def agenerate(self, messages: list[dict[str, str]], system: str | None = None) -> str:
        """Async counterpart. Providers that don't override this raise
        ``ProviderError``; ``BromptEngine.execute_async`` falls back to
        running the sync ``generate`` in a thread instead."""
        raise ProviderError(f"{type(self).__name__} does not implement agenerate().")

    def stream(self, messages: list[dict[str, str]], system: str | None = None) -> AsyncIterator[str]:
        """Sync streaming — yields partial tokens as they arrive.

        Default raises ``NotImplementedError`` (opt-in).  Override in
        subclasses that support real-time token emission."""
        raise NotImplementedError(f"{type(self).__name__} does not implement stream().")

    async def astream(self, messages: list[dict[str, str]], system: str | None = None) -> AsyncIterator[str]:
        """Async streaming — yields partial tokens as they arrive.

        Default raises ``NotImplementedError`` (opt-in).  Override in
        subclasses that support real-time token emission."""
        raise NotImplementedError(f"{type(self).__name__} does not implement astream().")


# ---------------------------------------------------------------------------
# Anthropic
# ---------------------------------------------------------------------------

class AnthropicProvider(LLMProvider):
    """Calls the Anthropic Messages API (Claude). Requires ``anthropic`` package."""

    def __init__(self, api_key: str | None = None, model: str = "claude-sonnet-4-5"):
        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise ProviderError("No Anthropic API key configured (pass api_key= or set ANTHROPIC_API_KEY).")
        try:
            import anthropic
        except ImportError as exc:
            raise ProviderError(
                "The 'anthropic' package is required. Install with: pip install 'brompt-engine[anthropic]'"
            ) from exc
        self._client = anthropic.Anthropic(api_key=key)
        self.model = model

    def generate(self, messages: list[dict[str, str]], system: str | None = None) -> str:
        if not messages:
            raise ProviderError("Cannot call provider with empty message history.")
        try:
            kwargs: dict = {"model": self.model, "max_tokens": 1024, "messages": messages}
            if system:
                kwargs["system"] = system
            response = _retry_sync(lambda: self._client.messages.create(**kwargs), "Anthropic")
        except Exception as exc:
            raise ProviderError(f"Anthropic API call failed: {exc}") from exc
        text_blocks = [b.text for b in response.content if getattr(b, "type", None) == "text"]
        if not text_blocks:
            raise ProviderError("Anthropic response contained no text content.")
        return "".join(text_blocks)


class AsyncAnthropicProvider(LLMProvider):
    """Async counterpart of :class:`AnthropicProvider`. Uses ``anthropic.AsyncAnthropic``."""

    def __init__(self, api_key: str | None = None, model: str = "claude-sonnet-4-5"):
        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise ProviderError("No Anthropic API key configured (pass api_key= or set ANTHROPIC_API_KEY).")
        try:
            import anthropic
        except ImportError as exc:
            raise ProviderError(
                "The 'anthropic' package is required. Install with: pip install 'brompt-engine[anthropic]'"
            ) from exc
        self._client = anthropic.AsyncAnthropic(api_key=key)
        self.model = model

    def generate(self, messages: list[dict[str, str]], system: str | None = None) -> str:
        raise ProviderError("AsyncAnthropicProvider only supports agenerate(); use AnthropicProvider for sync.")

    async def agenerate(self, messages: list[dict[str, str]], system: str | None = None) -> str:
        if not messages:
            raise ProviderError("Cannot call provider with empty message history.")
        try:
            kwargs: dict = {"model": self.model, "max_tokens": 1024, "messages": messages}
            if system:
                kwargs["system"] = system
            response = await _retry_async(lambda: self._client.messages.create(**kwargs), "Anthropic")
        except Exception as exc:
            raise ProviderError(f"Anthropic API call failed: {exc}") from exc
        text_blocks = [b.text for b in response.content if getattr(b, "type", None) == "text"]
        if not text_blocks:
            raise ProviderError("Anthropic response contained no text content.")
        return "".join(text_blocks)


# ---------------------------------------------------------------------------
# OpenAI (ChatGPT / GPT-4o / GPT-4)
# ---------------------------------------------------------------------------

class OpenAIProvider(LLMProvider):
    """Calls the OpenAI Chat Completions API. Requires ``openai`` package."""

    def __init__(self, api_key: str | None = None, model: str = "gpt-4o"):
        key = api_key or os.environ.get("OPENAI_API_KEY")
        if not key:
            raise ProviderError("No OpenAI API key configured (pass api_key= or set OPENAI_API_KEY).")
        try:
            import openai
        except ImportError as exc:
            raise ProviderError(
                "The 'openai' package is required. Install with: pip install 'brompt-engine[openai]'"
            ) from exc
        self._client = openai.OpenAI(api_key=key)
        self.model = model

    def generate(self, messages: list[dict[str, str]], system: str | None = None) -> str:
        if not messages:
            raise ProviderError("Cannot call provider with empty message history.")
        try:
            full_messages = []
            if system:
                full_messages.append({"role": "system", "content": system})
            full_messages.extend(messages)
            response = _retry_sync(
                lambda: self._client.chat.completions.create(
                    model=self.model, max_tokens=1024, messages=full_messages
                ),
                "OpenAI",
            )
        except Exception as exc:
            raise ProviderError(f"OpenAI API call failed: {exc}") from exc
        content = response.choices[0].message.content
        if not content:
            raise ProviderError("OpenAI response contained no text content.")
        return content


class AsyncOpenAIProvider(LLMProvider):
    """Async counterpart of :class:`OpenAIProvider`. Uses ``openai.AsyncOpenAI``."""

    def __init__(self, api_key: str | None = None, model: str = "gpt-4o"):
        key = api_key or os.environ.get("OPENAI_API_KEY")
        if not key:
            raise ProviderError("No OpenAI API key configured (pass api_key= or set OPENAI_API_KEY).")
        try:
            import openai
        except ImportError as exc:
            raise ProviderError(
                "The 'openai' package is required. Install with: pip install 'brompt-engine[openai]'"
            ) from exc
        self._client = openai.AsyncOpenAI(api_key=key)
        self.model = model

    def generate(self, messages: list[dict[str, str]], system: str | None = None) -> str:
        raise ProviderError("AsyncOpenAIProvider only supports agenerate(); use OpenAIProvider for sync.")

    async def agenerate(self, messages: list[dict[str, str]], system: str | None = None) -> str:
        if not messages:
            raise ProviderError("Cannot call provider with empty message history.")
        try:
            full_messages = []
            if system:
                full_messages.append({"role": "system", "content": system})
            full_messages.extend(messages)
            response = await _retry_async(
                lambda: self._client.chat.completions.create(
                    model=self.model, max_tokens=1024, messages=full_messages
                ),
                "OpenAI",
            )
        except Exception as exc:
            raise ProviderError(f"OpenAI API call failed: {exc}") from exc
        content = response.choices[0].message.content
        if not content:
            raise ProviderError("OpenAI response contained no text content.")
        return content


# ---------------------------------------------------------------------------
# Ollama (local)
# ---------------------------------------------------------------------------

class OllamaProvider(LLMProvider):
    """Calls a local Ollama instance. No API key required.

    Default endpoint: http://localhost:11434
    """

    def __init__(self, host: str | None = None, model: str = "llama3.2"):
        self.host = (host or os.environ.get("OLLAMA_HOST", "http://localhost:11434")).rstrip("/")
        self.model = model
        try:
            import ollama as _ollama
        except ImportError as exc:
            raise ProviderError(
                "The 'ollama' package is required. Install with: pip install 'brompt-engine[ollama]'"
            ) from exc
        self._client = _ollama.Client(host=self.host)

    def generate(self, messages: list[dict[str, str]], system: str | None = None) -> str:
        if not messages:
            raise ProviderError("Cannot call provider with empty message history.")
        try:
            kwargs: dict = {"model": self.model, "messages": messages}
            if system:
                kwargs["messages"] = [{"role": "system", "content": system}, *messages]
            response = self._client.chat(**kwargs)
        except Exception as exc:
            raise ProviderError(f"Ollama API call failed: {exc}") from exc
        content = response.get("message", {}).get("content", "")
        if not content:
            raise ProviderError("Ollama response contained no text content.")
        return content


# ---------------------------------------------------------------------------
# Google Gemini
# ---------------------------------------------------------------------------

class GeminiProvider(LLMProvider):
    """Calls the Google Gemini API. Requires ``google-genai`` package."""

    def __init__(self, api_key: str | None = None, model: str = "gemini-2.5-flash"):
        key = api_key or os.environ.get("GEMINI_API_KEY")
        if not key:
            raise ProviderError("No Gemini API key configured (pass api_key= or set GEMINI_API_KEY).")
        try:
            from google import genai
        except ImportError as exc:
            raise ProviderError(
                "The 'google-genai' package is required. Install with: pip install 'brompt-engine[gemini]'"
            ) from exc
        self._client = genai.Client(api_key=key)
        self.model = model

    def generate(self, messages: list[dict[str, str]], system: str | None = None) -> str:
        if not messages:
            raise ProviderError("Cannot call provider with empty message history.")
        contents = []
        for msg in messages:
            role = "user" if msg["role"] in ("user", "system") else "model"
            contents.append({"role": role, "parts": [{"text": msg["content"]}]})
        kwargs: dict = {"model": self.model, "contents": contents}
        if system:
            kwargs["config"] = {"system_instruction": system}
        try:
            response = _retry_sync(lambda: self._client.models.generate_content(**kwargs), "Gemini")
        except Exception as exc:
            raise ProviderError(f"Gemini API call failed: {exc}") from exc
        text = response.text
        if not text:
            raise ProviderError("Gemini response contained no text content.")
        return text


class AsyncGeminiProvider(LLMProvider):
    """Async counterpart of :class:`GeminiProvider`."""

    def __init__(self, api_key: str | None = None, model: str = "gemini-2.5-flash"):
        key = api_key or os.environ.get("GEMINI_API_KEY")
        if not key:
            raise ProviderError("No Gemini API key configured (pass api_key= or set GEMINI_API_KEY).")
        try:
            from google import genai
        except ImportError as exc:
            raise ProviderError(
                "The 'google-genai' package is required. Install with: pip install 'brompt-engine[gemini]'"
            ) from exc
        self._client = genai.Client(api_key=key)
        self.model = model

    def generate(self, messages: list[dict[str, str]], system: str | None = None) -> str:
        raise ProviderError("AsyncGeminiProvider only supports agenerate(); use GeminiProvider for sync.")

    async def agenerate(self, messages: list[dict[str, str]], system: str | None = None) -> str:
        if not messages:
            raise ProviderError("Cannot call provider with empty message history.")
        contents = []
        for msg in messages:
            role = "user" if msg["role"] in ("user", "system") else "model"
            contents.append({"role": role, "parts": [{"text": msg["content"]}]})
        kwargs: dict = {"model": self.model, "contents": contents}
        if system:
            kwargs["config"] = {"system_instruction": system}
        try:
            response = await _retry_async(lambda: self._client.aio.models.generate_content(**kwargs), "Gemini")
        except Exception as exc:
            raise ProviderError(f"Gemini API call failed: {exc}") from exc
        text = response.text
        if not text:
            raise ProviderError("Gemini response contained no text content.")
        return text


# ---------------------------------------------------------------------------
# Azure OpenAI
# ---------------------------------------------------------------------------

class AzureOpenAIProvider(LLMProvider):
    """Calls Azure OpenAI endpoint. Requires ``openai`` package with Azure config.

    Environment variables:
        AZURE_OPENAI_API_KEY   - API key
        AZURE_OPENAI_ENDPOINT  - e.g. https://myinstance.openai.azure.com
        AZURE_OPENAI_DEPLOYMENT - deployment name, e.g. gpt-4o-deployment
    """

    def __init__(
        self,
        api_key: str | None = None,
        endpoint: str | None = None,
        deployment: str | None = None,
        api_version: str = "2024-08-01-preview",
    ):
        self.api_key = api_key or os.environ.get("AZURE_OPENAI_API_KEY")
        self.endpoint = endpoint or os.environ.get("AZURE_OPENAI_ENDPOINT")
        self.deployment = deployment or os.environ.get("AZURE_OPENAI_DEPLOYMENT")
        self.api_version = api_version

        if not self.api_key:
            raise ProviderError("No Azure OpenAI API key (set AZURE_OPENAI_API_KEY).")
        if not self.endpoint:
            raise ProviderError("No Azure OpenAI endpoint (set AZURE_OPENAI_ENDPOINT).")
        if not self.deployment:
            raise ProviderError("No Azure OpenAI deployment (set AZURE_OPENAI_DEPLOYMENT).")

        try:
            import openai
        except ImportError as exc:
            raise ProviderError(
                "The 'openai' package is required. Install with: pip install 'brompt-engine[azure]'"
            ) from exc
        self._client = openai.AzureOpenAI(
            api_key=self.api_key,
            azure_endpoint=self.endpoint,
            api_version=self.api_version,
        )

    def generate(self, messages: list[dict[str, str]], system: str | None = None) -> str:
        if not messages:
            raise ProviderError("Cannot call provider with empty message history.")
        try:
            full_messages = []
            if system:
                full_messages.append({"role": "system", "content": system})
            full_messages.extend(messages)
            response = _retry_sync(
                lambda: self._client.chat.completions.create(
                    model=self.deployment, max_tokens=1024, messages=full_messages
                ),
                "Azure OpenAI",
            )
        except Exception as exc:
            raise ProviderError(f"Azure OpenAI API call failed: {exc}") from exc
        content = response.choices[0].message.content
        if not content:
            raise ProviderError("Azure OpenAI response contained no text content.")
        return content


class AsyncAzureOpenAIProvider(LLMProvider):
    """Async counterpart of :class:`AzureOpenAIProvider`."""

    def __init__(
        self,
        api_key: str | None = None,
        endpoint: str | None = None,
        deployment: str | None = None,
        api_version: str = "2024-08-01-preview",
    ):
        self.api_key = api_key or os.environ.get("AZURE_OPENAI_API_KEY")
        self.endpoint = endpoint or os.environ.get("AZURE_OPENAI_ENDPOINT")
        self.deployment = deployment or os.environ.get("AZURE_OPENAI_DEPLOYMENT")
        self.api_version = api_version

        if not self.api_key:
            raise ProviderError("No Azure OpenAI API key (set AZURE_OPENAI_API_KEY).")
        if not self.endpoint:
            raise ProviderError("No Azure OpenAI endpoint (set AZURE_OPENAI_ENDPOINT).")
        if not self.deployment:
            raise ProviderError("No Azure OpenAI deployment (set AZURE_OPENAI_DEPLOYMENT).")

        try:
            import openai
        except ImportError as exc:
            raise ProviderError(
                "The 'openai' package is required. Install with: pip install 'brompt-engine[azure]'"
            ) from exc
        self._client = openai.AsyncAzureOpenAI(
            api_key=self.api_key,
            azure_endpoint=self.endpoint,
            api_version=self.api_version,
        )

    def generate(self, messages: list[dict[str, str]], system: str | None = None) -> str:
        raise ProviderError("AsyncAzureOpenAIProvider only supports agenerate(); use AzureOpenAIProvider for sync.")

    async def agenerate(self, messages: list[dict[str, str]], system: str | None = None) -> str:
        if not messages:
            raise ProviderError("Cannot call provider with empty message history.")
        try:
            full_messages = []
            if system:
                full_messages.append({"role": "system", "content": system})
            full_messages.extend(messages)
            response = await _retry_async(
                lambda: self._client.chat.completions.create(
                    model=self.deployment, max_tokens=1024, messages=full_messages
                ),
                "Azure OpenAI",
            )
        except Exception as exc:
            raise ProviderError(f"Azure OpenAI API call failed: {exc}") from exc
        content = response.choices[0].message.content
        if not content:
            raise ProviderError("Azure OpenAI response contained no text content.")
        return content


# ---------------------------------------------------------------------------
# Mistral
# ---------------------------------------------------------------------------

class MistralProvider(LLMProvider):
    """Calls the Mistral API. Requires ``mistralai`` package."""

    def __init__(self, api_key: str | None = None, model: str = "mistral-large-latest"):
        key = api_key or os.environ.get("MISTRAL_API_KEY")
        if not key:
            raise ProviderError("No Mistral API key configured (pass api_key= or set MISTRAL_API_KEY).")
        try:
            from mistralai import Mistral
        except ImportError as exc:
            raise ProviderError(
                "The 'mistralai' package is required. Install with: pip install 'brompt-engine[mistral]'"
            ) from exc
        self._client = Mistral(api_key=key)
        self.model = model

    def generate(self, messages: list[dict[str, str]], system: str | None = None) -> str:
        if not messages:
            raise ProviderError("Cannot call provider with empty message history.")
        try:
            full_messages = []
            if system:
                full_messages.append({"role": "system", "content": system})
            full_messages.extend(messages)
            response = _retry_sync(
                lambda: self._client.chat.complete(model=self.model, messages=full_messages), "Mistral"
            )
        except Exception as exc:
            raise ProviderError(f"Mistral API call failed: {exc}") from exc
        content = response.choices[0].message.content
        if not content:
            raise ProviderError("Mistral response contained no text content.")
        return content


class AsyncMistralProvider(LLMProvider):
    """Async counterpart of :class:`MistralProvider`."""

    def __init__(self, api_key: str | None = None, model: str = "mistral-large-latest"):
        key = api_key or os.environ.get("MISTRAL_API_KEY")
        if not key:
            raise ProviderError("No Mistral API key configured (pass api_key= or set MISTRAL_API_KEY).")
        try:
            from mistralai import Mistral
        except ImportError as exc:
            raise ProviderError(
                "The 'mistralai' package is required. Install with: pip install 'brompt-engine[mistral]'"
            ) from exc
        self._client = Mistral(api_key=key)
        self.model = model

    def generate(self, messages: list[dict[str, str]], system: str | None = None) -> str:
        raise ProviderError("AsyncMistralProvider only supports agenerate(); use MistralProvider for sync.")

    async def agenerate(self, messages: list[dict[str, str]], system: str | None = None) -> str:
        if not messages:
            raise ProviderError("Cannot call provider with empty message history.")
        try:
            full_messages = []
            if system:
                full_messages.append({"role": "system", "content": system})
            full_messages.extend(messages)
            response = await _retry_async(
                lambda: self._client.chat.complete_async(model=self.model, messages=full_messages), "Mistral"
            )
        except Exception as exc:
            raise ProviderError(f"Mistral API call failed: {exc}") from exc
        content = response.choices[0].message.content
        if not content:
            raise ProviderError("Mistral response contained no text content.")
        return content


# ---------------------------------------------------------------------------
# LM Studio (OpenAI-compatible local)
# ---------------------------------------------------------------------------

class LMStudioProvider(LLMProvider):
    """Calls a local LM Studio server via OpenAI-compatible API.

    Default endpoint: http://localhost:1234/v1
    No API key required.
    """

    def __init__(self, host: str | None = None, model: str = "default"):
        self.host = (host or os.environ.get("LM_STUDIO_HOST", "http://localhost:1234/v1")).rstrip("/")
        self.model = model
        try:
            import openai
        except ImportError as exc:
            raise ProviderError(
                "The 'openai' package is required. Install with: pip install 'brompt-engine[lmstudio]'"
            ) from exc
        self._client = openai.OpenAI(api_key="lm-studio", base_url=self.host)

    def generate(self, messages: list[dict[str, str]], system: str | None = None) -> str:
        if not messages:
            raise ProviderError("Cannot call provider with empty message history.")
        try:
            full_messages = []
            if system:
                full_messages.append({"role": "system", "content": system})
            full_messages.extend(messages)
            response = self._client.chat.completions.create(
                model=self.model, max_tokens=1024, messages=full_messages
            )
        except Exception as exc:
            raise ProviderError(f"LM Studio API call failed: {exc}") from exc
        content = response.choices[0].message.content
        if not content:
            raise ProviderError("LM Studio response contained no text content.")
        return content


# ---------------------------------------------------------------------------
# Factory: build provider from environment variables
# ---------------------------------------------------------------------------

def build_provider_from_env(model: str | None = None) -> LLMProvider | None:
    """Best-effort provider construction from environment.

    Priority order:
        1. ANTHROPIC_API_KEY   -> AnthropicProvider
        2. OPENAI_API_KEY      -> OpenAIProvider
        3. GEMINI_API_KEY      -> GeminiProvider
        4. MISTRAL_API_KEY     -> MistralProvider
        5. AZURE_OPENAI_API_KEY -> AzureOpenAIProvider
        6. OLLAMA_HOST         -> OllamaProvider
        7. LM_STUDIO_HOST      -> LMStudioProvider

    Returns None (dry-run mode) rather than raising, so the engine can
    still be used purely as an input-validation/state layer when no
    provider is configured.
    """
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            return AnthropicProvider(model=model or "claude-sonnet-4-5")
        except ProviderError:
            return None

    if os.environ.get("OPENAI_API_KEY"):
        try:
            return OpenAIProvider(model=model or "gpt-4o")
        except ProviderError:
            return None

    if os.environ.get("GEMINI_API_KEY"):
        try:
            return GeminiProvider(model=model or "gemini-2.5-flash")
        except ProviderError:
            return None

    if os.environ.get("MISTRAL_API_KEY"):
        try:
            return MistralProvider(model=model or "mistral-large-latest")
        except ProviderError:
            return None

    if os.environ.get("AZURE_OPENAI_API_KEY"):
        try:
            return AzureOpenAIProvider()
        except ProviderError:
            return None

    if os.environ.get("OLLAMA_HOST"):
        try:
            return OllamaProvider(model=model or "llama3.2")
        except ProviderError:
            return None

    if os.environ.get("LM_STUDIO_HOST"):
        try:
            return LMStudioProvider(model=model or "default")
        except ProviderError:
            return None

    return None
