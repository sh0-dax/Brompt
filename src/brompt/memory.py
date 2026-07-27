"""Bounded State Management implementation for fixed-cost context tracking."""

import threading
from collections import deque
from typing import Any


class MemoryManager:
    """Thread-safe bounded state manager for fixed-size context tracking.

    Two things are tracked, deliberately kept separate:

    - ``_state``: arbitrary session-scoped key/value variables (user_id,
      role, feature flags, etc). This is *not* conversation history and is
      intentionally unbounded in key count -- bounding it would silently
      drop caller-owned data.
    - ``_history``: the actual conversation turns (role/content pairs) that
      get sent to the upstream LLM. This *is* bounded to ``max_turns`` via a
      ``deque(maxlen=...)``, so raw message tokens never accumulate past the
      configured window.
    """

    def __init__(self, max_turns: int = 3):
        if max_turns < 1:
            raise ValueError("max_turns must be >= 1")
        self.max_turns = max_turns
        self._state: dict[str, Any] = {}
        self._history: deque[dict[str, str]] = deque(maxlen=max_turns)
        self._lock = threading.Lock()

    def update_state(self, key: str, value: Any) -> None:
        """Thread-safe state update."""
        with self._lock:
            self._state[key] = value

    def get_state(self) -> dict[str, Any]:
        """Returns a snapshot copy of the current state."""
        with self._lock:
            return self._state.copy()

    def add_turn(self, role: str, content: str) -> None:
        """Append a conversation turn. Oldest turns are evicted once
        ``max_turns`` is exceeded."""
        with self._lock:
            self._history.append({"role": role, "content": content})

    def get_history(self) -> list[dict[str, str]]:
        """Returns a snapshot copy of the bounded turn history, oldest first."""
        with self._lock:
            return list(self._history)

    def clear(self) -> None:
        """Thread-safe state + history flush."""
        with self._lock:
            self._state.clear()
            self._history.clear()
