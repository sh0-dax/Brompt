"""Unit tests for the Policy-as-Code engine."""

import pytest

from brompt.policy import PolicyEngine, PolicyRule, PolicyViolationError


class TestPolicyRule:
    def test_from_dict_defaults(self):
        rule = PolicyRule.from_dict({})
        assert rule.caller_id == "*"
        assert rule.action == "allow"
        assert rule.reason == ""

    def test_from_dict_full(self):
        rule = PolicyRule.from_dict({"caller_id": "prod-*", "action": "deny", "reason": "no prod access"})
        assert rule.caller_id == "prod-*"
        assert rule.action == "deny"
        assert rule.reason == "no prod access"


class TestPolicyEngine:
    def test_no_rules_default_allow(self):
        engine = PolicyEngine()
        result = engine.evaluate("anyone")
        assert result.allowed is True

    def test_deny_rule_matches_caller(self):
        engine = PolicyEngine([PolicyRule("bad-actor-*", "deny", "blocked")])
        result = engine.evaluate("bad-actor-42")
        assert result.allowed is False

    def test_allow_rule_overrides_default(self):
        engine = PolicyEngine([PolicyRule("trusted-*", "allow")])
        result = engine.evaluate("trusted-user")
        assert result.allowed is True

    def test_non_matching_rule_default_allow(self):
        engine = PolicyEngine([PolicyRule("internal-*", "deny")])
        result = engine.evaluate("external-user")
        assert result.allowed is True

    def test_first_rule_wins(self):
        engine = PolicyEngine([
            PolicyRule("overlap-*", "deny", "first"),
            PolicyRule("overlap-*", "allow", "second"),
        ])
        result = engine.evaluate("overlap-1")
        assert result.allowed is False
        assert result.reason == "first"

    def test_check_raises_on_deny(self):
        engine = PolicyEngine([PolicyRule("*", "deny")])
        with pytest.raises(PolicyViolationError):
            engine.check("anyone")

    def test_check_passes_on_allow(self):
        engine = PolicyEngine([PolicyRule("*", "allow")])
        engine.check("anyone")

    def test_from_manifest_empty(self):
        engine = PolicyEngine.from_manifest({})
        assert len(engine.rules) == 0

    def test_from_manifest_with_rules(self):
        manifest = {
            "security_policy": {
                "rules": [
                    {"caller_id": "admin-*", "action": "allow"},
                    {"caller_id": "bot-*", "action": "deny", "reason": "bots not allowed"},
                ]
            }
        }
        engine = PolicyEngine.from_manifest(manifest)
        assert len(engine.rules) == 2
        assert engine.rules[0].caller_id == "admin-*"
        assert engine.rules[1].action == "deny"
