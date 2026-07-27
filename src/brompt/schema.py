"""Data schemas and type contracts for Brompt Engine."""

from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class SecurityConfig(BaseModel):
    isolation_level: str = Field(default="ZERO_TRUST")
    sanitize_inputs: bool = Field(default=True)
    max_payload_size_kb: int = Field(default=64)


class MemoryConfig(BaseModel):
    paging_mode: str = Field(default="VIRTUAL_STATE_O1")
    max_history_turns: int = Field(default=3)


class BromptConfig(BaseModel):
    name: str = Field(default="DefaultAgent")
    version: str = Field(default="1.0.0")
    environment: str = Field(default="production")
    security_policy: SecurityConfig = Field(default_factory=SecurityConfig)
    memory_strategy: MemoryConfig = Field(default_factory=MemoryConfig)


class ExecutionResult(BaseModel):
    state_id: str
    is_secure: bool
    data: Dict[str, Any]
    error_message: Optional[str] = None
