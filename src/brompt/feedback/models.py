"""Data models for the feedback loop system."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class PromptOutcome(Enum):
    """Classification of a prompt execution result."""
    SUCCESS = "success"
    PARTIAL = "partial"
    HALLUCINATION = "hallucination"
    IRRELEVANT = "irrelevant"
    REFUSED = "refused"
    ERROR = "error"

    @classmethod
    def from_string(cls, value: str) -> "PromptOutcome":
        mapping = {
            "success": cls.SUCCESS,
            "partial": cls.PARTIAL,
            "hallucination": cls.HALLUCINATION,
            "irrelevant": cls.IRRELEVANT,
            "refused": cls.REFUSED,
            "error": cls.ERROR,
        }
        return mapping.get(value.lower(), cls.ERROR)


@dataclass
class PromptExecution:
    """Record of a single prompt execution."""
    template_id: str
    generated_prompt: str
    model_response: str
    outcome: PromptOutcome
    latency_ms: float
    tokens_used: int
    user_feedback: Optional[int] = None
    model_name: str = "unknown"
    metadata: dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "template_id": self.template_id,
            "outcome": self.outcome.value,
            "latency_ms": self.latency_ms,
            "tokens_used": self.tokens_used,
            "user_feedback": self.user_feedback,
            "model_name": self.model_name,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PromptExecution":
        return cls(
            template_id=data["template_id"],
            generated_prompt="",
            model_response="",
            outcome=PromptOutcome.from_string(data["outcome"]),
            latency_ms=data["latency_ms"],
            tokens_used=data["tokens_used"],
            user_feedback=data.get("user_feedback"),
            model_name=data.get("model_name", "unknown"),
            metadata=data.get("metadata", {}),
            timestamp=datetime.fromisoformat(data["timestamp"]),
        )


@dataclass
class TemplateStats:
    """Aggregated performance statistics for a single template."""
    template_id: str
    total_uses: int = 0
    success_count: int = 0
    partial_count: int = 0
    hallucination_count: int = 0
    error_count: int = 0
    avg_latency: float = 0.0
    avg_rating: float = 0.0
    total_ratings: int = 0
    last_used: Optional[datetime] = None
    first_used: Optional[datetime] = None

    @property
    def success_rate(self) -> float:
        if self.total_uses == 0:
            return 0.0
        effective_success = self.success_count + (self.partial_count * 0.5)
        return (effective_success / self.total_uses) * 100

    @property
    def pure_success_rate(self) -> float:
        if self.total_uses == 0:
            return 0.0
        return (self.success_count / self.total_uses) * 100

    def update_from_execution(self, execution: PromptExecution):
        n = self.total_uses
        self.total_uses += 1
        self.last_used = execution.timestamp
        if self.first_used is None:
            self.first_used = execution.timestamp

        if execution.outcome == PromptOutcome.SUCCESS:
            self.success_count += 1
        elif execution.outcome == PromptOutcome.PARTIAL:
            self.partial_count += 1
        elif execution.outcome == PromptOutcome.HALLUCINATION:
            self.hallucination_count += 1
        elif execution.outcome == PromptOutcome.ERROR:
            self.error_count += 1

        self.avg_latency = (self.avg_latency * n + execution.latency_ms) / (n + 1)

        if execution.user_feedback is not None:
            self.total_ratings += 1
            m = self.total_ratings
            self.avg_rating = (self.avg_rating * (m - 1) + execution.user_feedback) / m

    def to_summary(self) -> dict:
        return {
            "template_id": self.template_id,
            "total_uses": self.total_uses,
            "success_rate": f"{self.success_rate:.1f}%",
            "pure_success_rate": f"{self.pure_success_rate:.1f}%",
            "avg_rating": f"{self.avg_rating:.1f}/5",
            "avg_latency": f"{self.avg_latency:.0f}ms",
            "hallucination_rate": f"{(self.hallucination_count / self.total_uses * 100):.1f}%" if self.total_uses > 0 else "0%",  # noqa: E501
            "last_used": self.last_used.isoformat() if self.last_used else None,
            "first_used": self.first_used.isoformat() if self.first_used else None,
        }
