"""Integration tests for compliance-grade PromptClient (audit, replay, policy,
budget, human-in-the-loop, air-gapped)."""

import json

import pytest

from brompt import (
    BudgetExceededError,
    ComplianceConfig,
    PromptClient,
    TamperDetectedError,
)
from brompt.config import (
    BudgetConfig,
    CacheConfig,
    FeedbackConfig,
    LogLevel,
    LoggingConfig,
    ProviderConfig,
    ProviderType,
    WidgetConfig,
)
from brompt.policy import PolicyViolationError
from brompt.providers.base import LLMProvider, ProviderResult
from brompt.schema import ExecutionResult
from brompt.widget import ProviderFactory


class FakeProvider(LLMProvider):
    def __init__(self, text="Fake response", model="fake-model", tokens=10, error=None):
        self._text = text
        self._tokens = tokens
        self._error = error
        super().__init__(model=model)

    def _setup_client(self):
        self._client = None

    async def generate(self, prompt, **kwargs):
        if self._error is not None:
            raise self._error
        return ProviderResult(
            text=self._text,
            model=self.model,
            tokens_used=self._tokens,
            prompt_tokens=self._tokens // 2,
            completion_tokens=self._tokens // 2,
        )

    async def stream(self, prompt, **kwargs):
        yield self._text

    async def validate_api_key(self):
        return True


def make_config():
    return WidgetConfig(
        provider=ProviderConfig(type=ProviderType.LOCAL, model="fake-model"),
        logging=LoggingConfig(level=LogLevel.WARNING, file_path=None),
        cache=CacheConfig(enabled=False),
        feedback=FeedbackConfig(enabled=False),
    )


@pytest.fixture
def client_factory(monkeypatch):
    def _make(compliance=None, audit_path=None, provider=None):
        monkeypatch.setattr(
            ProviderFactory, "from_config", lambda config: provider or FakeProvider()
        )
        return PromptClient(
            config=make_config(),
            audit_log_path=audit_path,
            audit_secret_key="test-secret-key",
            compliance=compliance,
        )

    return _make


@pytest.fixture
def compliant(tmp_path):
    def _make(**overrides):
        compliance = ComplianceConfig(
            enabled=True,
            signing_key="test-secret-key",
            **overrides,
        )
        return compliance

    return _make


class TestAuditTrail:
    async def test_prompt_records_signed_audit_entry(self, tmp_path, client_factory, compliant):
        log_path = str(tmp_path / "audit.log")
        client = client_factory(compliant(), audit_path=log_path)

        result = await client.prompt("Hello compliance")

        assert result.execution_id is not None
        assert result.audit_hash is not None
        assert result.audit_chain_id is not None
        assert result.tamper_check is True
        assert result.compliance_mode == "standard"

        assert client.audit_log.verify() is True
        entries = client.audit_log.read_all()
        assert len(entries) == 1
        assert entries[0]["event"] == "execute"
        assert entries[0]["state_id"] == result.execution_id
        assert entries[0]["is_secure"] is True
        assert "hmac" in entries[0]  # signed

    async def test_prompt_without_audit_still_works(self, client_factory):
        client = client_factory()

        result = await client.prompt("No audit configured")

        assert result.response == "Fake response"
        assert result.audit_hash is None
        assert client.verify_execution(result) is False
        assert client.export_audit_trail() == []

    async def test_provider_error_is_recorded(self, tmp_path, client_factory, compliant):
        log_path = str(tmp_path / "audit.log")
        client = client_factory(compliant(), audit_path=log_path, provider=FakeProvider(error=RuntimeError("boom")))

        with pytest.raises(RuntimeError, match="boom"):
            await client.prompt("will fail")

        entries = client.audit_log.read_all()
        assert entries[0]["event"] == "provider_error"
        assert entries[0]["is_secure"] is False

    async def test_verify_entry_rejects_tampered_log(self, tmp_path, client_factory, compliant):
        log_path = tmp_path / "audit.log"
        client = client_factory(compliant(), audit_path=str(log_path))

        result = await client.prompt("Important request")

        lines = log_path.read_text(encoding="utf-8").splitlines()
        first = json.loads(lines[0])
        first["detail"] = "tampered with!"
        lines[0] = json.dumps(first)
        log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        assert client.verify_execution(result) is False

    async def test_export_audit_trail(self, tmp_path, client_factory, compliant):
        log_path = str(tmp_path / "audit.log")
        client = client_factory(compliant(), audit_path=log_path)

        await client.prompt("First")
        await client.prompt("Second")

        trail = client.export_audit_trail()
        assert len(trail) == 2
        assert all(e["chain_verified"] for e in trail)
        assert trail[0]["id"] != trail[1]["id"]
        assert all(e["signed"] for e in trail)


class TestReplay:
    async def test_replay_chains_new_verifiable_entry(self, tmp_path, client_factory, compliant):
        log_path = str(tmp_path / "audit.log")
        client = client_factory(compliant(), audit_path=log_path)

        original = await client.prompt("Verify this transaction")

        replayed = await client.replay(original.execution_id)

        assert replayed.audit_hash is not None
        assert replayed.audit_hash != original.audit_hash  # new chained entry
        assert client.verify_execution(original) is True
        assert client.verify_execution(replayed) is True
        assert len(client.audit_log.read_all()) == 2

    async def test_replay_detects_tampering(self, tmp_path, client_factory, compliant):
        log_path = tmp_path / "audit.log"
        client = client_factory(compliant(), audit_path=str(log_path))

        original = await client.prompt("Sensitive data")

        lines = log_path.read_text(encoding="utf-8").splitlines()
        first = json.loads(lines[0])
        first["messages"] = [{"role": "user", "content": "replaced"}]
        lines[0] = json.dumps(first)
        log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        with pytest.raises(TamperDetectedError):
            await client.replay(original.execution_id)


class TestPolicy:
    async def test_policy_deny_blocks_and_audits(self, tmp_path, client_factory):
        log_path = str(tmp_path / "audit.log")
        compliance = ComplianceConfig(
            enabled=True,
            signing_key="k",
            policy_rules=[{"caller_id": "blocked-*", "action": "deny", "reason": "abuse"}],
        )
        client = client_factory(compliance, audit_path=log_path)

        with pytest.raises(PolicyViolationError):
            await client.prompt("Hello", caller_id="blocked-bot")

        entries = client.audit_log.read_all()
        assert entries[0]["event"] == "policy_denied"
        assert entries[0]["is_secure"] is False

    async def test_policy_allow_passes(self, tmp_path, client_factory):
        compliance = ComplianceConfig(
            enabled=True,
            signing_key="k",
            policy_rules=[{"caller_id": "trusted-*", "action": "allow"}],
        )
        client = client_factory(compliance, audit_path=str(tmp_path / "a.log"))

        result = await client.prompt("Hi", caller_id="trusted-42")
        assert result.response == "Fake response"


class TestBudget:
    async def test_budget_exceeded_blocks(self, tmp_path, client_factory):
        compliance = ComplianceConfig(
            enabled=True,
            signing_key="k",
            budget=BudgetConfig(max_daily_cost=1.0, max_per_request=1.0),
        )
        client = client_factory(compliance, audit_path=str(tmp_path / "a.log"))
        client._daily_spent = 1.0

        with pytest.raises(BudgetExceededError):
            await client.prompt("Expensive operation")

    async def test_budget_tracks_spend(self, tmp_path, client_factory):
        compliance = ComplianceConfig(
            enabled=True,
            signing_key="k",
            budget=BudgetConfig(max_daily_cost=100.0, max_per_request=10.0),
        )
        client = client_factory(compliance, audit_path=str(tmp_path / "a.log"))

        await client.prompt("Request one")
        await client.prompt("Request two")

        assert client._request_count == 2


class TestHumanInTheLoop:
    async def test_sensitive_request_needs_approval(self, tmp_path, client_factory):
        compliance = ComplianceConfig(
            enabled=True,
            signing_key="k",
            human_review_patterns=["transfer", "approve"],
        )
        client = client_factory(compliance, audit_path=str(tmp_path / "a.log"))

        result = await client.prompt("Please approve transfer of $1000")

        assert result.needs_approval is True
        assert result.approval_id is not None
        assert len(client._pending_approvals) == 1

    async def test_approve_executes_and_records(self, tmp_path, client_factory):
        compliance = ComplianceConfig(
            enabled=True,
            signing_key="k",
            human_review_patterns=["transfer"],
        )
        client = client_factory(compliance, audit_path=str(tmp_path / "a.log"))

        pending = await client.prompt("transfer funds now")

        approved = await client.approve(pending.approval_id, approver="admin")

        assert approved.audit_hash is not None
        assert approved.response == "Fake response"
        assert len(client._pending_approvals) == 0
        events = [e["event"] for e in client.audit_log.read_all()]
        assert "human_approved" in events
        assert "execute" in events

    async def test_reject_records(self, tmp_path, client_factory):
        compliance = ComplianceConfig(
            enabled=True,
            signing_key="k",
            human_review_patterns=["transfer"],
        )
        client = client_factory(compliance, audit_path=str(tmp_path / "a.log"))

        pending = await client.prompt("transfer funds now")
        client.reject(pending.approval_id, reason="too risky")

        assert len(client._pending_approvals) == 0
        events = [e["event"] for e in client.audit_log.read_all()]
        assert "human_rejected" in events


class TestAirGapped:
    async def test_air_gapped_pass_when_offline(self, tmp_path, client_factory, monkeypatch):
        def _offline(address, timeout=1):
            raise OSError("offline")

        monkeypatch.setattr("socket.create_connection", _offline)
        compliance = ComplianceConfig(enabled=True, signing_key="k", mode="air_gapped")
        client = client_factory(compliance, audit_path=str(tmp_path / "a.log"))

        result = await client.prompt("Hello air-gapped")
        assert result.response == "Fake response"

    async def test_air_gapped_blocks_when_online(self, tmp_path, client_factory, monkeypatch):
        def _online(address, timeout=1):
            return object()

        monkeypatch.setattr("socket.create_connection", _online)
        compliance = ComplianceConfig(enabled=True, signing_key="k", mode="air_gapped")
        client = client_factory(compliance, audit_path=str(tmp_path / "a.log"))

        with pytest.raises(RuntimeError, match="Air-gapped"):
            await client.prompt("Should not reach the network")

        entries = client.audit_log.read_all()
        assert entries[0]["event"] == "air_gapped_violation"


class TestSchema:
    def test_execution_result_provable(self):
        result = ExecutionResult(state_id="123", is_secure=True, data={})
        assert result.audit_hash is None
        assert result.audit_chain_id is None
        assert result.tamper_check is None

        stamped = ExecutionResult(
            state_id="123", is_secure=True, data={},
            audit_hash="abc", audit_chain_id="0" * 64, tamper_check=True,
        )
        assert stamped.audit_hash == "abc"
        assert stamped.receipt_hash is None  # legacy field untouched
