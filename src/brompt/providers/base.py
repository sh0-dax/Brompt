"""Base Provider Protocol."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, AsyncIterator


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
