"""Centralised configuration — WidgetConfig with validation."""

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Literal


class ProviderType(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    LOCAL = "local"
    CUSTOM = "custom"


class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


@dataclass
class ProviderConfig:
    type: ProviderType = ProviderType.OPENAI
    model: str = "gpt-4"
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    organization_id: Optional[str] = None

    def __post_init__(self):
        if self.api_key is None:
            env_key_map = {
                ProviderType.OPENAI: "OPENAI_API_KEY",
                ProviderType.ANTHROPIC: "ANTHROPIC_API_KEY",
                ProviderType.GOOGLE: "GEMINI_API_KEY",
            }
            env_var = env_key_map.get(self.type)
            if env_var:
                self.api_key = os.getenv(env_var)


@dataclass
class GenerationConfig:
    temperature: float = 0.7
    max_tokens: int = 2000
    top_p: float = 1.0
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0
    stop_sequences: list[str] = field(default_factory=list)

    def __post_init__(self):
        if not 0 <= self.temperature <= 2:
            raise ValueError(f"temperature must be 0-2, got {self.temperature}")
        if not 0 <= self.top_p <= 1:
            raise ValueError(f"top_p must be 0-1, got {self.top_p}")
        if self.max_tokens < 1:
            raise ValueError(f"max_tokens must be > 0")


@dataclass
class CacheConfig:
    enabled: bool = True
    ttl_seconds: int = 3600
    max_entries: int = 1000
    strategy: Literal["lru", "lfu", "fifo"] = "lru"
    exclude_templates: list[str] = field(default_factory=list)


@dataclass
class FeedbackConfig:
    enabled: bool = True
    storage_path: str = "./data/brompt_feedback.json"
    regression_threshold: float = 0.15
    min_uses_for_recommendation: int = 5
    success_weight: float = 0.5
    rating_weight: float = 0.3
    speed_weight: float = 0.2


@dataclass
class SessionConfig:
    max_sessions: int = 100
    max_messages_per_session: int = 100
    context_window_size: int = 20
    session_ttl_minutes: int = 60
    auto_cleanup: bool = True


@dataclass
class HooksConfig:
    enabled: bool = True
    builtin_logging: bool = True
    builtin_content_filter: bool = False
    blocked_words: list[str] = field(default_factory=list)


@dataclass
class LoggingConfig:
    level: LogLevel = LogLevel.INFO
    file_path: Optional[str] = "./logs/brompt.log"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    rich_tracebacks: bool = True


@dataclass
class WidgetConfig:
    provider: ProviderConfig = field(default_factory=ProviderConfig)
    generation: GenerationConfig = field(default_factory=GenerationConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)
    feedback: FeedbackConfig = field(default_factory=FeedbackConfig)
    session: SessionConfig = field(default_factory=SessionConfig)
    hooks: HooksConfig = field(default_factory=HooksConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    debug: bool = False
    default_template: str = "default"

    @classmethod
    def from_env(cls) -> "WidgetConfig":
        return cls(
            provider=ProviderConfig(
                type=ProviderType(os.getenv("BROMPT_PROVIDER", "openai")),
                model=os.getenv("BROMPT_MODEL", "gpt-4"),
            ),
            generation=GenerationConfig(
                temperature=float(os.getenv("BROMPT_TEMPERATURE", "0.7")),
                max_tokens=int(os.getenv("BROMPT_MAX_TOKENS", "2000")),
            ),
            cache=CacheConfig(
                enabled=os.getenv("BROMPT_CACHE_ENABLED", "true").lower() == "true",
            ),
            debug=os.getenv("BROMPT_DEBUG", "false").lower() == "true",
        )

    @classmethod
    def minimal(cls, api_key: str) -> "WidgetConfig":
        return cls(
            provider=ProviderConfig(api_key=api_key),
            cache=CacheConfig(enabled=False),
            feedback=FeedbackConfig(enabled=False),
        )

    def validate(self) -> list[str]:
        errors = []
        if self.provider.api_key is None and self.provider.type != ProviderType.LOCAL:
            errors.append(
                f"API key required for {self.provider.type.value}. "
                f"Set ProviderConfig(api_key='...') or the corresponding env var"
            )
        if self.generation.max_tokens > 100000:
            errors.append(f"max_tokens too large: {self.generation.max_tokens}")
        return errors


def create_dev_config() -> WidgetConfig:
    return WidgetConfig(
        provider=ProviderConfig(model="gpt-3.5-turbo"),
        generation=GenerationConfig(temperature=0.9, max_tokens=500),
        cache=CacheConfig(enabled=False),
        feedback=FeedbackConfig(enabled=False),
        debug=True,
        logging=LoggingConfig(level=LogLevel.DEBUG),
    )


def create_production_config(api_key: str) -> WidgetConfig:
    return WidgetConfig(
        provider=ProviderConfig(api_key=api_key, model="gpt-4"),
        generation=GenerationConfig(temperature=0.3, max_tokens=4000),
        cache=CacheConfig(enabled=True, ttl_seconds=7200),
        feedback=FeedbackConfig(enabled=True),
        debug=False,
        logging=LoggingConfig(level=LogLevel.WARNING),
    )


default_config = WidgetConfig.from_env()
