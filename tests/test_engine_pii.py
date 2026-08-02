"""Integration: agents.py PII healing wired into BromptEngine (API/CLI path).

BromptEngine powers both the REST API (execute_async) and the CLI
(execute). These tests prove the same Warden/Medic PII protection that
PromptClient has is applied on both engine paths.
"""

from brompt.core import BromptEngine
from brompt.providers_core import LLMProvider


class LeakySyncProvider(LLMProvider):
    def generate(self, messages, system=None):
        return "Card on file: 4242 4242 4242 4242. Email billing@example.com."


class LeakyAsyncProvider(LLMProvider):
    def generate(self, messages, system=None):
        return "Card on file: 4242 4242 4242 4242. Email billing@example.com."

    async def agenerate(self, messages, system=None):
        return "SSN 123-45-6789. Phone 555-123-4567."


def _write_manifest(tmp_path):
    config_file = tmp_path / "agent.brompt.yaml"
    config_file.write_text(
        "metadata:\n  name: TestAgent\n  version: 0.1.0\n  environment: test\n"
        "security_policy:\n  isolation_level: ZERO_TRUST\n  sanitize_inputs: true\n  max_payload_size_kb: 64\n"
        "memory_strategy:\n  paging_mode: VIRTUAL_STATE_O1\n  max_history_turns: 3\n",
        encoding="utf-8",
    )
    return config_file


def test_engine_execute_redacts_pii(tmp_path):
    manifest = _write_manifest(tmp_path)
    engine = BromptEngine(
        str(manifest), provider=LeakySyncProvider(),
        audit_log_path=str(tmp_path / "engine.audit.log"),
    )

    result = engine.execute("hello")

    assert "4242 4242 4242 4242" not in result.data["llm_response"]
    assert "billing@example.com" not in result.data["llm_response"]
    assert "[REDACTED-CC]" in result.data["llm_response"]
    assert "[REDACTED-EMAIL]" in result.data["llm_response"]
    events = [e["event"] for e in engine.audit.read_all()]
    assert "pii_redacted" in events


async def test_engine_execute_async_redacts_pii(tmp_path):
    manifest = _write_manifest(tmp_path)
    engine = BromptEngine(
        str(manifest), async_provider=LeakyAsyncProvider(),
        audit_log_path=str(tmp_path / "engine.audit.log"),
    )

    result = await engine.execute_async("hello")

    assert "123-45-6789" not in result.data["llm_response"]
    assert "555-123-4567" not in result.data["llm_response"]
    assert "[REDACTED-SSN]" in result.data["llm_response"]
    assert "[REDACTED-PHONE]" in result.data["llm_response"]
    events = [e["event"] for e in engine.audit.read_all()]
    assert "pii_redacted" in events


async def test_engine_sync_execute_inside_running_loop(tmp_path):
    """engine.execute() must not blow up when invoked from async code."""
    manifest = _write_manifest(tmp_path)
    engine = BromptEngine(
        str(manifest), provider=LeakySyncProvider(),
        audit_log_path=str(tmp_path / "engine.audit.log"),
    )

    result = engine.execute("hello")

    assert "[REDACTED-CC]" in result.data["llm_response"]
    assert "[REDACTED-EMAIL]" in result.data["llm_response"]
