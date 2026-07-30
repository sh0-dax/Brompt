"""Brompt — LLM prompt engine with a unified widget interface."""

__version__ = "2.0.0"
__author__ = "Brompt Team"

from .audit import AuditLog
from .circuit_breaker import CircuitBreaker, CircuitBreakerOpenError
from .classifier import ClassificationResult, InjectionClassifier, LLMInjectionClassifier, PendingReviewError, Tier
from .config import (
    CacheConfig,
    FeedbackConfig,
    GenerationConfig,
    LogLevel,
    ProviderConfig,
    ProviderType,
    SessionConfig,
    WidgetConfig,
    create_dev_config,
    create_production_config,
)
from .core.engine import BromptEngine
from .core.template_engine import Template, TemplateRegistry, template_registry
from .hooks import (
    AuditHook,
    BaseHook,
    HooksManager,
    InMemoryRateLimitBackend,
    LoggingHook,
    RateLimitBackend,
    RateLimitHook,
    RedisRateLimitBackend,
    SecurityHook,
    TimingHook,
    ValidationHook,
    hooks_manager,
)
from .observability import AlertManager, AlertRule, MetricsCollector, Span, Tracer, alert_manager, metrics, tracer
from .policy import PolicyEngine, PolicyRule, PolicyViolationError
from .providers import (
    AnthropicProvider,
    GoogleProvider,
    LLMProvider,
    MistralProvider,
    OllamaProvider,
    OpenAIProvider,
    ProviderFactory,
    ProviderRegistry,
    ProviderResult,
)
from .ratelimit import RateLimiter, RateLimiterBackend, RateLimitExceededError, RedisRateLimiter
from .router import ComplexityLevel, ModelRouter, RoutingStrategy
from .security import SecurityEngine, SecurityViolationError
from .session import Message, Session, SessionManager
from .widget import PromptClient, PromptResult

try:
    from .feedback import FeedbackLoop, PromptOutcome
    _feedback_available = True
except ImportError:
    _feedback_available = False

__all__ = [
    "AlertManager",
    "AlertRule",
    "AnthropicProvider",
    "AuditHook",
    "AuditLog",
    "BaseHook",
    "BromptEngine",
    "CacheConfig",
    "CircuitBreaker",
    "CircuitBreakerOpenError",
    "ClassificationResult",
    "ComplexityLevel",
    "FeedbackConfig",
    "GenerationConfig",
    "GoogleProvider",
    "HooksManager",
    "InjectionClassifier",
    "LLMInjectionClassifier",
    "LLMProvider",
    "LogLevel",
    "LoggingHook",
    "Message",
    "MetricsCollector",
    "MistralProvider",
    "ModelRouter",
    "OllamaProvider",
    "OpenAIProvider",
    "PendingReviewError",
    "PolicyEngine",
    "PolicyRule",
    "PolicyViolationError",
    "PromptClient",
    "PromptResult",
    "ProviderConfig",
    "ProviderFactory",
    "ProviderRegistry",
    "ProviderResult",
    "ProviderType",
    "RateLimitBackend",
    "RateLimitExceededError",
    "RateLimitHook",
    "RateLimiter",
    "RateLimiterBackend",
    "RedisRateLimitBackend",
    "RedisRateLimiter",
    "InMemoryRateLimitBackend",
    "RoutingStrategy",
    "SecurityEngine",
    "SecurityHook",
    "SecurityViolationError",
    "Session",
    "SessionConfig",
    "SessionManager",
    "Span",
    "Template",
    "TemplateRegistry",
    "Tier",
    "TimingHook",
    "Tracer",
    "ValidationHook",
    "WidgetConfig",
    "alert_manager",
    "create_dev_config",
    "create_production_config",
    "hooks_manager",
    "metrics",
    "template_registry",
    "tracer",
]

if _feedback_available:
    __all__ += ["FeedbackLoop", "PromptOutcome"]
