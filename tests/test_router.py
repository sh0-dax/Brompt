"""Tests for ModelRouter with heuristic complexity classification."""

import pytest

from brompt.router import (
    ModelRouter,
    ComplexityLevel,
    RoutingStrategy,
    Route,
    register_provider_profile,
    ProviderProfile,
    _PROVIDER_PROFILES,
)


class TestComplexityClassification:
    def test_simple_query(self):
        assert ModelRouter.classify_complexity("What is the capital of France?") == ComplexityLevel.SIMPLE

    def test_simple_short(self):
        assert ModelRouter.classify_complexity("Hello") == ComplexityLevel.SIMPLE

    def test_medium_word_count(self):
        q = " ".join(["word"] * 70)
        assert ModelRouter.classify_complexity(q) == ComplexityLevel.MEDIUM

    def test_medium_analytical(self):
        q = "Compare and contrast the economic implications of remote work on urban development."
        assert ModelRouter.classify_complexity(q) == ComplexityLevel.MEDIUM

    def test_medium_multi_paragraph(self):
        q = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph.\n\nFourth paragraph."
        assert ModelRouter.classify_complexity(q) == ComplexityLevel.MEDIUM

    def test_complex_code(self):
        # A one-function snippet with low word count is MEDIUM
        q = "Write a Python function that implements merge sort:\n\ndef merge_sort(arr):"
        assert ModelRouter.classify_complexity(q) == ComplexityLevel.MEDIUM

    def test_complex_code_large(self):
        q = "Write a full CRUD API in Python with FastAPI, SQLAlchemy, and Pydantic:\n\n" + "def " + " ".join(["word"] * 35)
        assert ModelRouter.classify_complexity(q) == ComplexityLevel.COMPLEX

    def test_complex_math(self):
        q = "Solve the integral ∫x^2 sin(x) dx using integration by parts."
        assert ModelRouter.classify_complexity(q) == ComplexityLevel.COMPLEX

    def test_complex_long(self):
        q = " ".join(["word"] * 250)
        assert ModelRouter.classify_complexity(q) == ComplexityLevel.COMPLEX

    def test_empty(self):
        assert ModelRouter.classify_complexity("") == ComplexityLevel.SIMPLE
        assert ModelRouter.classify_complexity("   ") == ComplexityLevel.SIMPLE


class TestModelRouter:
    def test_route_no_providers(self):
        router = ModelRouter()
        result = router.score_providers(ComplexityLevel.SIMPLE)
        assert result == []

    def test_route_unregistered_provider_skipped(self):
        router = ModelRouter()
        class FakeProvider:
            pass

        router.register_provider("unknown", FakeProvider())  # type: ignore
        result = router.score_providers(ComplexityLevel.SIMPLE)
        assert result == []

    def test_register_and_score(self):
        router = ModelRouter()

        class FakeProvider:
            pass

        router.register_provider("ollama", FakeProvider())  # type: ignore
        router.register_provider("google", FakeProvider())  # type: ignore

        routes = router.score_providers(ComplexityLevel.SIMPLE)
        names = [r.provider for r in routes]
        assert "ollama" in names
        assert "google" in names

    @pytest.mark.asyncio
    async def test_route_selects_cheapest(self):
        router = ModelRouter()

        class FakeProvider:
            pass

        router.register_provider("ollama", FakeProvider())  # type: ignore
        router.register_provider("openai", FakeProvider())  # type: ignore

        route = await router.route("hello", RoutingStrategy.CHEAPEST)
        assert route is not None
        assert route.provider == "ollama"

    @pytest.mark.asyncio
    async def test_route_selects_best_quality(self):
        router = ModelRouter()

        class FakeProvider:
            pass

        router.register_provider("ollama", FakeProvider())  # type: ignore
        router.register_provider("anthropic", FakeProvider())  # type: ignore

        route = await router.route("hello", RoutingStrategy.BEST_QUALITY)
        assert route is not None
        assert route.provider == "anthropic"

    @pytest.mark.asyncio
    async def test_route_empty_query(self):
        router = ModelRouter()

        class FakeProvider:
            pass

        router.register_provider("google", FakeProvider())  # type: ignore

        route = await router.route("", RoutingStrategy.CHEAPEST)
        assert route is not None

    def test_available_providers(self):
        router = ModelRouter()

        class FakeProvider:
            pass

        router.register_provider("ollama", FakeProvider())  # type: ignore
        assert "ollama" in router.available_providers()

    def test_latency_tracking(self):
        router = ModelRouter()
        router._record_latency("ollama", 100.0)
        router._record_latency("ollama", 200.0)
        assert router._estimated_latency("ollama") == 150.0

    @pytest.mark.asyncio
    async def test_route_complex_best_quality(self):
        router = ModelRouter()

        class FakeProvider:
            pass

        router.register_provider("google", FakeProvider())  # type: ignore
        router.register_provider("anthropic", FakeProvider())  # type: ignore

        # Medium complexity query
        route = await router.route("Compare and contrast two philosophical frameworks", RoutingStrategy.BEST_QUALITY)
        assert route is not None
        assert route.provider == "anthropic"

    def test_repr(self):
        router = ModelRouter()
        r = repr(router)
        assert "ModelRouter" in r
