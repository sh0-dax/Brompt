"""Append-only audit log with SHA-256 hash chaining + optional HMAC signing.

Each entry embeds the hash of the previous entry, so any retroactive
edit or deletion of a past entry breaks the chain and is detectable by
replaying ``verify()``.

When a *secret_key* is provided, every entry is additionally HMAC-SHA256
signed so that a tamperer who rewrites chain hashes still cannot forge
a valid signature.  The HMAC is computed over ``entry_hash`` only (the
chain is already protected by the hash), so verification remains O(N)
and the signature is independent of payload size.
"""

import hashlib
import hmac
import json
import threading
import time
from pathlib import Path
from typing import Any

GENESIS_HASH = "0" * 64


class AuditLog:
    def __init__(self, path: str = "brompt_audit.log", secret_key: str | None = None):
        self.path = Path(path)
        self._lock = threading.Lock()
        if not self.path.exists():
            self.path.touch()
        self._hmac_key: bytes | None = None
        if secret_key is not None:
            self._hmac_key = hashlib.sha256(secret_key.encode("utf-8")).digest()
        self._tail_cache: tuple[int, str] | None = None

    @property
    def is_signed(self) -> bool:
        """``True`` when this log instance was configured with a signing key."""
        return self._hmac_key is not None

    def _last_hash(self) -> str:
        # Fast path: when the file size matches the last write we observed,
        # reuse the cached tail hash instead of re-reading the whole log
        # (record() would otherwise be O(N) per write).
        cached = self._tail_cache
        size = self.path.stat().st_size
        if cached is not None and cached[0] == size:
            return cached[1]
        last = GENESIS_HASH
        if size == 0:
            self._tail_cache = (0, last)
            return last
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                last = json.loads(line)["entry_hash"]
        self._tail_cache = (size, last)
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
        messages: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        """Appends one tamper-evident record. No update/delete by design.

        *messages* - the exact message list sent to the LLM, stored so that
        :meth:`replay` can re-run the same prompt on a different model.
        """
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
                "messages": messages,
            }
            entry_hash = self._hash_entry(prev_hash, payload)
            record: dict[str, Any] = {**payload, "entry_hash": entry_hash}
            if self._hmac_key is not None:
                sig = hmac.new(self._hmac_key, entry_hash.encode("utf-8"), hashlib.sha256).hexdigest()
                record["hmac"] = sig
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
            self._tail_cache = (self.path.stat().st_size, entry_hash)
            return record

    def verify(self) -> bool:
        """Replays the whole chain and returns ``False`` on the first break.

        When the log was created with a *secret_key*, every signed entry
        must carry a valid ``hmac`` field.  An unsigned entry found while
        the log is configured for signing is treated as a downgrade attack.
        """
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
                stored_hmac = record.pop("hmac", None)
                if record["prev_hash"] != prev_hash:
                    return False
                if self._hash_entry(prev_hash, record) != claimed_hash:
                    return False
                # HMAC check
                if self._hmac_key is not None:
                    if stored_hmac is None:
                        return False  # downgrade attack
                    expected = hmac.new(self._hmac_key, claimed_hash.encode("utf-8"), hashlib.sha256).hexdigest()
                    if not hmac.compare_digest(expected, stored_hmac):
                        return False
                prev_hash = claimed_hash
        return True

    def read_all(self) -> list[dict[str, Any]]:
        if self.path.stat().st_size == 0:
            return []
        with open(self.path, "r", encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    def find_entry(self, entry_hash: str) -> dict[str, Any] | None:
        """Return the first audit entry whose ``entry_hash`` matches *entry_hash*."""
        for entry in self.read_all():
            if entry.get("entry_hash") == entry_hash:
                return entry
        return None

    def find_by_state(self, state_id: str) -> dict[str, Any] | None:
        """Return the first audit entry whose ``state_id`` matches *state_id*.

        Useful for looking up an execution by the identifier handed back to
        the caller (e.g. ``PromptResult.execution_id``).
        """
        for entry in self.read_all():
            if entry.get("state_id") == state_id:
                return entry
        return None

    def verify_entry(self, entry_hash: str) -> bool:
        """Verify a single entry: it must exist, chain to its predecessor,
        and (when the log is signed) carry a valid HMAC.

        Returns ``False`` if the entry is missing or tampered with.
        """
        entry = self.find_entry(entry_hash)
        if entry is None:
            return False
        payload = {k: v for k, v in entry.items() if k not in ("entry_hash", "hmac")}
        prev_hash = payload.get("prev_hash", GENESIS_HASH)
        if self._hash_entry(prev_hash, payload) != entry_hash:
            return False
        if self._hmac_key is not None:
            stored_hmac = entry.get("hmac")
            if stored_hmac is None:
                return False  # downgrade attack
            expected = hmac.new(self._hmac_key, entry_hash.encode("utf-8"), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(expected, stored_hmac):
                return False
        return True

    def replay(
        self,
        entry_hash: str,
        provider=None,
        system: str | None = None,
        fn=None,
    ) -> dict[str, Any]:
        """Re-run a previous execution and return a comparison.

        Parameters
        ----------
        entry_hash :
            The ``entry_hash`` of the audit entry to replay.
        provider :
            A :class:`LLMProvider` instance to call with the original messages.
            Ignored when *fn* is provided.
        system :
            Optional system prompt forwarded to the provider.
        fn :
            Alternative callable ``fn(messages, system=None) -> str``.  Use
            this when the provider does not match the ``(messages, system)``
            calling convention (e.g. the async providers used by
            ``PromptClient``).

        Returns
        -------
        A dict with keys ``original`` (the audit entry) and ``replayed``
        (the new :class:`ProviderResult`), or an ``error`` key if the
        entry cannot be found or contains no messages.
        """
        entry = self.find_entry(entry_hash)
        if entry is None:
            return {"error": f"Entry not found: {entry_hash}"}
        msgs = entry.get("messages")
        if not msgs:
            return {"error": "Entry has no stored messages; cannot replay"}
        from .providers.base import ProviderResult
        if fn is not None:
            text = fn(msgs, system=system)
        else:
            text = provider.generate(msgs, system=system)
        return {"original": entry, "replayed": ProviderResult(text=text)}
