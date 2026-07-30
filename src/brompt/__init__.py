"""Brompt — LLM prompt engine with a unified widget interface."""

__version__ = "2.0.0"
__author__ = "Brompt Team"

from .widget import PromptClient, PromptResult
from .config import (
    WidgetConfig, ProviderConfig, GenerationConfig, CacheConfig,
    FeedbackConfig, SessionConfig, ProviderType, LogLevel,
    create_dev_config, create_production_config,
)
from .providers import (
    LLMProvider, ProviderResult, ProviderFactory, ProviderRegistry,
    OpenAIProvider, AnthropicProvider, GoogleProvider, MistralProvider, OllamaProvider,
)
from .session import Session, SessionManager, Message
from .core.template_engine import Template, TemplateRegistry, template_registry
from .hooks import HooksManager, hooks_manager, BaseHook, LoggingHook, TimingHook, ValidationHook, AuditHook, RateLimitHook, SecurityHook
from .observability import Tracer, tracer, MetricsCollector, metrics, AlertManager, alert_manager, AlertRule, Span
from .core.engine import BromptEngine
from .circuit_breaker import CircuitBreaker, CircuitBreakerOpenError
from .router import ModelRouter, RoutingStrategy, ComplexityLevel
from .ratelimit import RateLimiter, RateLimiterBackend, RedisRateLimiter, RateLimitExceededError
from .audit import AuditLog
from .security import SecurityEngine, SecurityViolationError
from .classifier import LLMInjectionClassifier, Tier, PendingReviewError, ClassificationResult, InjectionClassifier
from .policy import PolicyEngine, PolicyRule, PolicyViolationError

try:
    from .feedback import FeedbackLoop, PromptOutcome
    _feedback_available = True
except ImportError:
    _feedback_available = False

__all__ = [
    "PromptResult",
    "WidgetConfig", "ProviderConfig", "GenerationConfig",
    "CacheConfig", "FeedbackConfig", "SessionConfig",
    "ProviderType", "LogLevel",
    "create_dev_config", "create_production_config",
    "LLMProvider", "ProviderResult", "ProviderFactory", "ProviderRegistry",
    "OpenAIProvider", "AnthropicProvider", "GoogleProvider", "MistralProvider", "OllamaProvider",
    "Session", "SessionManager", "Message",
    "Template", "TemplateRegistry", "template_registry",
    "HooksManager", "hooks_manager", "BaseHook",
    "LoggingHook", "TimingHook", "ValidationHook", "AuditHook", "RateLimitHook", "SecurityHook",
    "Tracer", "tracer", "MetricsCollector", "metrics", "AlertManager", "alert_manager", "AlertRule", "Span",
    "BromptEngine",
    "CircuitBreaker", "CircuitBreakerOpenError",
    "ModelRouter", "RoutingStrategy", "ComplexityLevel",
    "RateLimiter", "RateLimiterBackend", "RedisRateLimiter", "RateLimitExceededError",
    "AuditLog",
    "SecurityEngine", "SecurityViolationError",
    "LLMInjectionClassifier", "Tier", "PendingReviewError", "ClassificationResult", "InjectionClassifier",
    "PolicyEngine", "PolicyRule", "PolicyViolationError",
]

if _feedback_available:
    __all__ += ["FeedbackLoop", "PromptOutcome"]
