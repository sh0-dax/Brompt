"""Base Provider Protocol."""

import asyncio
import logging
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import AsyncIterator, Optional

logger = logging.getLogger("brompt.providers")

# ---------------------------------------------------------------------------
# Shared retry-with-backoff helper (async only).
# Mirrors the logic in ``brompt.providers_core`` so that both provider
# systems behave identically under rate-limit pressure.
# ---------------------------------------------------------------------------

_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 1.0


def is_rate_limit_error(exc: Exception) -> bool:
    """Return ``True`` when *exc* represents a HTTP 429 / rate-limit response."""
    if getattr(exc, "code", None) == 429:
        return True
    if getattr(exc, "status_code", None) == 429:
        return True
    msg = str(exc).lower()
    return "429" in msg or "resource_exhausted" in msg or "toomanyrequests" in msg or "rate_limit" in msg


async def retry_async_call(call, provider_name: str):
    """Await *call* (a zero-arg async callable), retrying with exponential
    backoff + jitter on rate-limit errors only.

    Any non-rate-limit exception propagates immediately.  After exhausting
    all retries the *last* exception is re-raised so callers can still apply
    their existing ``except`` handlers.
    """
    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES + 1):
        try:
            return await call()
        except Exception as exc:
            last_exc = exc
            if is_rate_limit_error(exc) and attempt < _MAX_RETRIES:
                delay = _RETRY_BASE_DELAY * (2 ** attempt) + random.uniform(0, 0.5)
                logger.warning(
                    "%s rate-limited (429), retrying in %.1fs (attempt %d/%d)",
                    provider_name, delay, attempt + 1, _MAX_RETRIES,
                )
                await asyncio.sleep(delay)
                continue
            raise
    raise last_exc  # pragma: no cover


class ProviderOutcome(str, Enum):
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    CONTENT_FILTERED = "content_filtered"


@dataclass
class ProviderResult:
    text: str
    model: str
    outcome: ProviderOutcome = ProviderOutcome.SUCCESS
    tokens_used: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: float = 0.0
    finish_reason: Optional[str] = None
    metadata: dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    error: Optional[str] = None

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    @property
    def is_success(self) -> bool:
        return self.outcome == ProviderOutcome.SUCCESS

    def to_dict(self) -> dict:
        return {
            "text": self.text[:100] + "..." if len(self.text) > 100 else self.text,
            "model": self.model,
            "outcome": self.outcome.value,
            "tokens_used": self.tokens_used,
            "latency_ms": self.latency_ms,
            "finish_reason": self.finish_reason,
            "error": self.error,
        }


class LLMProvider(ABC):
    def __init__(self, model: str, api_key: Optional[str] = None, **kwargs):
        self.model = model
        self.api_key = api_key
        self.kwargs = kwargs
        self._setup_client()

    @abstractmethod
    def _setup_client(self):
        ...

    @abstractmethod
    async def generate(self, prompt: str, **kwargs) -> ProviderResult:
        ...

    @abstractmethod
    async def stream(self, prompt: str, **kwargs) -> AsyncIterator[str]:
        ...

    @abstractmethod
    async def validate_api_key(self) -> bool:
        ...

    def get_model_info(self) -> dict:
        return {
            "provider": self.__class__.__name__,
            "model": self.model,
        }
