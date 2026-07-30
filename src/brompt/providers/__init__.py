"""Provider System — async LLM providers with factory and registry."""

from ..providers_core import AsyncAzureOpenAIProvider, AzureOpenAIProvider, LMStudioProvider
from .anthropic_provider import AnthropicProvider
from .base import LLMProvider, ProviderResult
from .factory import ProviderFactory, ProviderRegistry
from .google_provider import GoogleProvider
from .mistral_provider import MistralProvider
from .ollama_provider import OllamaProvider
from .openai_provider import OpenAIProvider

ProviderRegistry.register("openai", OpenAIProvider)
ProviderRegistry.register("anthropic", AnthropicProvider)
ProviderRegistry.register("google", GoogleProvider)
ProviderRegistry.register("mistral", MistralProvider)
ProviderRegistry.register("ollama", OllamaProvider)

__all__ = [
    "AnthropicProvider",
    "AsyncAzureOpenAIProvider",
    "AzureOpenAIProvider",
    "GoogleProvider",
    "LLMProvider",
    "LMStudioProvider",
    "MistralProvider",
    "OllamaProvider",
    "OpenAIProvider",
    "ProviderFactory",
    "ProviderRegistry",
    "ProviderResult",
]
