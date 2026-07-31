"""Tests for the dataclass config surface: BudgetConfig, ComplianceConfig,
WidgetConfig loading/validation, and RoutingConfig defaults."""

import pytest

from brompt.config import (
    BudgetConfig,
    CacheConfig,
    ComplianceConfig,
    FeedbackConfig,
    GenerationConfig,
    LoggingConfig,
    LogLevel,
    ProviderConfig,
    ProviderType,
    RoutingConfig,
    WidgetConfig,
)


class TestBudgetConfig:
    def test_validates_thresholds(self):
        with pytest.raises(ValueError):
            BudgetConfig(max_daily_cost=0)
        with pytest.raises(ValueError):
            BudgetConfig(max_per_request=0)
        with pytest.raises(ValueError):
            BudgetConfig(alert_threshold=1.5)

    def test_check_budget_daily_cap(self):
        budget = BudgetConfig(max_daily_cost=10.0, max_per_request=5.0)
        assert budget.check_budget(estimated_cost=3.0) is True
        budget.add_cost(8.0)
        assert budget.check_budget(estimated_cost=3.0) is False

    def test_check_budget_per_request_cap(self):
        budget = BudgetConfig(max_daily_cost=100.0, max_per_request=5.0)
        assert budget.check_budget(estimated_cost=5.0) is True
        assert budget.check_budget(estimated_cost=6.0) is False

    def test_add_cost_tracks_ledger(self):
        budget = BudgetConfig(max_daily_cost=100.0)
        budget.add_cost(2.5)
        budget.add_cost(3.5)
        assert budget.daily_spent == pytest.approx(6.0)
        assert budget.request_count == 2

    def test_get_alert_level(self):
        budget = BudgetConfig(max_daily_cost=10.0, alert_threshold=0.8)
        assert budget.get_alert_level() == "normal"
        budget.add_cost(9.0)
        assert budget.get_alert_level() == "warning"
        budget.add_cost(9.0)
        assert budget.get_alert_level() == "exceeded"

    def test_to_dict_snapshot(self):
        budget = BudgetConfig(max_daily_cost=10.0)
        budget.add_cost(1.0)
        snap = budget.to_dict()
        assert snap["max_daily_cost"] == 10.0
        assert snap["daily_spent"] == pytest.approx(1.0)
        assert snap["request_count"] == 1
        assert snap["alert_level"] == "normal"


class TestComplianceConfig:
    def test_rejects_invalid_review_action(self):
        with pytest.raises(ValueError):
            ComplianceConfig(human_review_action="delete")

    def test_defaults(self):
        cfg = ComplianceConfig()
        assert cfg.mode == "standard"
        assert cfg.human_review_action == "return"
        assert isinstance(cfg.budget, BudgetConfig)


class TestWidgetConfig:
    def test_validate_requires_api_key_for_cloud(self):
        cfg = WidgetConfig(
            provider=ProviderConfig(type=ProviderType.OPENAI, model="gpt-4o"),
            logging=LoggingConfig(level=LogLevel.WARNING, file_path=None),
            cache=CacheConfig(enabled=False),
            feedback=FeedbackConfig(enabled=False),
        )
        errors = cfg.validate()
        assert any("API key required" in e for e in errors)

    def test_validate_passes_for_local(self):
        cfg = WidgetConfig(
            provider=ProviderConfig(type=ProviderType.LOCAL, model="llama3.2"),
            logging=LoggingConfig(level=LogLevel.WARNING, file_path=None),
            cache=CacheConfig(enabled=False),
            feedback=FeedbackConfig(enabled=False),
        )
        assert cfg.validate() == []

    def test_validate_rejects_huge_max_tokens(self):
        cfg = WidgetConfig(
            provider=ProviderConfig(type=ProviderType.LOCAL),
            generation=GenerationConfig(max_tokens=200000),
            logging=LoggingConfig(level=LogLevel.WARNING, file_path=None),
            cache=CacheConfig(enabled=False),
            feedback=FeedbackConfig(enabled=False),
        )
        errors = cfg.validate()
        assert any("max_tokens too large" in e for e in errors)

    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("BROMPT_PROVIDER", "anthropic")
        monkeypatch.setenv("BROMPT_MODEL", "claude-sonnet-4-5")
        monkeypatch.setenv("BROMPT_TEMPERATURE", "0.2")
        monkeypatch.setenv("BROMPT_MAX_TOKENS", "1500")
        monkeypatch.setenv("BROMPT_ROUTING_ENABLED", "true")
        monkeypatch.delenv("BROMPT_REDIS_URL", raising=False)

        cfg = WidgetConfig.from_env()
        assert cfg.provider.type == ProviderType.ANTHROPIC
        assert cfg.provider.model == "claude-sonnet-4-5"
        assert cfg.generation.temperature == 0.2
        assert cfg.generation.max_tokens == 1500
        assert cfg.routing.enabled is True

    def test_routing_defaults(self):
        assert RoutingConfig().enabled is False
        assert RoutingConfig(enabled=True).enabled is True
