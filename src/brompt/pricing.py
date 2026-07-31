"""Per-model pricing registry for cost tracking.

Rates are approximate public USD per 1M tokens (as of mid-2026).
Update these as providers change their pricing.
"""


# ── per-model pricing (input / output / cached_input / cache_write) ──────────
# Rates in USD per 1M tokens.  Zero means free / local.
PRICING_REGISTRY: dict[str, dict[str, float]] = {
    # ── Gemini ──────────────────────────────────────────────────────────────
    "gemini/gemini-2.5-flash":   {"input": 0.15, "output": 0.60, "cached_input": 0.075, "cache_write": 0.0},
    "gemini/gemini-2.5-pro":     {"input": 1.25, "output": 5.00, "cached_input": 0.625, "cache_write": 0.0},
    "gemini/gemini-2.0-flash":   {"input": 0.10, "output": 0.40, "cached_input": 0.05,  "cache_write": 0.0},
    "gemini/gemini-1.5-flash":   {"input": 0.075,"output": 0.30, "cached_input": 0.0375,"cache_write": 0.0},
    "gemini/gemini-1.5-pro":     {"input": 1.25, "output": 5.00, "cached_input": 0.625, "cache_write": 0.0},
    # ── OpenAI ──────────────────────────────────────────────────────────────
    "openai/gpt-4o":             {"input": 2.50, "output": 10.00, "cached_input": 1.25, "cache_write": 0.0},
    "openai/gpt-4o-mini":        {"input": 0.15, "output": 0.60, "cached_input": 0.075, "cache_write": 0.0},
    "openai/gpt-4-turbo":        {"input": 10.00,"output": 30.00, "cached_input": 5.00, "cache_write": 0.0},
    "openai/o1":                 {"input": 15.00,"output": 60.00, "cached_input": 7.50, "cache_write": 0.0},
    "openai/o3-mini":            {"input": 1.10, "output": 4.40, "cached_input": 0.55, "cache_write": 0.0},
    # ── Anthropic ───────────────────────────────────────────────────────────
    "anthropic/claude-sonnet-4-5":{"input": 3.00, "output": 15.00, "cached_input": 1.50, "cache_write": 0.0},
    "anthropic/claude-sonnet-4": {"input": 3.00, "output": 15.00, "cached_input": 1.50, "cache_write": 0.0},
    "anthropic/claude-3-5-sonnet":{"input": 3.00, "output": 15.00, "cached_input": 1.50, "cache_write": 0.0},
    "anthropic/claude-3-haiku":  {"input": 0.25, "output": 1.25, "cached_input": 0.125, "cache_write": 0.0},
    "anthropic/claude-opus-4":   {"input": 15.00,"output": 75.00, "cached_input": 7.50, "cache_write": 0.0},
    # ── Mistral ─────────────────────────────────────────────────────────────
    "mistral/mistral-large-latest":{"input": 2.00, "output": 6.00, "cached_input": 1.00, "cache_write": 0.0},
    "mistral/mistral-small":     {"input": 1.00, "output": 3.00, "cached_input": 0.50, "cache_write": 0.0},
    # ── Azure OpenAI ────────────────────────────────────────────────────────
    "azure/gpt-4o":              {"input": 2.50, "output": 10.00, "cached_input": 1.25, "cache_write": 0.0},
    # ── Local (free) ────────────────────────────────────────────────────────
    "ollama/llama3.2":           {"input": 0.0, "output": 0.0, "cached_input": 0.0, "cache_write": 0.0},
    "ollama/mistral":            {"input": 0.0, "output": 0.0, "cached_input": 0.0, "cache_write": 0.0},
    "lmstudio/default":          {"input": 0.0, "output": 0.0, "cached_input": 0.0, "cache_write": 0.0},
}


# ── provider-name aliases ────────────────────────────────────────────────────
# Map provider class names (and common aliases) to registry key families.
_PROVIDER_ALIASES: dict[str, str] = {
    "openai": "openai",
    "azureopenai": "azure",
    "azure": "azure",
    "anthropic": "anthropic",
    "claude": "anthropic",
    "google": "gemini",
    "gemini": "gemini",
    "ollama": "ollama",
    "lmstudio": "lmstudio",
    "mistral": "mistral",
    "local": "local",
}


def _normalize_provider(name: str) -> str:
    """Normalize a provider name/class to its registry key family.

    Handles ``OpenAIProvider`` -> ``openai``, ``AsyncAnthropicProvider`` ->
    ``anthropic``, ``AzureOpenAIProvider`` -> ``azure``, ``gemini/gemini-2.5-flash``
    -> ``gemini``, and ``FakeProvider`` -> ``fake``.
    """
    lowered = name.lower().strip()
    if lowered.startswith("async"):
        lowered = lowered[len("async"):]
    if lowered.endswith("provider"):
        lowered = lowered[:-len("provider")]
    lowered = lowered.split("/", 1)[0].strip()
    return _PROVIDER_ALIASES.get(lowered, lowered)


def _lookup_model(provider: str, model: str) -> dict[str, float]:
    """Find pricing by ``provider/model`` key, falling back to provider-only,
    bare-model, and provider-as-model lookups."""
    norm_provider = _normalize_provider(provider)
    model_lower = model.lower()

    key = f"{norm_provider}/{model_lower}" if norm_provider else model_lower
    if key in PRICING_REGISTRY:
        return PRICING_REGISTRY[key]

    if norm_provider:
        for k, rates in PRICING_REGISTRY.items():
            if k.startswith(norm_provider + "/"):
                return rates

    for candidate in (model_lower, norm_provider):
        if not candidate or candidate == "default":
            continue
        for k, rates in PRICING_REGISTRY.items():
            if k.endswith("/" + candidate):
                return rates

    return {"input": 0.0, "output": 0.0, "cached_input": 0.0, "cache_write": 0.0}


def calculate_cost(
    provider: str,
    model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cached_input_tokens: int = 0,
) -> float:
    """Calculate cost in USD for a given provider/model/token count."""
    rates = _lookup_model(provider, model)
    input_cost = (input_tokens / 1_000_000) * rates["input"]
    cached_cost = (cached_input_tokens / 1_000_000) * rates.get("cached_input", rates["input"])
    output_cost = (output_tokens / 1_000_000) * rates["output"]
    return round(input_cost + cached_cost + output_cost, 6)


def estimate_cost(provider_name: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Legacy shim — delegates to ``calculate_cost`` with a best-guess model."""
    return calculate_cost(provider_name, "default", prompt_tokens, completion_tokens)
