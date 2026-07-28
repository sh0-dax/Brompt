"""Per-provider pricing estimates for cost tracking.

Rates are approximate public USD per 1K tokens (as of mid-2026).
Update these as providers change their pricing.
"""

PRICING_TABLE: dict[str, dict[str, float]] = {
    "gemini":   {"input": 0.15,  "output": 0.60},
    "openai":   {"input": 2.50,  "output": 10.00},
    "gpt":      {"input": 2.50,  "output": 10.00},
    "anthropic":{"input": 3.00,  "output": 15.00},
    "claude":   {"input": 3.00,  "output": 15.00},
    "mistral":  {"input": 2.00,  "output": 6.00},
    "azure":    {"input": 2.50,  "output": 10.00},
    "ollama":   {"input": 0.0,   "output": 0.0},
    "lmstudio": {"input": 0.0,   "output": 0.0},
}


def _lookup(provider_name: str) -> dict[str, float]:
    name = provider_name.lower()
    for key, rates in PRICING_TABLE.items():
        if key in name:
            return rates
    return {"input": 0.0, "output": 0.0}


def estimate_cost(provider_name: str, prompt_tokens: int, completion_tokens: int) -> float:
    rates = _lookup(provider_name)
    return round((prompt_tokens / 1000) * rates["input"] + (completion_tokens / 1000) * rates["output"], 6)
