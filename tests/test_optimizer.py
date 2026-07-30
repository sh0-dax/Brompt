"""Tests for TokenOptimizer."""
import pytest
from brompt.optimizer import TokenOptimizer


class TestTokenEstimator:
    def test_estimate_tokens_empty(self):
        assert TokenOptimizer.estimate_tokens("") == 0

    def test_estimate_tokens_short(self):
        assert TokenOptimizer.estimate_tokens("h") == 1

    def test_estimate_tokens_longer(self):
        text = "hello " * 100
        assert TokenOptimizer.estimate_tokens(text) == 150


class TestContentCleanup:
    def test_remove_redundant_whitespace(self):
        text = "hello   world\n\n\n\nfoo"
        result = TokenOptimizer.remove_redundant_whitespace(text)
        assert "   " not in result
        assert "\n\n\n" not in result

    def test_remove_duplicate_no_dupes(self):
        text = "line1\nline2\nline3"
        result = TokenOptimizer.remove_duplicate_content(text)
        assert result == text


class TestCompressContext:
    def test_compress_short_messages(self):
        messages = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ]
        compressed = TokenOptimizer.compress_context(messages)
        assert len(compressed) == 2
        assert compressed[0]["content"] == "hi"

    def test_compress_long_message(self):
        messages = [
            {"role": "user", "content": "a" * 1000},
            {"role": "assistant", "content": "b"},
        ]
        compressed = TokenOptimizer.compress_context(messages, max_messages=2)
        assert len(compressed) == 2

    def test_compress_exceeds_max_messages(self):
        messages = [{"role": "user", "content": f"msg{i}"} for i in range(10)]
        compressed = TokenOptimizer.compress_context(messages, max_messages=4)
        assert len(compressed) <= 4

    def test_compress_handles_code(self):
        messages = [{"role": "user", "content": "def foo():\n    return 42\n" * 50}]
        compressed = TokenOptimizer.compress_context(messages)
        assert len(compressed) == 1


class TestSummarizeHistory:
    def test_summarize_short_history(self):
        messages = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]
        result = TokenOptimizer.summarize_history(messages)
        assert isinstance(result, str)

    def test_summarize_empty(self):
        assert TokenOptimizer.summarize_history([]) == ""

    def test_summarize_long_history(self):
        messages = [{"role": "user", "content": f"msg{i}"} for i in range(10)]
        result = TokenOptimizer.summarize_history(messages)
        assert len(result) > 0


class TestBuildOptimizedPrompt:
    def test_build_optimized_prompt_basic(self):
        result = TokenOptimizer().build_optimized_prompt(
            system_prompt="You are helpful.",
            user_input="Hello!",
            template_content="",
        )
        prompt, stats = result
        assert "You are helpful" in prompt or prompt == "" or "Hello" in prompt

    def test_build_api_messages(self):
        result = TokenOptimizer().build_api_messages(
            system_prompt="You are helpful.",
            user_input="Hello!",
            template_content="",
        )
        messages, stats = result
        assert len(messages) >= 1
