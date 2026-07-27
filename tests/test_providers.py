"""Unit tests for the provider abstraction."""

import pytest

from brompt.providers import (
    AnthropicProvider,
    OpenAIProvider,
    OllamaProvider,
    GeminiProvider,
    MistralProvider,
    AzureOpenAIProvider,
    LMStudioProvider,
    ProviderError,
    build_provider_from_env,
)


class TestAnthropicProvider:
    def test_requires_key(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        with pytest.raises(ProviderError, match="No Anthropic API key"):
            AnthropicProvider()


class TestOpenAIProvider:
    def test_requires_key(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        with pytest.raises(ProviderError, match="No OpenAI API key"):
            OpenAIProvider()


class TestGeminiProvider:
    def test_requires_key(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        with pytest.raises(ProviderError, match="No Gemini API key"):
            GeminiProvider()


class TestMistralProvider:
    def test_requires_key(self, monkeypatch):
        monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
        with pytest.raises(ProviderError, match="No Mistral API key"):
            MistralProvider()


class TestAzureOpenAIProvider:
    def test_requires_key(self, monkeypatch):
        monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
        monkeypatch.delenv("AZURE_OPENAI_DEPLOYMENT", raising=False)
        with pytest.raises(ProviderError, match="No Azure OpenAI API key"):
            AzureOpenAIProvider()

    def test_requires_endpoint(self, monkeypatch):
        monkeypatch.setenv("AZURE_OPENAI_API_KEY", "fake-key")
        monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
        monkeypatch.delenv("AZURE_OPENAI_DEPLOYMENT", raising=False)
        with pytest.raises(ProviderError, match="No Azure OpenAI endpoint"):
            AzureOpenAIProvider()

    def test_requires_deployment(self, monkeypatch):
        monkeypatch.setenv("AZURE_OPENAI_API_KEY", "fake-key")
        monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://test.openai.azure.com")
        monkeypatch.delenv("AZURE_OPENAI_DEPLOYMENT", raising=False)
        with pytest.raises(ProviderError, match="No Azure OpenAI deployment"):
            AzureOpenAIProvider()


class TestLMStudioProvider:
    def test_default_host(self, monkeypatch):
        monkeypatch.delenv("LM_STUDIO_HOST", raising=False)
        provider = LMStudioProvider()
        assert provider.host == "http://localhost:1234/v1"

    def test_custom_host(self):
        provider = LMStudioProvider(host="http://192.168.1.100:1234/v1")
        assert provider.host == "http://192.168.1.100:1234/v1"


class TestOllamaProvider:
    def test_default_host(self, monkeypatch):
        monkeypatch.delenv("OLLAMA_HOST", raising=False)
        provider = OllamaProvider()
        assert provider.host == "http://localhost:11434"

    def test_custom_host(self):
        provider = OllamaProvider(host="http://192.168.1.100:11434")
        assert provider.host == "http://192.168.1.100:11434"


class TestBuildProviderFromEnv:
    def test_returns_none_without_any_key(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
        monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OLLAMA_HOST", raising=False)
        monkeypatch.delenv("LM_STUDIO_HOST", raising=False)
        assert build_provider_from_env() is None

    def test_returns_anthropic_when_key_set(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-fake-key")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        provider = build_provider_from_env()
        assert provider is not None
        assert isinstance(provider, AnthropicProvider)

    def test_returns_openai_when_key_set(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-fake-key")
        provider = build_provider_from_env()
        assert provider is not None
        assert isinstance(provider, OpenAIProvider)

    def test_returns_ollama_when_host_set(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
        monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
        monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
        provider = build_provider_from_env()
        assert provider is not None
        assert isinstance(provider, OllamaProvider)

    def test_returns_lmstudio_when_host_set(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
        monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OLLAMA_HOST", raising=False)
        monkeypatch.setenv("LM_STUDIO_HOST", "http://localhost:1234/v1")
        provider = build_provider_from_env()
        assert provider is not None
        assert isinstance(provider, LMStudioProvider)
