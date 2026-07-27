"""Unit tests for Bounded State Memory Engine."""

import threading

import pytest

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

    def test_concurrent_updates(self):
        mm = MemoryManager()

        def writer(n):
            for i in range(100):
                mm.update_state(f"t{n}_{i}", i)

        threads = [threading.Thread(target=writer, args=(t,)) for t in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        state = mm.get_state()
        assert len(state) == 400

    def test_history_bounded_by_max_turns(self):
        mm = MemoryManager(max_turns=3)
        for i in range(10):
            mm.add_turn("user", f"msg{i}")
        history = mm.get_history()
        assert len(history) == 3
        assert [t["content"] for t in history] == ["msg7", "msg8", "msg9"]

    def test_history_independent_of_state(self):
        mm = MemoryManager(max_turns=2)
        mm.update_state("k", "v")
        mm.add_turn("user", "hi")
        assert mm.get_state() == {"k": "v"}
        assert len(mm.get_history()) == 1

    def test_clear_also_clears_history(self):
        mm = MemoryManager(max_turns=5)
        mm.add_turn("user", "hi")
        mm.clear()
        assert mm.get_history() == []

    def test_invalid_max_turns_rejected(self):
        with pytest.raises(ValueError):
            MemoryManager(max_turns=0)

    def test_concurrent_clear_and_update(self):
        mm = MemoryManager()

        def writer():
            for i in range(50):
                mm.update_state(f"k{i}", i)

        def clearer():
            for _ in range(5):
                mm.clear()

        threads = [
            threading.Thread(target=writer),
            threading.Thread(target=clearer),
            threading.Thread(target=writer),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert isinstance(mm.get_state(), dict)
