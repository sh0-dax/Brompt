"""Tests for PromptClient widget."""
import pytest
from brompt.widget import PromptResult, LRUCache


def make_result(text="test", tokens=5):
    return PromptResult(
        user_input="hi", generated_prompt="you are a bot", response=text,
        template_id="default", model="test-model", tokens_used=tokens,
    )


class TestPromptResult:
    def test_required_fields(self):
        r = PromptResult(
            user_input="hi", generated_prompt="you are a bot",
            response="hello", template_id="default", model="test",
        )
        assert r.response == "hello"
        assert r.tokens_used == 0

    def test_to_dict(self):
        r = make_result("ok", tokens=50)
        d = r.to_dict()
        assert d["response"] == "ok"
        assert d["tokens_used"] == 50

    def test_from_dict(self):
        r = PromptResult.from_dict({
            "user_input": "hi", "generated_prompt": "prompt",
            "response": "res", "template_id": "t1", "model": "m1",
            "tokens_used": 10,
        })
        assert r.response == "res"
        assert r.tokens_used == 10


class TestLRUCache:
    def test_set_and_get(self):
        cache = LRUCache(max_entries=10, ttl_seconds=60)
        result = make_result("test")
        cache.set("hello", "default", {}, result)
        assert cache.get("hello", "default", {}) is result

    def test_cache_miss(self):
        cache = LRUCache(max_entries=10, ttl_seconds=60)
        assert cache.get("nonexistent", "default", {}) is None

    def test_clear(self):
        cache = LRUCache(max_entries=10, ttl_seconds=60)
        result = make_result("test")
        cache.set("hello", "default", {}, result)
        cache.clear()
        assert cache.get("hello", "default", {}) is None

    def test_len(self):
        cache = LRUCache(max_entries=10, ttl_seconds=60)
        cache.set("a", "default", {}, make_result("a"))
        cache.set("b", "default", {}, make_result("b"))
        assert len(cache) == 2


class TestPromptClientInit:
    def test_init_requires_api_key(self):
        from brompt.config import WidgetConfig
        cfg = WidgetConfig(provider=WidgetConfig().provider)
        with pytest.raises(ValueError, match="API key required"):
            from brompt.widget import PromptClient
            PromptClient(config=cfg)

    def test_init_with_config_and_key(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-fake-key")
        from brompt.widget import PromptClient
        client = PromptClient()
        assert client.config is not None

    def test_init_disables_auto_detect(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-fake-key")
        from brompt.widget import PromptClient
        client = PromptClient(enable_auto_detect=False)
        assert client._detector is None

    def test_init_with_audit_log(self, monkeypatch, tmp_path):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-fake-key")
        log_path = str(tmp_path / "test_audit.log")
        from brompt.widget import PromptClient
        client = PromptClient(audit_log_path=log_path)
        assert client._audit is not None
