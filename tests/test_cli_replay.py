"""Tests for the `brompt replay` and `brompt receipt` CLI commands."""

import yaml
from typer.testing import CliRunner

from brompt.audit import AuditLog
from brompt.cli.main import app

runner = CliRunner()


def make_manifest(tmp_path):
    cfg = tmp_path / "agent.brompt.yaml"
    data = {
        "metadata": {"name": "TestAgent", "version": "2.0.0", "environment": "test"},
        "security_policy": {"isolation_level": "ZERO_TRUST", "sanitize_inputs": True, "max_payload_size_kb": 64},
        "memory_strategy": {"paging_mode": "VIRTUAL_STATE_O1", "max_history_turns": 3},
        "rate_limit": {"max_requests": 30, "window_seconds": 60},
    }
    with open(cfg, "w") as f:
        yaml.dump(data, f)
    return str(cfg)


class FakeSyncProvider:
    model = "fake-model"

    def __init__(self, text="Replayed deterministic output"):
        self._text = text

    def generate(self, messages, system=None):
        return self._text


def audit_log_path(tmp_path):
    return str(tmp_path / "agent.brompt.audit.log")


class TestReplayCommand:
    def test_help_lists_replay(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "replay" in result.stdout
        assert "receipt" in result.stdout

    def test_replay_identical_output(self, tmp_path, monkeypatch):
        cfg = make_manifest(tmp_path)
        monkeypatch.setattr(
            "brompt.cli.main.build_provider_from_env",
            lambda model=None: FakeSyncProvider(text="Stored response"),
        )
        log = AuditLog(audit_log_path(tmp_path))
        entry = log.record(
            "execute", "exec-1", True,
            messages=[{"role": "user", "content": "Hello"}],
            response="Stored response",
        )
        entry_hash = entry["entry_hash"]

        result = runner.invoke(app, ["replay", "-c", cfg, entry_hash, "--model", "fake-model"])
        assert result.exit_code == 0
        assert "identical" in result.stdout.lower()

    def test_replay_diff_exits_nonzero(self, tmp_path, monkeypatch):
        cfg = make_manifest(tmp_path)
        monkeypatch.setattr(
            "brompt.cli.main.build_provider_from_env",
            lambda model=None: FakeSyncProvider(text="A different output"),
        )
        log = AuditLog(audit_log_path(tmp_path))
        entry = log.record(
            "execute", "exec-2", True,
            messages=[{"role": "user", "content": "Hello"}],
            response="Stored response",
        )
        entry_hash = entry["entry_hash"]

        result = runner.invoke(app, ["replay", "-c", cfg, entry_hash, "--model", "fake-model"])
        assert result.exit_code == 1
        assert "-Stored response" in result.stdout
        assert "+A different output" in result.stdout

    def test_replay_by_execution_id(self, tmp_path, monkeypatch):
        cfg = make_manifest(tmp_path)
        monkeypatch.setattr(
            "brompt.cli.main.build_provider_from_env",
            lambda model=None: FakeSyncProvider(text="Stored response"),
        )
        log = AuditLog(audit_log_path(tmp_path))
        log.record(
            "execute", "exec-3", True,
            messages=[{"role": "user", "content": "Hello"}],
            response="Stored response",
        )
        result = runner.invoke(app, ["replay", "-c", cfg, "exec-3", "--model", "fake-model"])
        assert result.exit_code == 0
        assert "identical" in result.stdout.lower()

    def test_replay_unknown_id_errors(self, tmp_path):
        cfg = make_manifest(tmp_path)
        AuditLog(audit_log_path(tmp_path))
        result = runner.invoke(app, ["replay", "-c", cfg, "does-not-exist"])
        assert result.exit_code == 2
        assert "not found" in result.stdout.lower()


class TestReceiptCommand:
    def test_export_and_verify_receipt(self, tmp_path):
        cfg = make_manifest(tmp_path)
        log = AuditLog(audit_log_path(tmp_path))
        entry = log.record(
            "execute", "exec-4", True,
            messages=[{"role": "user", "content": "Hello"}],
            response="Stored response",
        )
        entry_hash = entry["entry_hash"]
        out = str(tmp_path / "exec.receipt")

        export = runner.invoke(app, ["receipt", "-c", cfg, entry_hash, "-o", out])
        assert export.exit_code == 0
        assert "Wrote" in export.stdout

        verify = runner.invoke(app, ["receipt", "-c", cfg, "--verify", "-o", out])
        assert verify.exit_code == 0
        assert "VALID" in verify.stdout

    def test_verify_detects_tampered_receipt(self, tmp_path):
        import json

        cfg = make_manifest(tmp_path)
        log = AuditLog(audit_log_path(tmp_path))
        entry = log.record(
            "execute", "exec-5", True,
            messages=[{"role": "user", "content": "Hello"}],
            response="Stored response",
        )
        entry_hash = entry["entry_hash"]
        out = str(tmp_path / "tampered.receipt")
        runner.invoke(app, ["receipt", "-c", cfg, entry_hash, "-o", out])

        data = json.loads(open(out, encoding="utf-8").read())
        data["response"] = "tampered output"
        with open(out, "w", encoding="utf-8") as f:
            json.dump(data, f)

        verify = runner.invoke(app, ["receipt", "-c", cfg, "--verify", "-o", out])
        assert verify.exit_code == 1
        assert "INVALID" in verify.stdout

    def test_receipt_unknown_id_errors(self, tmp_path):
        cfg = make_manifest(tmp_path)
        AuditLog(audit_log_path(tmp_path))
        result = runner.invoke(app, ["receipt", "-c", cfg, "does-not-exist"])
        assert result.exit_code == 2
