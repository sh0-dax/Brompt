"""Shared pytest fixtures for feedback loop and API tests."""

import tempfile
from pathlib import Path

import pytest

from brompt.feedback import FeedbackLoop, PromptOptimizer, PromptOutcome


@pytest.fixture
def temp_storage():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = Path(f.name)
    yield str(path)
    if path.exists():
        path.unlink()


@pytest.fixture
def feedback_loop(temp_storage):
    loop = FeedbackLoop(storage_path=temp_storage)
    yield loop
    loop.reset()


@pytest.fixture
def populated_loop(feedback_loop):
    for i in range(20):
        feedback_loop.record_execution(
            template_id="template_a",
            generated_prompt=f"prompt-{i}",
            model_response=f"response-{i}",
            outcome=PromptOutcome.SUCCESS,
            latency_ms=1000.0 + i * 50,
            tokens_used=200,
            user_feedback=5 if i < 15 else 3,
            model_name="gpt-4",
        )
    for i in range(10):
        outcome = PromptOutcome.HALLUCINATION if i < 5 else PromptOutcome.ERROR
        feedback_loop.record_execution(
            template_id="template_b",
            generated_prompt=f"bad-prompt-{i}",
            model_response="bad-response",
            outcome=outcome,
            latency_ms=3000.0,
            tokens_used=150,
            user_feedback=2,
            model_name="gpt-3.5",
        )
    return feedback_loop


@pytest.fixture
def optimizer():
    return PromptOptimizer()
