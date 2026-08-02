"""Unit tests for the Redis-backed (cross-process) budget ledger.

Uses fakeredis so these tests exercise the atomic accounting without a
live Redis server.  No Lua is involved (INCRBYFLOAT/INCR/EXPIRE only), so
fakeredis works without the 'lua' extra.
"""

import pytest

fakeredis = pytest.importorskip("fakeredis")

from brompt.budget import RedisBudgetLedger  # noqa: E402
from brompt.config import BudgetConfig  # noqa: E402


def make_client():
    return fakeredis.FakeStrictRedis()


class TestRedisBudgetLedger:
    def test_starts_at_zero(self):
        ledger = RedisBudgetLedger(make_client())
        assert ledger.spent() == 0.0
        assert ledger.count() == 0

    def test_add_cost_accumulates_and_counts(self):
        ledger = RedisBudgetLedger(make_client())
        ledger.add_cost(1.25)
        ledger.add_cost(0.75)
        assert ledger.spent() == 2.0
        assert ledger.count() == 2

    def test_shared_across_two_ledgers_same_redis(self):
        client = make_client()
        a = RedisBudgetLedger(client)
        b = RedisBudgetLedger(client)
        a.add_cost(5.0)
        assert b.spent() == 5.0
        assert b.count() == 1

    def test_close_is_best_effort(self):
        ledger = RedisBudgetLedger(make_client())
        ledger.close()  # must not raise


class TestBudgetConfigWithBackend:
    def test_check_budget_reads_live_backend(self):
        client = make_client()
        ledger = RedisBudgetLedger(client)
        cfg = BudgetConfig(max_daily_cost=10.0, backend=ledger)

        assert cfg.check_budget(2.0) is True
        ledger.add_cost(9.5)
        assert cfg.check_budget(2.0) is False  # 9.5 + 2.0 > 10.0

    def test_shared_daily_cap_across_instances(self):
        client = make_client()
        cfg_a = BudgetConfig(max_daily_cost=10.0, backend=RedisBudgetLedger(client))
        cfg_b = BudgetConfig(max_daily_cost=10.0, backend=RedisBudgetLedger(client))

        assert cfg_a.check_budget(6.0) is True
        cfg_a.add_cost(6.0)
        # cfg_b sees the spend recorded by cfg_a and rejects the request.
        assert cfg_b.check_budget(5.0) is False

    def test_alert_level_reflects_shared_spend(self):
        ledger = RedisBudgetLedger(make_client())
        cfg = BudgetConfig(max_daily_cost=10.0, alert_threshold=0.8, backend=ledger)
        assert cfg.get_alert_level() == "normal"
        ledger.add_cost(8.5)
        assert cfg.get_alert_level() == "warning"
        ledger.add_cost(1.5)
        assert cfg.get_alert_level() == "exceeded"

    def test_to_dict_reports_backend(self):
        cfg = BudgetConfig(max_daily_cost=10.0, backend=RedisBudgetLedger(make_client()))
        snapshot = cfg.to_dict()
        assert snapshot["backend"] == "RedisBudgetLedger"
        assert snapshot["daily_spent"] == 0.0

    def test_in_process_remains_backward_compatible(self):
        cfg = BudgetConfig(max_daily_cost=10.0)
        cfg.add_cost(3.0)
        assert cfg.daily_spent == 3.0
        assert cfg.request_count == 1
        assert cfg.to_dict()["backend"] == "in-process"
        assert cfg.check_budget(8.0) is False  # 3.0 + 8.0 > 10.0


class TestWidgetWiring:
    def test_prompt_client_injects_backend_from_url(self, monkeypatch):
        from brompt.config import (
            CacheConfig,
            ComplianceConfig,
            FeedbackConfig,
            LoggingConfig,
            LogLevel,
            ProviderConfig,
            ProviderType,
            WidgetConfig,
        )
        from brompt.providers.base import LLMProvider
        from brompt.widget import PromptClient

        class DummyProvider(LLMProvider):
            def _setup_client(self):
                self._client = None

            async def generate(self, prompt, **kwargs):
                return "dummy"

            async def stream(self, prompt, **kwargs):
                yield "dummy"

            async def validate_api_key(self):
                return True

        monkeypatch.setattr(
            "brompt.widget.ProviderFactory.from_config", lambda cfg: DummyProvider("fake-model")
        )
        ledger = RedisBudgetLedger(make_client())

        def fake_from_url(url, key_prefix="brompt:budget"):
            assert url == "redis://localhost:6379/0"
            return ledger

        monkeypatch.setattr("brompt.budget.RedisBudgetLedger.from_url", fake_from_url)

        config = WidgetConfig(
            provider=ProviderConfig(type=ProviderType.LOCAL, model="fake-model"),
            logging=LoggingConfig(level=LogLevel.WARNING, file_path=None),
            cache=CacheConfig(enabled=False),
            feedback=FeedbackConfig(enabled=False),
            budget_redis_url="redis://localhost:6379/0",
            compliance=ComplianceConfig(enabled=True, budget=BudgetConfig(max_daily_cost=10.0)),
        )
        client = PromptClient(config=config)
        assert client._budget is not None
        assert client._budget.backend is ledger

        assert client._budget.check_budget(3.0) is True
        client._budget.add_cost(4.0)
        assert ledger.spent() == 4.0
        assert ledger.count() == 1
