"""Data schemas and type contracts for Brompt Engine."""

from typing import Any

from pydantic import BaseModel, Field


class SecurityConfig(BaseModel):
    isolation_level: str = Field(default="ZERO_TRUST")
    sanitize_inputs: bool = Field(default=True)
    max_payload_size_kb: int = Field(default=64)


class MemoryConfig(BaseModel):
    paging_mode: str = Field(default="VIRTUAL_STATE_O1")
    max_history_turns: int = Field(default=3)


class FeedbackConfig(BaseModel):
    """Settings for the feedback loop system (analytics, regression, recommendations)."""
    storage_path: str = Field(default="data/feedback_store.json", description="Path to the JSON persistence file")
    regression_threshold: float = Field(default=0.15, description="Max allowed drop in success rate before alert")
    min_uses_for_recommendation: int = Field(default=5, description="Minimum executions before a template is eligible for recommendations")
    recent_window_size: int = Field(default=10, description="Number of recent executions used for regression checks")
    max_stored_executions: int = Field(default=1000, description="Max stored execution records before trimming")
    success_rate_weight: float = Field(default=0.5, description="Weight of success rate in template scoring (0-1)")
    rating_weight: float = Field(default=0.3, description="Weight of user rating in template scoring (0-1)")
    speed_weight: float = Field(default=0.2, description="Weight of latency in template scoring (0-1)")
    high_latency_threshold_ms: float = Field(default=5000.0, description="Latency above this triggers improvement suggestions")
    low_success_threshold: float = Field(default=70.0, description="Success rate below this triggers improvement suggestions")
    low_rating_threshold: float = Field(default=3.5, description="Average rating below this triggers improvement suggestions")


class APIConfig(BaseModel):
    """Settings for the REST API server."""
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000, ge=1024, le=65535)
    workers: int = Field(default=4, ge=1)
    rate_limit_per_minute: int = Field(default=60, ge=1)
    enable_metrics: bool = Field(default=True)
    enable_docs: bool = Field(default=True)


class BromptConfig(BaseModel):
    name: str = Field(default="DefaultAgent")
    version: str = Field(default="1.0.0")
    environment: str = Field(default="production")
    security_policy: SecurityConfig = Field(default_factory=SecurityConfig)
    memory_strategy: MemoryConfig = Field(default_factory=MemoryConfig)
    feedback: FeedbackConfig = Field(default_factory=FeedbackConfig)
    api: APIConfig = Field(default_factory=APIConfig)


class ExecutionResult(BaseModel):
    state_id: str
    is_secure: bool
    data: dict[str, Any]
    error_message: str | None = None
