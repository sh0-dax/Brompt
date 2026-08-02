"""Standalone signed execution receipts for external audit.

A receipt is a self-contained, tamper-evident JSON file that attests to a
single execution recorded in the audit trail.  It embeds the audit-proof
fields (``audit_hash``, ``audit_chain_id``, ``tamper_check``, ``signed_at``),
the exact response text and its SHA-256 hash, and — when the audit log is
signed — a signature over the canonical receipt payload.

Verification layers
-------------------
* **Response integrity** — ``response_hash`` must match the SHA-256 of the
  stored ``response`` text, so a receipt cannot silently ship altered output.
* **Chain anchoring** — ``audit_hash`` points at the tamper-evident entry in
  the append-only log; when the log is supplied, ``verify_receipt`` also
  re-checks ``AuditLog.find_entry`` / ``verify_entry``.
* **Signature** — when the log is HMAC-SHA256 or Ed25519 signed, the receipt
  is signed over its canonical payload.  An Ed25519 receipt embeds the
  public key (``pubkey_der_b64``), so a third party can verify it standalone
  without access to the log.

The file format is plain JSON with a ``schema_version`` so future evolution
stays backward-compatible.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

try:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    _CRYPTO_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only when cryptography is absent
    _CRYPTO_AVAILABLE = False
    InvalidSignature = Exception
    Ed25519PrivateKey = None  # type: ignore[assignment,misc]

RECEIPT_SCHEMA_VERSION = 1

_SIGNATURE_FIELDS = ("receipt_signature", "signature_scheme", "pubkey_id", "pubkey_der_b64")


@dataclass
class Receipt:
    """Tamper-evident attestation for a single signed execution."""

    schema_version: int = RECEIPT_SCHEMA_VERSION
    execution_id: Optional[str] = None
    audit_hash: Optional[str] = None
    audit_chain_id: Optional[str] = None
    tamper_check: Optional[bool] = None
    policy_id: Optional[str] = None
    compliance_mode: Optional[str] = None
    data_residency: Optional[str] = None
    model: Optional[str] = None
    tokens_used: int = 0
    cost: float = 0.0
    signed_at: Optional[str] = None
    response_hash: str = ""
    response: str = ""
    signature_scheme: Optional[str] = None
    receipt_signature: Optional[str] = None
    pubkey_id: Optional[str] = None
    pubkey_der_b64: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Receipt":
        valid = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**valid)

    @classmethod
    def from_audit_entry(cls, entry: dict[str, Any], audit_log: Any = None) -> "Receipt":
        """Build a receipt from a stored audit entry dict.

        *entry* is one record as returned by
        :meth:`AuditLog.read_all` / :meth:`AuditLog.find_entry`.  The
        response text is taken from the ``response`` payload field stored
        since the receipt feature shipped; older entries yield an empty
        response (still chain-anchored and signed when the log is signed).
        """
        entry_hash = entry.get("entry_hash")
        response = entry.get("response") or ""
        receipt = cls(
            execution_id=entry.get("state_id"),
            audit_hash=entry_hash,
            audit_chain_id=entry.get("prev_hash"),
            tamper_check=(
                audit_log.verify_entry(entry_hash)
                if entry_hash and audit_log is not None else None
            ),
            tokens_used=entry.get("tokens_used") or 0,
            response_hash=hashlib.sha256(response.encode("utf-8")).hexdigest(),
            response=response,
        )
        if audit_log is not None:
            _sign_receipt(receipt, audit_log)
        return receipt


def _canonical_payload(receipt: Receipt) -> str:
    """Stable serialization of the receipt body, excluding the signature."""
    body = {k: v for k, v in receipt.to_dict().items() if k not in _SIGNATURE_FIELDS}
    return json.dumps(body, sort_keys=True, ensure_ascii=False)


def _audit_public_der(audit_log: Any) -> str | None:
    key = getattr(audit_log, "_signing_key", None)
    if key is None or not _CRYPTO_AVAILABLE:
        return None
    try:
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

        der = key.public_key().public_bytes(
            encoding=Encoding.DER, format=PublicFormat.SubjectPublicKeyInfo
        )
        return base64.b64encode(der).decode("ascii")
    except Exception:  # pragma: no cover - defensive
        return None


def build_receipt(result: Any, audit_log: Any = None) -> Receipt:
    """Build a :class:`Receipt` from a signed execution *result*.

    *result* may be any object exposing ``to_audit_dict()`` and ``response``
    (e.g. :class:`~brompt.widget.SignedExecutionResult`).  When *audit_log*
    is supplied and signed, the receipt is signed over its canonical payload.
    """
    audit = result.to_audit_dict()
    receipt = Receipt(
        execution_id=audit.get("execution_id"),
        audit_hash=audit.get("audit_hash"),
        audit_chain_id=audit.get("audit_chain_id"),
        tamper_check=audit.get("tamper_check"),
        policy_id=audit.get("policy_id"),
        compliance_mode=audit.get("compliance_mode"),
        data_residency=audit.get("data_residency"),
        model=audit.get("model"),
        tokens_used=audit.get("tokens_used") or 0,
        cost=audit.get("cost") or 0.0,
        signed_at=audit.get("signed_at"),
        response_hash=hashlib.sha256(result.response.encode("utf-8")).hexdigest(),
        response=result.response,
    )
    if audit_log is not None:
        _sign_receipt(receipt, audit_log)
    return receipt


def _sign_receipt(receipt: Receipt, audit_log: Any) -> None:
    signing_key = getattr(audit_log, "_signing_key", None)
    hmac_key = getattr(audit_log, "_hmac_key", None)
    payload = _canonical_payload(receipt)
    if signing_key is not None and _CRYPTO_AVAILABLE:
        receipt.receipt_signature = signing_key.sign(payload.encode("utf-8")).hex()
        receipt.signature_scheme = "ed25519"
        receipt.pubkey_id = getattr(audit_log, "pubkey_id", None)
        receipt.pubkey_der_b64 = _audit_public_der(audit_log)
    elif hmac_key is not None:
        receipt.receipt_signature = hmac.new(
            hmac_key, payload.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        receipt.signature_scheme = "hmac"


def _verify_ed25519(receipt: Receipt, public_key: Any) -> bool:
    if not _CRYPTO_AVAILABLE or public_key is None:
        return False
    try:
        public_key.verify(
            bytes.fromhex(receipt.receipt_signature or ""),
            _canonical_payload(receipt).encode("utf-8"),
        )
        return True
    except (ValueError, InvalidSignature):
        return False


def verify_receipt(receipt: Receipt, audit_log: Any = None) -> dict[str, Any]:
    """Verify *receipt*, returning ``{"ok": bool, "reason": str}``.

    Checks, in order: presence of a chain anchor, response-text integrity,
    chain integrity (when *audit_log* is supplied) and the receipt signature.
    """
    if not receipt.audit_hash:
        return {"ok": False, "reason": "missing audit_hash (not a signed execution)"}
    if not receipt.response_hash:
        return {"ok": False, "reason": "missing response_hash"}
    actual = hashlib.sha256(receipt.response.encode("utf-8")).hexdigest()
    if actual != receipt.response_hash:
        return {"ok": False, "reason": "response hash mismatch (content altered)"}

    if audit_log is not None:
        if audit_log.find_entry(receipt.audit_hash) is None:
            return {"ok": False, "reason": "audit entry not found in the log"}
        if not audit_log.verify_entry(receipt.audit_hash):
            return {"ok": False, "reason": "audit entry failed chain/signature verification"}

    if receipt.receipt_signature:
        signing_key = getattr(audit_log, "_signing_key", None) if audit_log is not None else None
        hmac_key = getattr(audit_log, "_hmac_key", None) if audit_log is not None else None
        if signing_key is not None and _CRYPTO_AVAILABLE:
            if not _verify_ed25519(receipt, signing_key.public_key()):
                return {"ok": False, "reason": "ed25519 signature invalid"}
        elif hmac_key is not None:
            expected = hmac.new(
                hmac_key, _canonical_payload(receipt).encode("utf-8"), hashlib.sha256
            ).hexdigest()
            if not hmac.compare_digest(expected, receipt.receipt_signature):
                return {"ok": False, "reason": "hmac signature invalid"}
        elif receipt.pubkey_der_b64 and _CRYPTO_AVAILABLE:
            try:
                from cryptography.hazmat.primitives.serialization import load_der_public_key

                der = base64.b64decode(receipt.pubkey_der_b64)
                public_key = load_der_public_key(der)
            except Exception:
                return {"ok": False, "reason": "embedded public key unreadable"}
            if not _verify_ed25519(receipt, public_key):
                return {"ok": False, "reason": "ed25519 signature invalid"}
        else:
            return {"ok": False, "reason": "signature present but no key available to verify"}

    return {"ok": True, "reason": "ok"}


def save_receipt(receipt: Receipt, path: str | Path) -> None:
    """Persist *receipt* as pretty-printed JSON (``*.receipt``)."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as f:
        json.dump(receipt.to_dict(), f, indent=2, sort_keys=True, ensure_ascii=False)
        f.write("\n")


def load_receipt(path: str | Path) -> Receipt:
    """Load a receipt previously written by :func:`save_receipt`."""
    with Path(path).open("r", encoding="utf-8") as f:
        data = json.load(f)
    return Receipt.from_dict(data)


def to_datetime(value: Optional[str]) -> Optional[datetime]:
    """Parse the ISO ``signed_at`` field back into a datetime (best effort)."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
