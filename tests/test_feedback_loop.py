"""Tests for the feedback loop system (models, loop, optimizer)."""

import pytest

from brompt.feedback import FeedbackLoop, PromptOutcome, PromptExecution, TemplateStats, PromptOptimizer


class TestPromptOutcome:
    def test_from_string_valid(self):
        assert PromptOutcome.from_string("success") == PromptOutcome.SUCCESS
        assert PromptOutcome.from_string("hallucination") == PromptOutcome.HALLUCINATION

    def test_from_string_invalid_falls_back_to_error(self):
        assert PromptOutcome.from_string("bogus") == PromptOutcome.ERROR

    def test_enum_values(self):
        assert PromptOutcome.SUCCESS.value == "success"
        assert PromptOutcome.ERROR.value == "error"


class TestPromptExecution:
    def test_creation(self):
        e = PromptExecution(template_id="t", generated_prompt="p", model_response="r",
                            outcome=PromptOutcome.SUCCESS, latency_ms=100, tokens_used=10)
        assert e.template_id == "t"
        assert e.outcome == PromptOutcome.SUCCESS

    def test_to_dict_and_back(self):
        orig = PromptExecution(template_id="t", generated_prompt="p", model_response="r",
                               outcome=PromptOutcome.SUCCESS, latency_ms=100, tokens_used=10,
                               user_feedback=4, model_name="gpt-4")
        d = orig.to_dict()
        restored = PromptExecution.from_dict(d)
        assert restored.template_id == "t"
        assert restored.outcome == PromptOutcome.SUCCESS
        assert restored.latency_ms == 100
        assert restored.user_feedback == 4


class TestTemplateStats:
    def test_initial_state(self):
        s = TemplateStats(template_id="t")
        assert s.total_uses == 0 and s.success_rate == 0.0

    def test_success_updates_stats(self):
        s = TemplateStats(template_id="t")
        s.update_from_execution(PromptExecution(template_id="t", generated_prompt="", model_response="",
                                outcome=PromptOutcome.SUCCESS, latency_ms=100, tokens_used=10, user_feedback=5))
        assert s.total_uses == 1 and s.success_count == 1 and s.success_rate == 100.0 and s.avg_rating == 5.0

    def test_partial_weights_half(self):
        s = TemplateStats(template_id="t")
        s.update_from_execution(PromptExecution(template_id="t", generated_prompt="", model_response="",
                                outcome=PromptOutcome.SUCCESS, latency_ms=100, tokens_used=10))
        s.update_from_execution(PromptExecution(template_id="t", generated_prompt="", model_response="",
                                outcome=PromptOutcome.PARTIAL, latency_ms=100, tokens_used=10))
        assert s.success_rate == 75.0

    def test_running_average_latency(self):
        s = TemplateStats(template_id="t")
        for lat in [1000, 2000, 3000]:
            s.update_from_execution(PromptExecution(template_id="t", generated_prompt="", model_response="",
                                    outcome=PromptOutcome.SUCCESS, latency_ms=lat, tokens_used=10))
        assert s.avg_latency == 2000.0


class TestFeedbackLoop:
    def test_init_empty(self, temp_storage):
        loop = FeedbackLoop(storage_path=temp_storage)
        assert len(loop.executions) == 0 and len(loop.template_stats) == 0

    def test_record_single(self, feedback_loop):
        feedback_loop.record_execution(template_id="t", generated_prompt="p", model_response="r",
                                       outcome=PromptOutcome.SUCCESS, latency_ms=100, tokens_used=10)
        assert len(feedback_loop.executions) == 1
        assert "t" in feedback_loop.template_stats

    def test_user_feedback_validation(self, feedback_loop):
        with pytest.raises(ValueError, match="1-5"):
            feedback_loop.record_execution(template_id="t", generated_prompt="", model_response="",
                                           outcome=PromptOutcome.SUCCESS, latency_ms=100, tokens_used=10,
                                           user_feedback=99)

    def test_latency_validation(self, feedback_loop):
        with pytest.raises(ValueError, match="negative"):
            feedback_loop.record_execution(template_id="t", generated_prompt="", model_response="",
                                           outcome=PromptOutcome.SUCCESS, latency_ms=-1, tokens_used=10)

    def test_best_template_recommendation(self, populated_loop):
        assert populated_loop.get_best_template() == "template_a"

    def test_best_template_exclusion(self, populated_loop):
        assert populated_loop.get_best_template(exclude_ids=["template_a"]) == "template_b"

    def test_best_template_no_data(self, feedback_loop):
        assert feedback_loop.get_best_template() is None

    def test_improvement_suggestions(self, populated_loop):
        suggestions = populated_loop.generate_improvement_suggestions()
        tb = [s for s in suggestions if s["template_id"] == "template_b"]
        assert len(tb) > 0 and len(tb[0]["issues"]) > 0 and len(tb[0]["recommended_actions"]) > 0

    def test_performance_report(self, populated_loop):
        report = populated_loop.get_performance_report()
        assert report["status"] == "ok"
        assert report["summary"]["total_executions"] == 30
        assert "template_a" in report["templates_detail"]
        assert report["best_template"] is not None

    def test_template_health(self, populated_loop):
        h = populated_loop.get_template_health("template_a")
        assert h["health"] in ("excellent", "good")
        hb = populated_loop.get_template_health("template_b")
        assert hb["health"] in ("poor", "needs_improvement")

    def test_template_health_unknown(self, feedback_loop):
        assert feedback_loop.get_template_health("nonexistent")["status"] == "unknown"

    def test_persistence(self, temp_storage):
        loop1 = FeedbackLoop(storage_path=temp_storage)
        loop1.record_execution(template_id="t", generated_prompt="p", model_response="r",
                               outcome=PromptOutcome.SUCCESS, latency_ms=100, tokens_used=10)
        loop2 = FeedbackLoop(storage_path=temp_storage)
        assert len(loop2.executions) == 1
        assert "t" in loop2.template_stats

    def test_reset(self, populated_loop):
        populated_loop.reset()
        assert len(populated_loop.executions) == 0
        assert len(populated_loop.template_stats) == 0
