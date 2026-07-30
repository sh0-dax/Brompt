"""Tests for Session and SessionManager."""
import time
import pytest
from brompt.session import Session, SessionManager, Message


class TestMessage:
    def test_create_user_message(self):
        msg = Message(role="user", content="hello")
        assert msg.role == "user"
        assert msg.content == "hello"
        assert msg.is_user is True
        assert msg.is_assistant is False

    def test_create_assistant_message(self):
        msg = Message(role="assistant", content="world")
        assert msg.is_assistant is True
        assert msg.is_user is False

    def test_to_dict(self):
        msg = Message(role="user", content="test")
        d = msg.to_dict()
        assert d == {"role": "user", "content": "test"}

    def test_to_log(self):
        msg = Message(role="system", content="hello world")
        log = msg.to_log()
        assert "[SYSTEM]" in log
        assert "hello world" in log

    def test_tokens_default_zero(self):
        msg = Message(role="user", content="hi")
        assert msg.tokens_used == 0


class TestSession:
    def test_create_session(self):
        session = Session()
        assert session.id is not None
        assert len(session.messages) == 0

    def test_add_message(self):
        session = Session()
        session.add_message(role="user", content="hello", tokens_used=5, latency_ms=10.0)
        assert len(session.messages) == 1
        assert session.total_tokens == 5

    def test_add_multiple_messages(self):
        session = Session()
        session.add_message(role="user", content="hi", tokens_used=2)
        session.add_message(role="assistant", content="hello", tokens_used=10)
        assert len(session.messages) == 2
        assert session.total_tokens == 12
        assert session.total_user_messages == 1

    def test_get_context(self):
        session = Session()
        session.add_message(role="user", content="hi")
        session.add_message(role="assistant", content="hello")
        ctx = session.get_context(last_n=1)
        assert len(ctx) == 1
        assert ctx[0]["role"] == "assistant"

    def test_get_context_as_message_objects(self):
        session = Session()
        session.add_message(role="user", content="hi")
        ctx = session.get_context(as_dict=False)
        assert isinstance(ctx[0], Message)

    def test_clear(self):
        session = Session()
        session.add_message(role="user", content="hi")
        session.clear(keep_system_messages=False)
        assert len(session.messages) == 0

    def test_clear_keeps_system(self):
        session = Session()
        session.add_message(role="system", content="be helpful")
        session.add_message(role="user", content="hi")
        session.clear(keep_system_messages=True)
        assert len(session.messages) == 1
        assert session.messages[0].role == "system"

    def test_conversation_summary(self):
        session = Session()
        for i in range(5):
            session.add_message(role="user", content=f"q{i}")
            session.add_message(role="assistant", content=f"a{i}")
        summary = session.get_conversation_summary()
        assert "q0" in summary
        assert "a4" in summary

    def test_age_property(self):
        session = Session()
        assert session.age_minutes >= 0

    def test_avg_latency(self):
        session = Session()
        session.add_message(role="user", content="hi", latency_ms=100.0)
        assert session.avg_latency == 100.0

    def test_avg_latency_no_messages(self):
        session = Session()
        assert session.avg_latency == 0.0

    def test_to_summary(self):
        session = Session()
        session.add_message(role="user", content="hello", tokens_used=5)
        summary = session.to_summary()
        assert summary["total_messages"] == 1
        assert summary["total_tokens"] == 5


class TestSessionManager:
    def test_create_and_get(self):
        mgr = SessionManager()
        session = mgr.create_session(template_id="t1")
        assert mgr.get_session(session.id) is session

    def test_get_or_create(self):
        mgr = SessionManager()
        session = mgr.create_session(template_id="t1")
        same = mgr.get_or_create_session(session_id=session.id)
        assert same is session

    def test_get_or_create_new(self):
        mgr = SessionManager()
        session = mgr.get_or_create_session(session_id="nonexistent-id")
        assert session is not None

    def test_delete_session(self):
        mgr = SessionManager()
        session = mgr.create_session()
        mgr.delete_session(session.id)
        assert mgr.get_session(session.id) is None

    def test_list_sessions(self):
        mgr = SessionManager()
        mgr.create_session(template_id="a")
        mgr.create_session(template_id="b")
        assert len(mgr.list_sessions()) == 2

    def test_clear_all(self):
        mgr = SessionManager()
        mgr.create_session()
        mgr.clear_all()
        assert mgr.get_total_sessions() == 0

    def test_len(self):
        mgr = SessionManager()
        mgr.create_session()
        assert len(mgr) == 1

    def test_contains(self):
        mgr = SessionManager()
        session = mgr.create_session()
        assert session.id in mgr

    def test_iter(self):
        mgr = SessionManager()
        s1 = mgr.create_session()
        s2 = mgr.create_session()
        ids = [s.id for s in mgr]
        assert s1.id in ids
        assert s2.id in ids

    def test_max_sessions_eviction(self):
        mgr = SessionManager(max_sessions=3)
        s1 = mgr.create_session()
        s2 = mgr.create_session()
        s3 = mgr.create_session()
        s4 = mgr.create_session()
        assert mgr.get_total_sessions() <= 3
