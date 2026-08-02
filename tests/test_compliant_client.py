"""Tests for the policy-driven compliance surface: PolicyConfig,
CompliantPromptClient, and SignedExecutionResult."""

import json

import pytest

from brompt import (
    ComplianceMode,
    CompliantPromptClient,
    HumanApprovalRequired,
    PolicyConfig,
    SensitivityLevel,
    SignedExecutionResult,
)
from brompt.config import (
    BudgetConfig,
    CacheConfig,
    ComplianceConfig,
    FeedbackConfig,
    LoggingConfig,
    LogLevel,
    ProviderConfig,
    ProviderType,
    WidgetConfig,
)
from brompt.providers.base import LLMProvider, ProviderResult
from brompt.widget import ProviderFactory


class FakeProvider(LLMProvider):
    def __init__(self, text="Compliant response", model="fake-model", tokens=10, error=None):
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
def provider(monkeypatch):
    monkeypatch.setattr(ProviderFactory, "from_config", lambda config: FakeProvider())
    return FakeProvider()


def standard_policy(**overrides):
    defaults = dict(
        tenant_id="tenant-a",
        mode=ComplianceMode.STANDARD,
        sensitivity=SensitivityLevel.MEDIUM,
        budget=BudgetConfig(max_daily_cost=100.0, max_per_request=10.0),
        signing_key="policy-test-key",
    )
    defaults.update(overrides)
    return PolicyConfig(**defaults)


class TestSignedExecutionResult:
    async def test_prompt_returns_signed_result(self, tmp_path, provider):
        client = CompliantPromptClient(
            config=make_config(),
            policy=standard_policy(),
            audit_log_path=str(tmp_path / "a.log"),
        )

        result = await client.prompt("Hello")

        assert isinstance(result, SignedExecutionResult)
        assert result.audit_hash is not None
        assert result.tamper_check is True
        assert result.verified is True
        assert result.receipt == result.audit_hash
        assert client.verify_execution(result) is True

    async def test_replay_returns_signed_result(self, tmp_path, provider):
        client = CompliantPromptClient(
            config=make_config(),
            policy=standard_policy(),
            audit_log_path=str(tmp_path / "a.log"),
        )

        original = await client.prompt("Replay me")
        replayed = await client.replay(original.execution_id)

        assert isinstance(replayed, SignedExecutionResult)
        assert replayed.audit_hash != original.audit_hash
        assert replayed.verified is True

    async def test_pending_approval_returns_signed_result(self, tmp_path, provider):
        policy = standard_policy(human_review_patterns=["transfer"])
        client = CompliantPromptClient(
            config=make_config(), policy=policy, audit_log_path=str(tmp_path / "a.log"),
        )

        pending = await client.prompt("transfer funds")

        assert isinstance(pending, SignedExecutionResult)
        assert pending.needs_approval is True
        assert pending.verified is False  # not yet signed


class TestPolicyConfig:
    def test_yaml_roundtrip(self, tmp_path):
        policy = standard_policy(
            data_residency="eu",
            human_review_patterns=["approve", "transfer"],
        )
        path = tmp_path / "policy.yaml"
        policy.to_yaml(str(path))

        loaded = PolicyConfig.from_yaml(str(path))
        assert loaded.tenant_id == "tenant-a"
        assert loaded.mode == ComplianceMode.STANDARD
        assert loaded.sensitivity == SensitivityLevel.MEDIUM
        assert loaded.data_residency == "eu"
        assert loaded.human_review_patterns == ["approve", "transfer"]

    def test_json_roundtrip(self, tmp_path):
        policy = standard_policy(mode=ComplianceMode.AIR_GAPPED, tenant_id="air-1")
        path = tmp_path / "policy.json"
        payload = policy.to_dict()
        path.write_text(json.dumps(payload), encoding="utf-8")

        loaded = PolicyConfig.from_json(str(path))
        assert loaded.tenant_id == "air-1"
        assert loaded.mode == ComplianceMode.AIR_GAPPED
        assert loaded.get_signing_key() == "policy-test-key"

    def test_default_signing_key_is_tenant_derived(self):
        a = PolicyConfig(tenant_id="t1").get_signing_key()
        b = PolicyConfig(tenant_id="t2").get_signing_key()
        assert a != b
        assert PolicyConfig(tenant_id="t1").get_signing_key() == a

    def test_needs_human_review(self):
        policy = standard_policy(human_review_patterns=["transfer"])
        assert policy.needs_human_review("Please transfer the funds") is True
        assert policy.needs_human_review("What is the weather?") is False

        strict = standard_policy(sensitivity=SensitivityLevel.HIGH)
        assert strict.needs_human_review("anything") is True

    def test_to_compliance_config_bridge(self):
        policy = standard_policy(
            mode=ComplianceMode.AIR_GAPPED,
            data_residency="mena",
            human_review_action="raise",
        )
        cc = policy.to_compliance_config()
        assert isinstance(cc, ComplianceConfig)
        assert cc.enabled is True
        assert cc.mode == "air_gapped"
        assert cc.data_residency == "mena"
        assert cc.human_review_action == "raise"
        assert cc.signing_key == "policy-test-key"


class TestCompliantPromptClient:
    async def test_policy_drives_behaviour(self, tmp_path, provider):
        policy = standard_policy(
            data_residency="us",
            human_review_patterns=["approve"],
            budget=BudgetConfig(max_daily_cost=50.0),
        )
        client = CompliantPromptClient(
            config=make_config(), policy=policy, audit_log_path=str(tmp_path / "a.log"),
        )

        result = await client.prompt("Approve the request")
        assert result.needs_approval is True
        assert result.data_residency == "us"

        approved = await client.approve(result.approval_id, approver="admin")
        assert approved.response == "Compliant response"
        assert approved.data_residency == "us"

    async def test_raise_mode(self, tmp_path, provider):
        policy = standard_policy(
            human_review_patterns=["transfer"],
            human_review_action="raise",
        )
        client = CompliantPromptClient(
            config=make_config(), policy=policy, audit_log_path=str(tmp_path / "a.log"),
        )

        with pytest.raises(HumanApprovalRequired):
            await client.prompt("transfer funds")

    async def test_air_gapped_policy_mode(self, tmp_path, provider, monkeypatch):
        def _offline(address, timeout=1):
            raise OSError("offline")

        monkeypatch.setattr("socket.create_connection", _offline)
        policy = standard_policy(mode=ComplianceMode.AIR_GAPPED, tenant_id="airgap")
        client = CompliantPromptClient(
            config=make_config(), policy=policy, audit_log_path=str(tmp_path / "a.log"),
        )

        result = await client.prompt("Hello air-gapped")
        assert result.response == "Compliant response"
        assert client.mode == "air_gapped"

    async def test_multi_tenant_isolation(self, tmp_path, provider):
        client_a = CompliantPromptClient(
            config=make_config(), policy=standard_policy(tenant_id="t1", signing_key="k1"),
            audit_log_path=str(tmp_path / "a.log"),
        )
        client_b = CompliantPromptClient(
            config=make_config(), policy=standard_policy(tenant_id="t2", signing_key="k2"),
            audit_log_path=str(tmp_path / "b.log"),
        )

        res_a = await client_a.prompt("A")
        res_b = await client_b.prompt("B")

        assert client_a.policy.tenant_id == "t1"
        assert client_b.policy.tenant_id == "t2"
        assert client_a._audit_key != client_b._audit_key
        assert client_a.verify_execution(res_a) is True
        assert client_a.verify_execution(res_b) is False  # foreign signature

    async def test_report_and_export(self, tmp_path, provider):
        client = CompliantPromptClient(
            config=make_config(), policy=standard_policy(data_residency="eu"),
            audit_log_path=str(tmp_path / "a.log"),
        )
        await client.prompt("One")
        await client.prompt("Two")

        report = client.get_compliance_report()
        assert report["compliance_enabled"] is True
        assert report["data_residency"] == "eu"
        assert report["chain_integrity"] is True
        assert report["signed_entries"] is True

        trail = client.export_audit_trail()
        assert len(trail) == 2
        assert all(e["chain_verified"] for e in trail)

    async def test_backward_compatible_with_prompt_client(self, tmp_path, provider):
        policy = standard_policy()
        client = CompliantPromptClient(
            config=make_config(), policy=policy, audit_log_path=str(tmp_path / "a.log"),
        )

        result = await client.prompt("Hello", session_id="s1")
        assert isinstance(result, SignedExecutionResult)
        assert client.audit_log is client.audit  # audit alias works
        assert client.audit is not None


class TestPolicyPiiScan:
    def test_policy_default_enables_agents(self, provider):
        client = CompliantPromptClient(config=make_config(), policy=standard_policy())
        assert client._warden is not None
        assert client._medic is not None

    def test_policy_enable_pii_scan_disables_agents(self, provider):
        client = CompliantPromptClient(
            config=make_config(), policy=standard_policy(enable_pii_scan=False),
        )
        assert client._warden is None
        assert client._medic is None

    def test_policy_wins_over_constructor_argument(self, provider):
        client = CompliantPromptClient(
            config=make_config(),
            policy=standard_policy(enable_pii_scan=False),
            enable_pii_scan=True,
        )
        assert client._warden is None

    def test_policy_pii_scan_yaml_roundtrip(self, tmp_path, provider):
        policy = standard_policy(enable_pii_scan=False)
        path = tmp_path / "policy.yaml"
        policy.to_yaml(str(path))
        loaded = PolicyConfig.from_yaml(str(path))
        assert loaded.enable_pii_scan is False
