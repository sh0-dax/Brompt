"""Append-only audit log with SHA-256 hash chaining + optional signing.

Each entry embeds the hash of the previous entry, so any retroactive
edit or deletion of a past entry breaks the chain and is detectable by
replaying ``verify()``.

Signing
-------
When a *secret_key* is provided, every entry is additionally HMAC-SHA256
signed so that a tamperer who rewrites chain hashes still cannot forge
a valid signature.  The HMAC is computed over ``entry_hash`` only (the
chain is already protected by the hash), so verification remains O(N)
and the signature is independent of payload size.

For third-party (asymmetric) verifiability, pass a *signing_key*; each
entry then carries an Ed25519 ``signature`` of ``entry_hash`` plus a
``pubkey_id``.  This provides non-repudiation: anyone holding the public
key can verify the log without sharing a secret.

Concurrency
-----------
Writes are protected against concurrent processes: when *portalocker*
is installed an exclusive cross-process lock is taken around each
``record()`` (and a shared lock around ``verify()``).  Without
portalocker the fallback is a single ``os.write`` of the full JSON line
in ``O_APPEND`` mode, which is atomic on POSIX for the common small
records.  A ``threading.Lock`` is always held as a final layer.

Key management
--------------
Pass secrets via environment variables or a secret manager (Vault, OS
keyring) rather than plain-text config files.  ``secret_key`` may be
read from ``BROMPT_AUDIT_SECRET`` and a signing seed from
``BROMPT_AUDIT_SIGNING_KEY`` (see :class:`BromptEngine`).
"""

import contextlib
import hashlib
import hmac
import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .providers.base import LLMProvider

try:  # pragma: no cover - exercised when portalocker is installed
    import portalocker

    _PORTALOCKER_AVAILABLE = True
except ImportError:
    _PORTALOCKER_AVAILABLE = False

try:  # pragma: no cover - exercised when cryptography is installed
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    _CRYPTO_AVAILABLE = True
except ImportError:
    _CRYPTO_AVAILABLE = False

logger = logging.getLogger("brompt.audit")

GENESIS_HASH = "0" * 64

_SIGNING_FIELDS = ("entry_hash", "hmac", "signature", "pubkey_id")


class AuditLog:
    def __init__(
        self,
        path: str = "brompt_audit.log",
        secret_key: str | None = None,
        signing_key: str | bytes | None = None,
        pubkey_id: str | None = None,
    ):
        self.path = Path(path)
        self._lock = threading.Lock()
        if not self.path.exists():
            try:
                self.path.touch()
            except OSError:
                # Racing another process that is creating the file — the
                # first write below will create it if it is still missing.
                pass
        self._hmac_key: bytes | None = None
        if secret_key is not None:
            self._hmac_key = hashlib.sha256(secret_key.encode("utf-8")).digest()
        self._signing_key: Ed25519PrivateKey | None = None
        self._pubkey_id: str | None = None
        if signing_key is not None:
            if not _CRYPTO_AVAILABLE:
                raise ImportError(
                    "Ed25519 signing requires the 'cryptography' package. "
                    'Install it with `pip install -e ".[audit]"` or `pip install cryptography`.'
                )
            raw = signing_key.encode("utf-8") if isinstance(signing_key, str) else signing_key
            seed = hashlib.sha256(raw).digest()
            self._signing_key = Ed25519PrivateKey.from_private_bytes(seed)
            self._pubkey_id = pubkey_id or self._derive_pubkey_id()
        self._tail_cache: tuple[int, str] | None = None
        self._warn_weak_permissions()

    # -- configuration ------------------------------------------------------

    @property
    def is_signed(self) -> bool:
        """``True`` when this log instance was configured with an HMAC key."""
        return self._hmac_key is not None

    @property
    def is_ed25519(self) -> bool:
        """``True`` when this log instance signs entries with Ed25519."""
        return self._signing_key is not None

    @property
    def pubkey_id(self) -> str | None:
        """Identifier for the active Ed25519 public key (``None`` if unsigned)."""
        return self._pubkey_id

    def _derive_pubkey_id(self) -> str:
        if self._signing_key is None:
            return ""
        public_bytes = self._signing_key.public_key().public_bytes(
            encoding=Encoding.Raw,
            format=PublicFormat.Raw,
        )
        return hashlib.sha256(public_bytes).hexdigest()[:16]

    def _warn_weak_permissions(self) -> None:
        """Warn when the audit file is readable/writable by group or other (POSIX)."""
        if os.name != "posix":
            return
        try:
            mode = self.path.stat().st_mode & 0o777
        except OSError:
            return
        if mode & 0o077:
            logger.warning(
                "Audit log %s has permissions %o (world/group accessible); "
                "consider `chmod 600` to protect tamper evidence and secrets.",
                self.path, mode,
            )

    # -- chain helpers ------------------------------------------------------

    def _read_lines(self, handle) -> list[str]:
        """Return non-empty stripped lines via the locked handle or a fresh read handle."""
        if handle is not None:
            handle.seek(0)
            lines = []
            for line in handle:
                s = line.strip()
                if s:
                    lines.append(s)
            handle.seek(0, os.SEEK_END)
            return lines
        with open(self.path, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]

    def _last_hash(self, handle=None) -> str:
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
        for line in self._read_lines(handle):
            try:
                last = json.loads(line)["entry_hash"]
            except (json.JSONDecodeError, KeyError):
                # Trailing partial line from a concurrent writer — skip.
                continue
        self._tail_cache = (size, last)
        return last

    @staticmethod
    def _hash_entry(prev_hash: str, payload: dict[str, Any]) -> str:
        canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256((prev_hash + canonical).encode("utf-8")).hexdigest()

    def _append(self, record: dict[str, Any], handle) -> None:
        line = json.dumps(record, ensure_ascii=False) + "\n"
        if handle is not None:
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())
        else:
            # Atomic-append fallback: a single write() in O_APPEND mode.
            fd = os.open(str(self.path), os.O_WRONLY | os.O_APPEND)
            try:
                os.write(fd, line.encode("utf-8"))
            finally:
                os.close(fd)

    @contextlib.contextmanager
    def _cross_process_lock(self):
        """Exclusive cross-process lock (portalocker) or a no-op fallback.

        When portalocker is unavailable the lock is a no-op and ``record()``
        relies on ``O_APPEND`` single-write atomicity — byte integrity is
        preserved but two processes could still fork the chain.  Install
        portalocker for full cross-process chain integrity.
        """
        if _PORTALOCKER_AVAILABLE:
            handle = open(self.path, "a+", encoding="utf-8")
            try:
                portalocker.lock(handle, portalocker.LOCK_EX)
                yield handle
            finally:
                try:
                    portalocker.unlock(handle)
                finally:
                    handle.close()
        else:
            yield None

    def record(
        self,
        event: str,
        state_id: str,
        is_secure: bool,
        detail: str | None = None,
        latency_ms: float | None = None,
        tokens_used: int | None = None,
        messages: list[dict[str, str]] | None = None,
        response: str | None = None,
    ) -> dict[str, Any]:
        """Appends one tamper-evident record. No update/delete by design.

        *messages* - the exact message list sent to the LLM, stored so that
        :meth:`replay` can re-run the same prompt on a different model.
        *response* - the exact output text, stored so that standalone
        receipts (``brompt.receipt``) can be re-exported from the trail.
        """
        with self._lock, self._cross_process_lock() as handle:
            prev_hash = self._last_hash(handle)
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
            if response is not None:
                payload["response"] = response
            entry_hash = self._hash_entry(prev_hash, payload)
            record: dict[str, Any] = {**payload, "entry_hash": entry_hash}
            if self._hmac_key is not None:
                sig = hmac.new(self._hmac_key, entry_hash.encode("utf-8"), hashlib.sha256).hexdigest()
                record["hmac"] = sig
            if self._signing_key is not None:
                signature = self._signing_key.sign(entry_hash.encode("utf-8"))
                record["signature"] = signature.hex()
                record["pubkey_id"] = self._pubkey_id
            self._append(record, handle)
            self._tail_cache = (self.path.stat().st_size, entry_hash)
            return record

    def verify(self) -> bool:
        """Replays the whole chain and returns ``False`` on the first break.

        When the log was created with a *secret_key*, every signed entry
        must carry a valid ``hmac`` field; when created with an Ed25519
        *signing_key*, every entry must carry a valid ``signature``.  An
        entry missing the expected field is treated as a downgrade attack.

        For a detailed, locatable failure report use :meth:`verify_report`.
        """
        return self.verify_report()["ok"]

    def verify_report(self) -> dict[str, Any]:
        """Like :meth:`verify` but returns a structured report.

        Returns a dict with keys ``ok`` (bool), ``reason`` (str),
        ``line`` (1-based index of the failing entry or ``None``),
        ``entries`` (number of valid entries scanned), and — when a chain
        break or hash mismatch is found — ``expected_prev_hash`` and
        ``found_prev_hash``.
        """
        prev_hash = GENESIS_HASH
        entries = 0
        try:
            with self._cross_process_lock() as handle:
                if self.path.stat().st_size == 0:
                    return {"ok": True, "reason": "empty", "line": None, "entries": 0,
                            "expected_prev_hash": None, "found_prev_hash": None}
                for line_index, line in enumerate(self._read_lines(handle), start=1):
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        return {"ok": False, "reason": "invalid_json", "line": line_index,
                                "entries": entries, "expected_prev_hash": prev_hash,
                                "found_prev_hash": None}
                    claimed_hash = record.get("entry_hash")
                    found_prev = record.get("prev_hash")
                    if found_prev != prev_hash:
                        return {"ok": False, "reason": "chain_break", "line": line_index,
                                "entries": entries, "expected_prev_hash": prev_hash,
                                "found_prev_hash": found_prev}
                    payload = {k: v for k, v in record.items() if k not in _SIGNING_FIELDS}
                    if self._hash_entry(prev_hash, payload) != claimed_hash:
                        return {"ok": False, "reason": "hash_mismatch", "line": line_index,
                                "entries": entries, "expected_prev_hash": prev_hash,
                                "found_prev_hash": found_prev}
                    if self._hmac_key is not None:
                        stored_hmac = record.get("hmac")
                        if stored_hmac is None:
                            return {"ok": False, "reason": "missing_hmac", "line": line_index,
                                    "entries": entries, "expected_prev_hash": prev_hash,
                                    "found_prev_hash": found_prev}
                        expected = hmac.new(self._hmac_key, claimed_hash.encode("utf-8"),
                                            hashlib.sha256).hexdigest()
                        if not hmac.compare_digest(expected, stored_hmac):
                            return {"ok": False, "reason": "hmac_mismatch", "line": line_index,
                                    "entries": entries, "expected_prev_hash": prev_hash,
                                    "found_prev_hash": found_prev}
                    if self._signing_key is not None:
                        stored_sig = record.get("signature")
                        if stored_sig is None:
                            return {"ok": False, "reason": "missing_signature", "line": line_index,
                                    "entries": entries, "expected_prev_hash": prev_hash,
                                    "found_prev_hash": found_prev}
                        try:
                            self._signing_key.public_key().verify(
                                bytes.fromhex(stored_sig), claimed_hash.encode("utf-8")
                            )
                        except (ValueError, InvalidSignature):
                            return {"ok": False, "reason": "signature_mismatch", "line": line_index,
                                    "entries": entries, "expected_prev_hash": prev_hash,
                                    "found_prev_hash": found_prev}
                    prev_hash = claimed_hash
                    entries += 1
        except OSError as exc:
            return {"ok": False, "reason": f"io_error: {exc}", "line": None,
                    "entries": entries, "expected_prev_hash": prev_hash, "found_prev_hash": None}
        return {"ok": True, "reason": "valid", "line": None, "entries": entries,
                "expected_prev_hash": None, "found_prev_hash": None}

    def read_all(self) -> list[dict[str, Any]]:
        with self._lock, self._cross_process_lock() as handle:
            if self.path.stat().st_size == 0:
                return []
            entries = []
            for line in self._read_lines(handle):
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    # Skip a trailing partial line from a concurrent writer.
                    continue
            return entries

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
        and (when the log is signed) carry a valid HMAC/Ed25519 signature.

        Returns ``False`` if the entry is missing or tampered with.
        """
        entry = self.find_entry(entry_hash)
        if entry is None:
            return False
        payload = {k: v for k, v in entry.items() if k not in _SIGNING_FIELDS}
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
        if self._signing_key is not None:
            stored_sig = entry.get("signature")
            if stored_sig is None:
                return False  # downgrade attack
            try:
                self._signing_key.public_key().verify(
                    bytes.fromhex(stored_sig), entry_hash.encode("utf-8")
                )
            except (ValueError, InvalidSignature):
                return False
        return True

    def replay(
        self,
        entry_hash: str,
        provider: "LLMProvider | None" = None,
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
            model = "replay"
        elif provider is None:
            return {"error": "No provider or fn supplied; cannot replay"}
        else:
            text = provider.generate(msgs, system=system)
            model = getattr(provider, "model", "replay")
        return {"original": entry, "replayed": ProviderResult(text=text, model=model)}
