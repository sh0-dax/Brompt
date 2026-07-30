"""Model Router — cost/latency/quality-based provider selection.

Routes each request to the optimal provider based on a configurable
strategy (cheapest, fastest, best-quality, fallback) after classifying
query complexity via heuristics (no ML model required).
"""

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .providers.base import LLMProvider

logger = logging.getLogger("brompt.router")


class RoutingStrategy(str, Enum):
    CHEAPEST = "cheapest"
    FASTEST = "fastest"
    BEST_QUALITY = "best_quality"
    FALLBACK = "fallback"


class ComplexityLevel(str, Enum):
    SIMPLE = "simple"
    MEDIUM = "medium"
    COMPLEX = "complex"


@dataclass
class Route:
    provider: str
    model: str
    estimated_cost: float
    estimated_latency_ms: float
    quality_score: float
    complexity: ComplexityLevel = ComplexityLevel.MEDIUM


@dataclass
class ProviderProfile:
    name: str
    provider_class: type
    model: str
    cost_per_1k_input: float
    cost_per_1k_output: float
    latency_p50_ms: float
    quality_score: float
    supports_complexity: set[ComplexityLevel] = field(
        default_factory=lambda: {ComplexityLevel.SIMPLE, ComplexityLevel.MEDIUM, ComplexityLevel.COMPLEX}
    )


_PROVIDER_PROFILES: dict[str, ProviderProfile] = {}


def register_provider_profile(profile: ProviderProfile):
    _PROVIDER_PROFILES[profile.name] = profile


def _init_default_profiles():
    if _PROVIDER_PROFILES:
        return
    register_provider_profile(ProviderProfile(
        name="openai", provider_class=None, model="gpt-4o",
        cost_per_1k_input=2.50, cost_per_1k_output=10.00,
        latency_p50_ms=1200, quality_score=0.92,
        supports_complexity={ComplexityLevel.SIMPLE, ComplexityLevel.MEDIUM, ComplexityLevel.COMPLEX},
    ))
    register_provider_profile(ProviderProfile(
        name="anthropic", provider_class=None, model="claude-3-5-sonnet",
        cost_per_1k_input=3.00, cost_per_1k_output=15.00,
        latency_p50_ms=1500, quality_score=0.94,
        supports_complexity={ComplexityLevel.SIMPLE, ComplexityLevel.MEDIUM, ComplexityLevel.COMPLEX},
    ))
    register_provider_profile(ProviderProfile(
        name="google", provider_class=None, model="gemini-2.0-flash",
        cost_per_1k_input=0.15, cost_per_1k_output=0.60,
        latency_p50_ms=800, quality_score=0.85,
        supports_complexity={ComplexityLevel.SIMPLE, ComplexityLevel.MEDIUM},
    ))
    register_provider_profile(ProviderProfile(
        name="mistral", provider_class=None, model="mistral-large",
        cost_per_1k_input=2.00, cost_per_1k_output=6.00,
        latency_p50_ms=1100, quality_score=0.88,
        supports_complexity={ComplexityLevel.SIMPLE, ComplexityLevel.MEDIUM, ComplexityLevel.COMPLEX},
    ))
    register_provider_profile(ProviderProfile(
        name="ollama", provider_class=None, model="llama3",
        cost_per_1k_input=0.0, cost_per_1k_output=0.0,
        latency_p50_ms=3000, quality_score=0.75,
        supports_complexity={ComplexityLevel.SIMPLE, ComplexityLevel.MEDIUM},
    ))


_init_default_profiles()


class ModelRouter:
    def __init__(self):
        self._providers: dict[str, LLMProvider] = {}
        self._latency_history: dict[str, list[float]] = {}

    def register_provider(self, name: str, provider: LLMProvider):
        self._providers[name] = provider

    def register_providers(self, providers: dict[str, LLMProvider]):
        self._providers.update(providers)

    def _record_latency(self, name: str, latency_ms: float):
        if name not in self._latency_history:
            self._latency_history[name] = []
        self._latency_history[name].append(latency_ms)
        if len(self._latency_history[name]) > 100:
            self._latency_history[name] = self._latency_history[name][-100:]

    def _estimated_latency(self, name: str) -> float:
        history = self._latency_history.get(name, [])
        if history:
            return sum(history) / len(history)
        profile = _PROVIDER_PROFILES.get(name)
        return profile.latency_p50_ms if profile else 2000.0

    @staticmethod
    def classify_complexity(query: str) -> ComplexityLevel:
        """Heuristic-only complexity classification — no ML model needed.

        Uses token count, code markers, math symbols, and keyword patterns
        to estimate whether a query is simple, medium, or complex.
        """
        if not query or not query.strip():
            return ComplexityLevel.SIMPLE

        word_count = len(query.split())
        has_code = bool(re.search(r'(```|def |class |function |import |from\s+\w+\s+import|const |let |var )', query))
        has_math = bool(re.search(r'[∫∑∏√∂∆∇πθλ]|\\\(|\\\[|\\\\\(|\\\\\[', query))
        has_multi_paragraph = query.count('\n\n') >= 3
        has_analytical_keywords = bool(re.search(
            r'\b(compare|contrast|analyze|synthesize|evaluate|critique|justify|reason|explain\s+why|implications|tradeoffs|root.cause)\b',
            query, re.IGNORECASE,
        ))
        has_multi_step = bool(re.search(
            r'\b(steps?\s+\d|firstly|secondly|finally|phase\s+\d|stage\s+\d|part\s+\d)',
            query, re.IGNORECASE,
        ))
        has_long_words = any(len(w) > 20 for w in query.split())

        if word_count > 200 or has_math or (has_code and word_count > 30):
            return ComplexityLevel.COMPLEX
        if word_count > 60 or has_code or has_multi_paragraph or has_analytical_keywords or has_multi_step or has_long_words:  # noqa: E501
            return ComplexityLevel.MEDIUM
        return ComplexityLevel.SIMPLE

    def score_providers(self, complexity: ComplexityLevel) -> list[Route]:
        """Score all registered providers for the given complexity level.

        Returns a list of Route objects sorted by quality_score descending.
        """
        routes: list[Route] = []
        for name in self._providers:
            profile = _PROVIDER_PROFILES.get(name)
            if profile is None:
                continue
            if complexity not in profile.supports_complexity:
                continue
            cost = profile.cost_per_1k_input + profile.cost_per_1k_output
            latency = self._estimated_latency(name)
            routes.append(Route(
                provider=name,
                model=profile.model,
                estimated_cost=cost,
                estimated_latency_ms=latency,
                quality_score=profile.quality_score,
                complexity=complexity,
            ))
        routes.sort(key=lambda r: r.quality_score, reverse=True)
        return routes

    async def route(
        self,
        query: str,
        strategy: RoutingStrategy = RoutingStrategy.CHEAPEST,
    ) -> Optional[Route]:
        """Select the optimal provider for *query* under *strategy*.

        Returns None if no provider can handle the query's complexity.
        """
        complexity = self.classify_complexity(query)
        candidates = self.score_providers(complexity)
        if not candidates:
            logger.warning("No provider supports complexity level: %s", complexity)
            return None

        if strategy == RoutingStrategy.CHEAPEST:
            selected = min(candidates, key=lambda r: r.estimated_cost)
        elif strategy == RoutingStrategy.FASTEST:
            selected = min(candidates, key=lambda r: r.estimated_latency_ms)
        elif strategy == RoutingStrategy.BEST_QUALITY:
            selected = max(candidates, key=lambda r: r.quality_score)
        elif strategy == RoutingStrategy.FALLBACK:
            selected = max(candidates, key=lambda r: r.quality_score)
        else:
            selected = candidates[0]

        logger.info(
            "Route [%s]: %s/%s — cost=%.4f, latency=%.0fms, quality=%.2f, complexity=%s",
            strategy.value, selected.provider, selected.model,
            selected.estimated_cost, selected.estimated_latency_ms,
            selected.quality_score, complexity.value,
        )
        return selected

    def available_providers(self) -> list[str]:
        return list(self._providers.keys())

    def __repr__(self) -> str:
        return f"ModelRouter(providers={list(self._providers.keys())})"
