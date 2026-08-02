"""Tests for standalone signed execution receipts (brompt.receipt)."""

import hashlib

import pytest

from brompt import (
    ComplianceMode,
    CompliantPromptClient,
    PolicyConfig,
    SensitivityLevel,
)
from brompt.audit import AuditLog
from brompt.config import (
    BudgetConfig,
    CacheConfig,
    FeedbackConfig,
    LoggingConfig,
    LogLevel,
    ProviderConfig,
    ProviderType,
    WidgetConfig,
)
from brompt.providers.base import LLMProvider, ProviderResult
from brompt.receipt import (
    Receipt,
    build_receipt,
    load_receipt,
    save_receipt,
    verify_receipt,
)
from brompt.widget import ProviderFactory


class FakeProvider(LLMProvider):
    def __init__(self, text="Receipt response", model="fake-model", tokens=10):
        self._text = text
        self._tokens = tokens
        super().__init__(model=model)

    def _setup_client(self):
        self._client = None

    async def generate(self, prompt, **kwargs):
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
        tenant_id="tenant-receipt",
        mode=ComplianceMode.STANDARD,
        sensitivity=SensitivityLevel.MEDIUM,
        budget=BudgetConfig(max_daily_cost=100.0, max_per_request=10.0),
        signing_key="receipt-test-key",
    )
    defaults.update(overrides)
    return PolicyConfig(**defaults)


async def signed_result(tmp_path):
    client = CompliantPromptClient(
        config=make_config(),
        policy=standard_policy(),
        audit_log_path=str(tmp_path / "a.log"),
    )
    result = await client.prompt("issue a receipt")
    return client, result


class TestReceiptBuild:
    async def test_build_receipt_from_signed_result(self, tmp_path, provider):
        client, result = await signed_result(tmp_path)
        rcpt = build_receipt(result, client.audit)

        assert rcpt.audit_hash == result.audit_hash
        assert rcpt.execution_id == result.execution_id
        assert rcpt.model == result.model
        assert rcpt.response_hash == hashlib.sha256(result.response.encode()).hexdigest()
        assert rcpt.response == result.response
        assert rcpt.signature_scheme == "hmac"
        assert rcpt.receipt_signature

    async def test_audit_entry_stores_response(self, tmp_path, provider):
        client, result = await signed_result(tmp_path)
        entry = client.audit.find_entry(result.audit_hash)
        assert entry is not None
        assert entry["response"] == result.response

    async def test_save_load_roundtrip(self, tmp_path, provider):
        client, result = await signed_result(tmp_path)
        path = str(tmp_path / "exec.receipt")
        rcpt = build_receipt(result, client.audit)
        save_receipt(rcpt, path)

        loaded = load_receipt(path)
        assert loaded.audit_hash == result.audit_hash
        assert loaded.response == result.response
        assert loaded.receipt_signature == rcpt.receipt_signature

    async def test_write_and_verify_receipt_via_client(self, tmp_path, provider):
        client, result = await signed_result(tmp_path)
        path = str(tmp_path / "client.receipt")
        client.write_receipt(result, path)

        report = client.verify_receipt(path)
        assert report["ok"] is True
        assert report["reason"] == "ok"

    async def test_tampered_response_detected(self, tmp_path, provider):
        client, result = await signed_result(tmp_path)
        path = str(tmp_path / "tampered.receipt")
        client.write_receipt(result, path)

        loaded = load_receipt(path)
        loaded.response = "an attacker rewrote this output"
        report = verify_receipt(loaded, client.audit)
        assert report["ok"] is False
        assert "response hash mismatch" in report["reason"]

    async def test_tampered_signature_detected(self, tmp_path, provider):
        client, result = await signed_result(tmp_path)
        path = str(tmp_path / "forged.receipt")
        client.write_receipt(result, path)

        loaded = load_receipt(path)
        sig = loaded.receipt_signature
        flipped = ("0" if sig[0] != "0" else "1") + sig[1:]
        loaded.receipt_signature = flipped
        report = verify_receipt(loaded, client.audit)
        assert report["ok"] is False
        assert "signature invalid" in report["reason"]

    async def test_verify_against_foreign_log_fails(self, tmp_path, provider):
        client, result = await signed_result(tmp_path)
        path = str(tmp_path / "x.receipt")
        client.write_receipt(result, path)

        other_log = AuditLog(str(tmp_path / "other.log"))
        report = verify_receipt(load_receipt(path), other_log)
        assert report["ok"] is False
        assert "audit entry not found" in report["reason"]


class TestEd25519Receipts:
    def test_from_audit_entry_signs_ed25519(self, tmp_path):
        log = AuditLog(
            str(tmp_path / "signed.log"),
            signing_key="ed25519-seed-material",
        )
        entry = log.record(
            "execute", "exec-1", True,
            messages=[{"role": "user", "content": "hi"}],
            response="Signed output",
        )
        rcpt = Receipt.from_audit_entry(entry, log)

        assert rcpt.signature_scheme == "ed25519"
        assert rcpt.pubkey_id == log.pubkey_id
        assert rcpt.pubkey_der_b64
        assert rcpt.audit_hash == entry["entry_hash"]

    def test_verify_standalone_with_embedded_public_key(self, tmp_path):
        log = AuditLog(
            str(tmp_path / "signed.log"),
            signing_key="ed25519-seed-material",
        )
        entry = log.record(
            "execute", "exec-2", True,
            messages=[{"role": "user", "content": "hi"}],
            response="Standalone verifiable",
        )
        rcpt = Receipt.from_audit_entry(entry, log)

        report = verify_receipt(rcpt)  # no audit_log: uses embedded pubkey
        assert report["ok"] is True

    def test_verify_fails_after_response_mutation_standalone(self, tmp_path):
        log = AuditLog(
            str(tmp_path / "signed.log"),
            signing_key="ed25519-seed-material",
        )
        entry = log.record("execute", "exec-3", True, response="original")
        rcpt = Receipt.from_audit_entry(entry, log)

        rcpt.response = "mutated output"
        report = verify_receipt(rcpt)
        assert report["ok"] is False

    def test_missing_audit_hash_rejected(self):
        rcpt = Receipt(response="hi")
        report = verify_receipt(rcpt)
        assert report["ok"] is False
        assert "audit_hash" in report["reason"]
