"""Provider System — async LLM providers with factory and registry."""

from .base import LLMProvider, ProviderResult
from .factory import ProviderFactory, ProviderRegistry
from .openai_provider import OpenAIProvider
from .anthropic_provider import AnthropicProvider
from .google_provider import GoogleProvider
from .mistral_provider import MistralProvider
from .ollama_provider import OllamaProvider

ProviderRegistry.register("openai", OpenAIProvider)
ProviderRegistry.register("anthropic", AnthropicProvider)
ProviderRegistry.register("google", GoogleProvider)
ProviderRegistry.register("mistral", MistralProvider)
ProviderRegistry.register("ollama", OllamaProvider)

__all__ = [
    "LLMProvider",
    "ProviderResult",
    "ProviderFactory",
    "ProviderRegistry",
    "OpenAIProvider",
    "AnthropicProvider",
    "GoogleProvider",
    "MistralProvider",
    "OllamaProvider",
]
