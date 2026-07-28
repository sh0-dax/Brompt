"""Provider Factory + Registry Pattern."""

from typing import Type, Optional

from .base import LLMProvider
from ..config import ProviderType


class ProviderRegistry:
    _providers: dict[str, Type[LLMProvider]] = {}

    @classmethod
    def register(cls, name: str, provider_class: Type[LLMProvider]):
        if name in cls._providers:
            raise ValueError(f"Provider '{name}' already registered")
        if not issubclass(provider_class, LLMProvider):
            raise TypeError(f"{provider_class.__name__} must inherit from LLMProvider")
        cls._providers[name] = provider_class

    @classmethod
    def get(cls, name: str) -> Type[LLMProvider]:
        if name not in cls._providers:
            available = list(cls._providers.keys())
            raise ValueError(f"Unknown provider '{name}'. Available: {available}")
        return cls._providers[name]

    @classmethod
    def list_providers(cls) -> list[str]:
        return list(cls._providers.keys())

    @classmethod
    def unregister(cls, name: str):
        cls._providers.pop(name, None)

    @classmethod
    def clear(cls):
        cls._providers.clear()


class ProviderFactory:
    _type_mapping = {
        ProviderType.OPENAI: "openai",
        ProviderType.ANTHROPIC: "anthropic",
        ProviderType.GOOGLE: "google",
        ProviderType.LOCAL: "ollama",
    }

    @classmethod
    def create(
        cls,
        provider_type: ProviderType,
        model: str,
        api_key: Optional[str] = None,
        **kwargs
    ) -> LLMProvider:
        if provider_type == ProviderType.CUSTOM:
            custom_name = kwargs.pop("custom_provider_name", None)
            if custom_name is None:
                raise ValueError("ProviderType.CUSTOM requires custom_provider_name")
            provider_class = ProviderRegistry.get(custom_name)
        else:
            name = cls._type_mapping.get(provider_type)
            if name is None:
                raise ValueError(f"Unknown provider type: {provider_type}")
            provider_class = ProviderRegistry.get(name)
        return provider_class(model=model, api_key=api_key, **kwargs)

    @classmethod
    def from_config(cls, config: "ProviderConfig") -> LLMProvider:
        from ..config import ProviderConfig as PC
        return cls.create(
            provider_type=config.type,
            model=config.model,
            api_key=config.api_key,
            base_url=config.base_url,
            organization_id=config.organization_id,
        )
