"""Tests for the Typer-based CLI."""
import json
import yaml
import pytest
from pathlib import Path
from typer.testing import CliRunner
from brompt.cli.main import app

runner = CliRunner()


@pytest.fixture
def config_file(tmp_path):
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


class TestCLI:
    def test_version(self):
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "Brompt Engine" in result.stdout

    def test_help(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "chat" in result.stdout
        assert "run" in result.stdout
        assert "history" in result.stdout
        assert "audit" in result.stdout
        assert "status" in result.stdout
        assert "templates" in result.stdout
        assert "config" in result.stdout
        assert "clear" in result.stdout

    def test_run_dry(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        cfg = tmp_path / "agent.brompt.yaml"
        data = {
            "metadata": {"name": "TestAgent", "version": "2.0.0", "environment": "test"},
            "security_policy": {"isolation_level": "ZERO_TRUST", "sanitize_inputs": True, "max_payload_size_kb": 64},
            "memory_strategy": {"paging_mode": "VIRTUAL_STATE_O1", "max_history_turns": 3},
            "rate_limit": {"max_requests": 30, "window_seconds": 60},
        }
        with open(cfg, "w") as f:
            yaml.dump(data, f)
        result = runner.invoke(app, ["run", "-c", str(cfg), "Hello world"])
        assert result.exit_code == 0
        assert "dry-run" in result.stdout.lower()

    def test_config_show(self, config_file):
        result = runner.invoke(app, ["config", config_file, "--show"])
        assert result.exit_code == 0
        assert "TestAgent" in result.stdout
        assert "2.0.0" in result.stdout

    def test_config_not_found(self):
        result = runner.invoke(app, ["config", "nonexistent.yaml"])
        assert result.exit_code == 1
        assert "not found" in result.stdout

    def test_status(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        cfg = tmp_path / "agent.brompt.yaml"
        data = {
            "metadata": {"name": "TestAgent", "version": "2.0.0", "environment": "test"},
            "security_policy": {"isolation_level": "ZERO_TRUST", "sanitize_inputs": True, "max_payload_size_kb": 64},
            "memory_strategy": {"paging_mode": "VIRTUAL_STATE_O1", "max_history_turns": 3},
            "rate_limit": {"max_requests": 30, "window_seconds": 60},
        }
        with open(cfg, "w") as f:
            yaml.dump(data, f)
        result = runner.invoke(app, ["status", "-c", str(cfg)])
        assert result.exit_code == 0
        assert "Provider" in result.stdout or "Engine" in result.stdout

    def test_templates(self):
        result = runner.invoke(app, ["templates"])
        assert result.exit_code == 0
        assert len(result.stdout) > 0

    def test_history(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        cfg = tmp_path / "agent.brompt.yaml"
        data = {
            "metadata": {"name": "TestAgent", "version": "2.0.0", "environment": "test"},
            "security_policy": {"isolation_level": "ZERO_TRUST", "sanitize_inputs": True, "max_payload_size_kb": 64},
            "memory_strategy": {"paging_mode": "VIRTUAL_STATE_O1", "max_history_turns": 3},
            "rate_limit": {"max_requests": 30, "window_seconds": 60},
        }
        with open(cfg, "w") as f:
            yaml.dump(data, f)
        result = runner.invoke(app, ["history", "-c", str(cfg)])
        assert result.exit_code == 0

    def test_audit(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        cfg = tmp_path / "agent.brompt.yaml"
        data = {
            "metadata": {"name": "TestAgent", "version": "2.0.0", "environment": "test"},
            "security_policy": {"isolation_level": "ZERO_TRUST", "sanitize_inputs": True, "max_payload_size_kb": 64},
            "memory_strategy": {"paging_mode": "VIRTUAL_STATE_O1", "max_history_turns": 3},
            "rate_limit": {"max_requests": 30, "window_seconds": 60},
        }
        with open(cfg, "w") as f:
            yaml.dump(data, f)
        result = runner.invoke(app, ["audit", "-c", str(cfg)])
        assert result.exit_code == 0
