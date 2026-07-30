"""Policy-as-Code engine — per-tenant allow/deny rules evaluated before
the prompt reaches any provider.

Rules are defined inside the YAML manifest under
``security_policy.rules``::

    security_policy:
      rules:
        - caller_id: "tenant-alpha-*"
          action: allow
        - caller_id: "suspected-bot-*"
          action: deny
          reason: "known abuse pattern"

Each rule is matched against the *caller_id* supplied at execution
time using ``fnmatch`` (``*`` / ``?`` wildcards).  The first matching
rule wins; if no rule matches the default is ``allow``.
"""

import fnmatch
import logging

logger = logging.getLogger("brompt.policy")


class PolicyRule:
    """A single allow/deny rule from the manifest."""

    __slots__ = ("caller_id", "action", "reason")

    def __init__(self, caller_id: str, action: str, reason: str = ""):
        self.caller_id = caller_id
        self.action = action
        self.reason = reason

    @classmethod
    def from_dict(cls, d: dict) -> "PolicyRule":
        return cls(
            caller_id=str(d.get("caller_id", "*")),
            action=str(d.get("action", "allow")),
            reason=str(d.get("reason", "")),
        )

    def __repr__(self) -> str:
        return f"PolicyRule(caller_id={self.caller_id!r}, action={self.action!r})"


class PolicyResult:
    __slots__ = ("allowed", "reason")

    def __init__(self, allowed: bool, reason: str = ""):
        self.allowed = allowed
        self.reason = reason

    def __repr__(self) -> str:
        return f"PolicyResult(allowed={self.allowed}, reason={self.reason!r})"


class PolicyViolationError(Exception):
    """Raised when the policy engine denies a request."""


class PolicyEngine:
    """Evaluates caller identity against a list of :class:`PolicyRule`.

    Usage::

        engine = PolicyEngine.from_manifest(raw_manifest)
        result = engine.evaluate("tenant-alpha-42")
        # → PolicyResult(allowed=True, ...)
    """

    def __init__(self, rules: list[PolicyRule] | None = None):
        self.rules = rules or []

    @classmethod
    def from_manifest(cls, raw_manifest: dict) -> "PolicyEngine":
        """Build from the top-level manifest dict (YAML output)."""
        rules_raw = []
        sec = raw_manifest.get("security_policy", {})
        if isinstance(sec, dict):
            rules_raw = sec.get("rules", [])
        return cls(rules=[PolicyRule.from_dict(r) for r in rules_raw])

    def evaluate(self, caller_id: str) -> PolicyResult:
        """Walk rules in order; return the first match or a default allow."""
        for rule in self.rules:
            if fnmatch.fnmatch(caller_id, rule.caller_id):
                allowed = rule.action == "allow"
                return PolicyResult(allowed=allowed, reason=rule.reason)
        return PolicyResult(allowed=True, reason="default allow (no rules matched)")

    def check(self, caller_id: str) -> None:
        """Convenience: evaluate and raise :class:`PolicyViolationError`
        if the request is denied."""
        result = self.evaluate(caller_id)
        if not result.allowed:
            msg = result.reason or f"caller {caller_id!r} denied by policy"
            raise PolicyViolationError(msg)
