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

try:
    from .feedback import FeedbackLoop, PromptOutcome
    _feedback_available = True
except ImportError:
    _feedback_available = False

__all__ = [
    "BromptWidget", "PromptResult",
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
]

if _feedback_available:
    __all__ += ["FeedbackLoop", "PromptOutcome"]
