"""Append-only audit log with SHA-256 hash chaining.

Each entry embeds the hash of the previous entry, so any retroactive
edit or deletion of a past entry breaks the chain and is detectable by
replaying ``verify()``.
"""

import hashlib
import json
import threading
import time
from pathlib import Path
from typing import Any

GENESIS_HASH = "0" * 64


class AuditLog:
    def __init__(self, path: str = "brompt_audit.log"):
        self.path = Path(path)
        self._lock = threading.Lock()
        if not self.path.exists():
            self.path.touch()

    def _last_hash(self) -> str:
        last = GENESIS_HASH
        if self.path.stat().st_size == 0:
            return last
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                last = json.loads(line)["entry_hash"]
        return last

    @staticmethod
    def _hash_entry(prev_hash: str, payload: dict[str, Any]) -> str:
        canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256((prev_hash + canonical).encode("utf-8")).hexdigest()

    def record(
        self,
        event: str,
        state_id: str,
        is_secure: bool,
        detail: str | None = None,
        latency_ms: float | None = None,
        tokens_used: int | None = None,
    ) -> dict[str, Any]:
        """Appends one tamper-evident record. No update/delete by design."""
        with self._lock:
            prev_hash = self._last_hash()
            payload = {
                "timestamp": time.time(),
                "event": event,
                "state_id": state_id,
                "is_secure": is_secure,
                "detail": detail,
                "latency_ms": latency_ms,
                "tokens_used": tokens_used,
                "prev_hash": prev_hash,
            }
            entry_hash = self._hash_entry(prev_hash, payload)
            record = {**payload, "entry_hash": entry_hash}
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
            return record

    def verify(self) -> bool:
        """Replays the whole chain and returns False on the first break."""
        prev_hash = GENESIS_HASH
        if self.path.stat().st_size == 0:
            return True
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                claimed_hash = record.pop("entry_hash")
                if record["prev_hash"] != prev_hash:
                    return False
                if self._hash_entry(prev_hash, record) != claimed_hash:
                    return False
                prev_hash = claimed_hash
        return True

    def read_all(self) -> list[dict[str, Any]]:
        if self.path.stat().st_size == 0:
            return []
        with open(self.path, "r", encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]
