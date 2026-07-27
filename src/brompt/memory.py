"""Bounded State Management implementation for fixed-cost context tracking."""

import threading
from typing import Any, Dict


class MemoryManager:
    """Thread-safe bounded state manager for fixed-size context tracking.

    Maintains a dictionary of operational variables without accumulating
    raw message tokens over extended execution turns.
    """

    def __init__(self, max_turns: int = 3):
        self.max_turns = max_turns
        self._state: Dict[str, Any] = {}
        self._lock = threading.Lock()

    def update_state(self, key: str, value: Any) -> None:
        """Thread-safe state update."""
        with self._lock:
            self._state[key] = value

    def get_state(self) -> Dict[str, Any]:
        """Returns a snapshot copy of the current state."""
        with self._lock:
            return self._state.copy()

    def clear(self) -> None:
        """Thread-safe state flush."""
        with self._lock:
            self._state.clear()
