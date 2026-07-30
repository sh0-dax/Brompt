"""Session Management System."""

import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime
from threading import Lock
from typing import Iterator, Optional


@dataclass
class Message:
    role: str
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    tokens_used: int = 0
    latency_ms: float = 0.0
    metadata: dict = field(default_factory=dict)

    @property
    def is_user(self) -> bool:
        return self.role == "user"

    @property
    def is_assistant(self) -> bool:
        return self.role == "assistant"

    def to_dict(self) -> dict:
        return {"role": self.role, "content": self.content}

    def to_log(self) -> str:
        preview = self.content[:80].replace('\n', ' ')
        return f"[{self.role.upper()}] {preview}..."


@dataclass
class Session:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    template_id: Optional[str] = None
    messages: list[Message] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)
    total_messages: int = 0
    total_user_messages: int = 0
    total_tokens: int = 0
    total_latency_ms: float = 0.0

    def add_message(
        self,
        role: str,
        content: str,
        tokens_used: int = 0,
        latency_ms: float = 0.0,
        **metadata
    ) -> Message:
        message = Message(
            role=role, content=content, tokens_used=tokens_used,
            latency_ms=latency_ms, metadata=metadata,
        )
        self.messages.append(message)
        self.total_messages += 1
        self.total_tokens += tokens_used
        self.total_latency_ms += latency_ms
        self.last_activity = message.timestamp
        if role == "user":
            self.total_user_messages += 1
        return message

    def get_context(
        self,
        last_n: int = 10,
        include_system: bool = True,
        as_dict: bool = True,
    ) -> list:
        messages = self.messages
        if not include_system:
            messages = [m for m in messages if m.role != "system"]
        context = messages[-last_n:]
        if as_dict:
            return [m.to_dict() for m in context]
        return context

    def get_conversation_summary(self) -> str:
        if not self.messages:
            return "Empty conversation"
        lines = []
        for i, msg in enumerate(self.messages[-10:], 1):
            preview = msg.content[:60].replace('\n', ' ')
            lines.append(f"  {i}. [{msg.role}] {preview}...")
        return "\n".join(lines)

    def clear(self, keep_system_messages: bool = True):
        if keep_system_messages:
            self.messages = [m for m in self.messages if m.role == "system"]
        else:
            self.messages = []
        self.total_messages = len(self.messages)
        self.total_tokens = 0
        self.total_latency_ms = 0.0

    @property
    def age_minutes(self) -> float:
        return (datetime.now() - self.created_at).total_seconds() / 60

    @property
    def idle_minutes(self) -> float:
        return (datetime.now() - self.last_activity).total_seconds() / 60

    @property
    def avg_latency(self) -> float:
        if self.total_user_messages == 0:
            return 0.0
        return self.total_latency_ms / self.total_user_messages

    def to_summary(self) -> dict:
        return {
            "id": self.id,
            "template_id": self.template_id,
            "total_messages": self.total_messages,
            "total_tokens": self.total_tokens,
            "avg_latency_ms": f"{self.avg_latency:.0f}",
            "age_minutes": f"{self.age_minutes:.1f}",
            "idle_minutes": f"{self.idle_minutes:.1f}",
            "last_activity": self.last_activity.isoformat(),
        }


class SessionManager:
    def __init__(
        self,
        max_sessions: int = 100,
        max_messages_per_session: int = 100,
        session_ttl_minutes: int = 60,
        auto_cleanup: bool = True,
    ):
        self._max_sessions = max_sessions
        self._max_messages = max_messages_per_session
        self._session_ttl = session_ttl_minutes
        self._auto_cleanup = auto_cleanup
        self._sessions: OrderedDict[str, Session] = OrderedDict()
        self._lock = Lock()

    def create_session(
        self,
        template_id: Optional[str] = None,
        system_prompt: Optional[str] = None,
        **metadata
    ) -> Session:
        with self._lock:
            if self._auto_cleanup:
                self._cleanup_expired()
            if len(self._sessions) >= self._max_sessions:
                oldest_id = next(iter(self._sessions))
                del self._sessions[oldest_id]
            session = Session(template_id=template_id, metadata=metadata)
            if system_prompt:
                session.add_message("system", system_prompt)
            self._sessions[session.id] = session
            return session

    def get_session(self, session_id: str) -> Optional[Session]:
        session = self._sessions.get(session_id)
        if session is None:
            return None
        if session.idle_minutes > self._session_ttl:
            self.delete_session(session_id)
            return None
        return session

    def get_or_create_session(
        self, session_id: Optional[str] = None, **kwargs
    ) -> Session:
        if session_id:
            session = self.get_session(session_id)
            if session:
                return session
        return self.create_session(**kwargs)

    def delete_session(self, session_id: str) -> bool:
        with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                return True
            return False

    def _cleanup_expired(self):
        expired = []
        for sid, session in self._sessions.items():
            if session.idle_minutes > self._session_ttl:
                expired.append(sid)
        for sid in expired:
            del self._sessions[sid]

    def list_sessions(self) -> list[dict]:
        return [s.to_summary() for s in self._sessions.values()]

    def get_total_sessions(self) -> int:
        return len(self._sessions)

    def clear_all(self):
        with self._lock:
            self._sessions.clear()

    def __len__(self) -> int:
        return len(self._sessions)

    def __contains__(self, session_id: str) -> bool:
        return session_id in self._sessions

    def __iter__(self) -> Iterator[Session]:
        return iter(self._sessions.values())
