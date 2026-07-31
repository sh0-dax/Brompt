"""Tests for the pricing registry and provider-name normalization.

These guard the cost-tracking fix: `estimate_cost`/`calculate_cost` must
produce non-zero, correct costs for real provider class names (the README
Quick Start path) and for bare model names.
"""

import pytest

from brompt.pricing import calculate_cost, estimate_cost


class TestEstimateCost:
    def test_provider_class_name(self):
        cost = estimate_cost("OpenAIProvider", 200, 100)
        assert cost > 0
        assert cost == pytest.approx(0.0015)

    def test_async_provider_class_name(self):
        cost = estimate_cost("AsyncAnthropicProvider", 150, 50)
        assert cost > 0
        assert cost == pytest.approx(0.0012)

    def test_bare_model_name(self):
        cost = estimate_cost("gpt-4o", 200, 100)
        assert cost > 0
        assert cost == pytest.approx(0.0015)

    def test_azure_provider_class(self):
        cost = estimate_cost("AzureOpenAIProvider", 200, 100)
        assert cost == pytest.approx(0.0015)

    def test_local_provider_is_free(self):
        assert estimate_cost("OllamaProvider", 200, 100) == 0.0
        assert estimate_cost("LMStudioProvider", 200, 100) == 0.0

    def test_unknown_provider_is_zero(self):
        assert estimate_cost("FakeProvider", 200, 100) == 0.0


class TestCalculateCost:
    def test_exact_provider_model_key(self):
        cost = calculate_cost("openai", "gpt-4o", input_tokens=1_000_000, output_tokens=1_000_000)
        assert cost == pytest.approx(12.5)

    def test_provider_prefix_fallback(self):
        cost = calculate_cost("openai", "unknown-model", input_tokens=200, output_tokens=100)
        assert cost == pytest.approx(0.0015)

    def test_cached_input_pricing(self):
        cost = calculate_cost(
            "openai", "gpt-4o",
            input_tokens=100, output_tokens=100, cached_input_tokens=100,
        )
        assert cost == pytest.approx(0.00025 + 0.000125 + 0.001)

    def test_zero_tokens_is_zero(self):
        assert calculate_cost("openai", "gpt-4o") == 0.0
