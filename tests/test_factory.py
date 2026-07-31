"""Tests for the provider factory and registry."""

import pytest

from brompt.config import ProviderConfig, ProviderType
from brompt.providers import ProviderFactory, ProviderRegistry
from brompt.providers.base import LLMProvider, ProviderResult


class StubProvider(LLMProvider):
    def __init__(self, model="stub", api_key=None, **kwargs):
        super().__init__(model=model, api_key=api_key, **kwargs)

    def _setup_client(self):
        self._client = None

    async def generate(self, prompt, **kwargs):
        return ProviderResult(text="stub", model=self.model)

    async def stream(self, prompt, **kwargs):
        yield "stub"

    async def validate_api_key(self):
        return True


@pytest.fixture(autouse=True)
def _clean_registry():
    saved = dict(ProviderRegistry._providers)
    ProviderRegistry._providers.clear()
    try:
        yield
    finally:
        ProviderRegistry._providers.clear()
        ProviderRegistry._providers.update(saved)


class TestProviderRegistry:
    def test_register_get_list(self):
        ProviderRegistry.register("stub", StubProvider)
        assert ProviderRegistry.list_providers() == ["stub"]
        assert ProviderRegistry.get("stub") is StubProvider

    def test_duplicate_registration_raises(self):
        ProviderRegistry.register("stub", StubProvider)
        with pytest.raises(ValueError):
            ProviderRegistry.register("stub", StubProvider)

    def test_unknown_provider_raises(self):
        with pytest.raises(ValueError):
            ProviderRegistry.get("nope")

    def test_rejects_non_llm_provider(self):
        with pytest.raises(TypeError):
            ProviderRegistry.register("bad", dict)

    def test_unregister_and_clear(self):
        ProviderRegistry.register("stub", StubProvider)
        ProviderRegistry.unregister("stub")
        assert ProviderRegistry.list_providers() == []
        ProviderRegistry.register("stub", StubProvider)
        ProviderRegistry.clear()
        assert ProviderRegistry.list_providers() == []


class TestProviderFactory:
    def test_create_custom_registered(self):
        ProviderRegistry.register("stub", StubProvider)
        provider = ProviderFactory.create(
            ProviderType.CUSTOM, model="stub-1", custom_provider_name="stub",
        )
        assert isinstance(provider, StubProvider)
        assert provider.model == "stub-1"

    def test_create_custom_requires_name(self):
        with pytest.raises(ValueError):
            ProviderFactory.create(ProviderType.CUSTOM, model="x")

    def test_unknown_provider_type(self):
        with pytest.raises(ValueError):
            ProviderFactory.create(ProviderType.LOCAL, model="x", custom_provider_name="stub")

    def test_from_config_local(self, monkeypatch):
        monkeypatch.setattr(ProviderFactory, "_type_mapping", {
            ProviderType.LOCAL: "stub",
        })
        ProviderRegistry.register("stub", StubProvider)
        cfg = ProviderConfig(type=ProviderType.LOCAL, model="llama3.2")
        provider = ProviderFactory.from_config(cfg)
        assert isinstance(provider, StubProvider)
        assert provider.model == "llama3.2"
