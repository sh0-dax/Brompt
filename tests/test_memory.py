"""Unit tests for Virtual State Memory Engine."""

from brompt.memory import MemoryManager


class TestMemoryManager:
    def test_update_and_get(self):
        mm = MemoryManager()
        mm.update_state("key1", "value1")
        assert mm.get_state() == {"key1": "value1"}

    def test_multiple_updates(self):
        mm = MemoryManager()
        mm.update_state("a", 1)
        mm.update_state("b", 2)
        state = mm.get_state()
        assert state == {"a": 1, "b": 2}

    def test_overwrite_key(self):
        mm = MemoryManager()
        mm.update_state("x", "old")
        mm.update_state("x", "new")
        assert mm.get_state()["x"] == "new"

    def test_clear(self):
        mm = MemoryManager()
        mm.update_state("k", "v")
        mm.clear()
        assert mm.get_state() == {}

    def test_get_state_returns_copy(self):
        mm = MemoryManager()
        mm.update_state("k", "v")
        state = mm.get_state()
        state["injected"] = "bad"
        assert mm.get_state() == {"k": "v"}

    def test_max_turns_stored(self):
        mm = MemoryManager(max_turns=5)
        assert mm.max_turns == 5

    def test_empty_state(self):
        mm = MemoryManager()
        assert mm.get_state() == {}
