"""Centralised configuration — WidgetConfig with validation."""

import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Literal, Optional


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
            raise ValueError("max_tokens must be > 0")


@dataclass
class RoutingProfile:
    name: str = ""
    model: str = ""
    cost_per_1k_input: float = 0.0
    cost_per_1k_output: float = 0.0
    latency_p50_ms: float = 1000.0
    quality_score: float = 0.5

    @classmethod
    def from_dict(cls, d: dict) -> "RoutingProfile":
        return cls(
            name=d.get("name", ""),
            model=d.get("model", ""),
            cost_per_1k_input=float(d.get("cost_per_1k_input", 0)),
            cost_per_1k_output=float(d.get("cost_per_1k_output", 0)),
            latency_p50_ms=float(d.get("latency_p50_ms", 1000)),
            quality_score=float(d.get("quality_score", 0.5)),
        )


@dataclass
class RoutingConfig:
    enabled: bool = False
    strategy: str = "cheapest"
    fallback_provider: Optional[str] = None
    profiles: list[RoutingProfile] = field(default_factory=list)

    def __post_init__(self):
        valid = {"cheapest", "fastest", "best_quality", "fallback"}
        if self.strategy not in valid:
            raise ValueError(f"strategy must be one of {valid}, got {self.strategy!r}")


@dataclass
class CacheConfig:
    enabled: bool = True
    ttl_seconds: int = 3600
    max_entries: int = 1000
    strategy: Literal["lru", "lfu", "fifo"] = "lru"
    exclude_templates: list[str] = field(default_factory=list)
    redis_url: Optional[str] = None


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
    routing: RoutingConfig = field(default_factory=RoutingConfig)
    debug: bool = False
    default_template: str = "default"

    @classmethod
    def from_yaml(cls, path: str | Path) -> "WidgetConfig":
        """Load configuration from a YAML manifest file."""
        import yaml
        path = Path(path)
        with open(path) as f:
            data = yaml.safe_load(f) or {}

        cfg = cls()

        if "provider" in data:
            p = data["provider"]
            ptype = ProviderType(p.get("type", "openai"))
            cfg.provider = ProviderConfig(
                type=ptype,
                model=p.get("model", "gpt-4"),
                api_key=p.get("api_key") or os.getenv("BROMPT_API_KEY"),
                base_url=p.get("base_url"),
                organization_id=p.get("organization_id"),
            )

        if "generation" in data:
            g = data["generation"]
            cfg.generation = GenerationConfig(
                temperature=g.get("temperature", 0.7),
                max_tokens=g.get("max_tokens", 2000),
                top_p=g.get("top_p", 1.0),
                frequency_penalty=g.get("frequency_penalty", 0.0),
                presence_penalty=g.get("presence_penalty", 0.0),
                stop_sequences=g.get("stop_sequences", []),
            )

        if "routing" in data:
            r = data["routing"]
            profiles = [RoutingProfile.from_dict(p) for p in r.get("profiles", [])]
            cfg.routing = RoutingConfig(
                enabled=r.get("enabled", False),
                strategy=r.get("strategy", "cheapest"),
                fallback_provider=r.get("fallback_provider"),
                profiles=profiles,
            )

        if "cache" in data:
            c = data["cache"]
            cfg.cache = CacheConfig(
                enabled=c.get("enabled", True),
                ttl_seconds=c.get("ttl_seconds", 3600),
                max_entries=c.get("max_entries", 1000),
                strategy=c.get("strategy", "lru"),
                redis_url=c.get("redis_url"),
            )

        if "feedback" in data:
            fb = data["feedback"]
            cfg.feedback = FeedbackConfig(
                enabled=fb.get("enabled", True),
                storage_path=fb.get("storage_path", "./data/brompt_feedback.json"),
                regression_threshold=fb.get("regression_threshold", 0.15),
            )

        if "session" in data:
            s = data["session"]
            cfg.session = SessionConfig(
                max_sessions=s.get("max_sessions", 100),
                max_messages_per_session=s.get("max_messages_per_session", 100),
                context_window_size=s.get("context_window_size", 20),
                session_ttl_minutes=s.get("session_ttl_minutes", 60),
            )

        if "hooks" in data:
            h = data["hooks"]
            cfg.hooks = HooksConfig(
                enabled=h.get("enabled", True),
                builtin_logging=h.get("builtin_logging", True),
                builtin_content_filter=h.get("builtin_content_filter", False),
                blocked_words=h.get("blocked_words", []),
            )

        if "logging" in data:
            lc = data["logging"]
            cfg.logging = LoggingConfig(
                level=LogLevel(lc.get("level", "INFO")),
                file_path=lc.get("file_path"),
                format=lc.get("format", "%(asctime)s - %(name)s - %(levelname)s - %(message)s"),
            )

        cfg.debug = data.get("debug", False)
        return cfg

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
                redis_url=os.getenv("BROMPT_REDIS_URL") or None,
            ),
            routing=RoutingConfig(
                enabled=os.getenv("BROMPT_ROUTING_ENABLED", "false").lower() == "true",
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
