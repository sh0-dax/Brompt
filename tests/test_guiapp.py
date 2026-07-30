"""Smoke tests for the guiapp package.

Tests that do not require a display are always run.
Tests that require Tk are conditionally skipped via ``DISPLAY`` env check
so CI (headless) still passes.
"""

import os
from pathlib import Path

import pytest

from brompt.guiapp import _resolve_config_path

# ---------------------------------------------------------------------------
# Pure-logic tests (no display needed)
# ---------------------------------------------------------------------------

class TestResolveConfigPath:
    def test_returns_path_object(self):
        result = _resolve_config_path()
        assert isinstance(result, Path)

    def test_always_returns_agent_brompt_yaml(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        result = _resolve_config_path()
        assert result.name == "agent.brompt.yaml"
        assert isinstance(result, Path)


# ---------------------------------------------------------------------------
# Smoke tests that require a display / Tk
# ---------------------------------------------------------------------------

def _has_display() -> bool:
    if os.name == "nt":
        return True
    return os.environ.get("DISPLAY") is not None or os.environ.get("WAYLAND_DISPLAY") is not None


pytestmark = pytest.mark.skipif(not _has_display(), reason="No display available")


@pytest.fixture(scope="module")
def widget():
    """Create a BromptWidget once per module (requires display)."""
    from brompt.guiapp import BromptWidget
    w = BromptWidget(live_mode=False)
    yield w
    w.root.destroy()


class TestWidgetCreation:
    def test_widget_created(self, widget):
        assert widget is not None
        assert widget.root is not None
        assert widget.root.title() == "Brompt Engine"


class TestTabs:
    def test_tab_buttons_created(self, widget):
        tab_buttons = widget.tab_buttons
        assert len(tab_buttons) == 5


class TestProviderList:
    def test_provider_factories_populated(self, widget):
        from brompt.guiapp import PROVIDER_FACTORIES
        assert "OpenAI" in PROVIDER_FACTORIES
        assert "Anthropic" in PROVIDER_FACTORIES
        assert "Ollama" in PROVIDER_FACTORIES


class TestConfigPath:
    def test_resolve_config_path_function(self):
        p = _resolve_config_path()
        assert isinstance(p, Path)
        assert p.name == "agent.brompt.yaml"
