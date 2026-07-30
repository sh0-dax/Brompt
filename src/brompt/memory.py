"""Bounded State Management implementation for fixed-cost context tracking.

Supports optional JSON file persistence so state survives process restarts.
"""

import json
import threading
from collections import deque
from pathlib import Path
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

    If *storage_path* is provided, state is persisted to a JSON file and
    reloaded on init.
    """

    def __init__(self, max_turns: int = 3, storage_path: str | None = None):
        if max_turns < 1:
            raise ValueError("max_turns must be >= 1")
        self.max_turns = max_turns
        self._storage_path = Path(storage_path) if storage_path else None
        self._state: dict[str, Any] = {}
        self._history: deque[dict[str, str]] = deque(maxlen=max_turns)
        self._lock = threading.Lock()
        if self._storage_path:
            self._load()

    def update_state(self, key: str, value: Any) -> None:
        """Thread-safe state update."""
        with self._lock:
            self._state[key] = value
            self._save()

    def get_state(self) -> dict[str, Any]:
        """Returns a snapshot copy of the current state."""
        with self._lock:
            return self._state.copy()

    def add_turn(self, role: str, content: str) -> None:
        """Append a conversation turn. Oldest turns are evicted once
        ``max_turns`` is exceeded."""
        with self._lock:
            self._history.append({"role": role, "content": content})
            self._save()

    def get_history(self) -> list[dict[str, str]]:
        """Returns a snapshot copy of the bounded turn history, oldest first."""
        with self._lock:
            return list(self._history)

    def clear(self) -> None:
        """Thread-safe state + history flush."""
        with self._lock:
            self._state.clear()
            self._history.clear()
            self._save()

    def _save(self) -> None:
        if not self._storage_path:
            return
        try:
            self._storage_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "state": self._state,
                "history": list(self._history),
            }
            with open(self._storage_path, "w") as f:
                json.dump(data, f)
        except OSError as e:
            import logging
            logging.getLogger("brompt.memory").warning("Failed to persist memory: %s", e)

    def _load(self) -> None:
        if not self._storage_path or not self._storage_path.exists():
            return
        try:
            with open(self._storage_path) as f:
                data = json.load(f)
            self._state = data.get("state", {})
            for turn in data.get("history", []):
                self._history.append(turn)
        except (OSError, json.JSONDecodeError) as e:
            import logging
            logging.getLogger("brompt.memory").warning("Failed to load persisted memory: %s", e)
