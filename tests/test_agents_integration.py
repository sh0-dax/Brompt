"""Proves agents.py (Warden/Medic) is actually wired into PromptClient.prompt().

Exercises the real async path end-to-end instead of asserting against agent
classes in isolation — the integration guarantee that the security-agents
layer is part of the pipeline, not a standalone module nobody calls.
"""

from brompt.config import (
    CacheConfig,
    FeedbackConfig,
    LoggingConfig,
    LogLevel,
    ProviderConfig,
    ProviderType,
    WidgetConfig,
)
from brompt.providers.base import LLMProvider, ProviderResult
from brompt.widget import PromptClient, ProviderFactory


class FakeProviderWithPII(LLMProvider):
    """Returns a canned response containing PII, simulating a model that
    leaked a credit card number and an email address."""

    def __init__(self, text: str, model: str = "fake-model"):
        self._text = text
        super().__init__(model=model)

    def _setup_client(self):
        self._client = None

    async def generate(self, prompt, **kwargs):
        return ProviderResult(
            text=self._text, model=self.model, tokens_used=10,
            prompt_tokens=5, completion_tokens=5,
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


async def test_prompt_redacts_pii_via_warden_and_medic(monkeypatch, tmp_path):
    leaky_response = (
        "Sure, here's the card on file: 4242 4242 4242 4242. Reach us at billing@example.com."
    )
    monkeypatch.setattr(
        ProviderFactory, "from_config",
        lambda config: FakeProviderWithPII(leaky_response),
    )
    audit_path = str(tmp_path / "audit.log")
    client = PromptClient(config=make_config(), audit_log_path=audit_path)

    result = await client.prompt("What card do you have on file?")

    assert "4242 4242 4242 4242" not in result.response
    assert "billing@example.com" not in result.response
    assert "[REDACTED-CC]" in result.response
    assert "[REDACTED-EMAIL]" in result.response

    # The redaction must be traceable in the audit chain, not silent.
    entries = client._audit.read_all()
    pii_entries = [e for e in entries if e["event"] == "pii_redacted"]
    assert len(pii_entries) == 1
    assert "potential_credit_card_leak" in pii_entries[0]["detail"]
    assert "potential_email_leak" in pii_entries[0]["detail"]
    assert client._audit.verify() is True


async def test_prompt_leaves_clean_response_untouched(monkeypatch):
    monkeypatch.setattr(
        ProviderFactory, "from_config",
        lambda config: FakeProviderWithPII("The weather today is sunny with a light breeze."),
    )
    client = PromptClient(config=make_config(), enable_pii_scan=True)

    result = await client.prompt("How's the weather?")

    assert result.response == "The weather today is sunny with a light breeze."


async def test_pii_scan_can_be_disabled(monkeypatch):
    leaky_response = "Email me at billing@example.com anytime."
    monkeypatch.setattr(
        ProviderFactory, "from_config",
        lambda config: FakeProviderWithPII(leaky_response),
    )
    client = PromptClient(config=make_config(), enable_pii_scan=False)

    result = await client.prompt("What's your contact?")

    # Opt-out respected: secret-scan (SecurityEngine) still runs, but no
    # PII layer, so the email survives untouched.
    assert "billing@example.com" in result.response
