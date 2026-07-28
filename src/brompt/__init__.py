"""Brompt — LLM prompt engine with a unified widget interface."""

__version__ = "1.0.0"
__author__ = "Brompt Team"

from .widget import BromptWidget, PromptResult
from .config import (
    WidgetConfig, ProviderConfig, GenerationConfig, CacheConfig,
    FeedbackConfig, SessionConfig, ProviderType, LogLevel,
    create_dev_config, create_production_config,
)
from .providers import LLMProvider, ProviderResult, ProviderFactory, ProviderRegistry
from .session import Session, SessionManager, Message

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
    "Session", "SessionManager", "Message",
]

if _feedback_available:
    __all__ += ["FeedbackLoop", "PromptOutcome"]
