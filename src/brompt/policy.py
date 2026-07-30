"""Policy-as-Code engine — per-tenant allow/deny rules evaluated before
the prompt reaches any provider.

Rules are defined inside the YAML manifest under
``security_policy.rules``.

Simple caller-id match::

    - caller_id: "tenant-alpha-*"
      action: allow

Compound conditions with AND/OR/NOT::

    - action: deny
      when:
        and:
          - caller_id: "suspected-*"
          - role: anonymous
        reason: "anonymous users from suspected sources blocked"

Each condition key is an attribute name on the context dict passed to
``evaluate()``. The first matching rule wins; if no rule matches the
default is ``allow``.
"""

import fnmatch
import logging
from typing import Any

logger = logging.getLogger("brompt.policy")


class PolicyRule:
    """A single allow/deny rule with optional compound conditions."""

    __slots__ = ("action", "caller_id", "reason", "when")

    def __init__(self, caller_id: str = "*", action: str = "allow", reason: str = "",
                 when: "Condition | None" = None):
        self.caller_id = caller_id
        self.action = action
        self.reason = reason
        self.when = when

    @classmethod
    def from_dict(cls, d: dict) -> "PolicyRule":
        raw_when = d.get("when")
        when = Condition.from_dict(raw_when) if isinstance(raw_when, dict) else None
        return cls(
            caller_id=str(d.get("caller_id", "*")),
            action=str(d.get("action", "allow")),
            reason=str(d.get("reason", "")),
            when=when,
        )

    def matches(self, context: dict[str, Any]) -> bool:
        if self.when is not None:
            return self.when.evaluate(context)
        caller_id = context.get("caller_id", "")
        return fnmatch.fnmatch(caller_id, self.caller_id)

    def __repr__(self) -> str:
        return f"PolicyRule(action={self.action!r}, when={self.when or self.caller_id!r})"


class Condition:
    """A condition expression tree supporting ``and``, ``or``, ``not``,
    and leaf attribute comparisons."""

    def __init__(self, op: str, sub: list["Condition"] | None = None,
                 attr: str | None = None, pattern: str | None = None):
        self.op = op
        self.sub = sub or []
        self.attr = attr
        self.pattern = pattern

    def evaluate(self, context: dict[str, Any]) -> bool:
        if self.op == "and":
            return all(c.evaluate(context) for c in self.sub)
        if self.op == "or":
            return any(c.evaluate(context) for c in self.sub)
        if self.op == "not":
            return not self.sub[0].evaluate(context) if self.sub else True
        value = context.get(self.attr, "")
        if isinstance(value, str):
            return fnmatch.fnmatch(value, self.pattern or "*")
        return value == self.pattern

    @classmethod
    def from_dict(cls, d: dict) -> "Condition":
        if "and" in d:
            subs = [cls.from_dict(item) if isinstance(item, dict) else cls._leaf(item)
                    for item in d["and"]]
            return cls(op="and", sub=subs)
        if "or" in d:
            subs = [cls.from_dict(item) if isinstance(item, dict) else cls._leaf(item)
                    for item in d["or"]]
            return cls(op="or", sub=subs)
        if "not" in d:
            inner = d["not"]
            sub = cls.from_dict(inner) if isinstance(inner, dict) else cls._leaf(inner)
            return cls(op="not", sub=[sub])
        return cls._leaf(d)

    @classmethod
    def _leaf(cls, d: dict) -> "Condition":
        for key, val in d.items():
            return cls(op="match", attr=key, pattern=str(val))
        return cls(op="match", attr="", pattern="*")

    def __repr__(self) -> str:
        if self.op == "match":
            return f"{self.attr}={self.pattern!r}"
        return f"{self.op}({', '.join(repr(s) for s in self.sub)})"


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
    """Evaluates caller identity/context against a list of :class:`PolicyRule`.

    Usage::

        engine = PolicyEngine.from_manifest(raw_manifest)
        result = engine.evaluate({"caller_id": "tenant-alpha-42", "role": "admin"})
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

    def evaluate(self, context: str | dict[str, Any]) -> PolicyResult:
        """Walk rules in order; return the first match or a default allow.

        *context* can be a plain ``caller_id`` string (backward compat)
        or a dict with attributes to match against condition expressions.
        """
        ctx: dict[str, Any] = (
            {"caller_id": context} if isinstance(context, str) else context
        )
        for rule in self.rules:
            if rule.matches(ctx):
                allowed = rule.action == "allow"
                return PolicyResult(allowed=allowed, reason=rule.reason)
        return PolicyResult(allowed=True, reason="default allow (no rules matched)")

    def check(self, context: str | dict[str, Any]) -> None:
        """Convenience: evaluate and raise :class:`PolicyViolationError`
        if the request is denied."""
        result = self.evaluate(context)
        if not result.allowed:
            if isinstance(context, dict):
                msg = result.reason or f"context {context} denied by policy"
            else:
                msg = result.reason or f"caller {context!r} denied by policy"
            raise PolicyViolationError(msg)
