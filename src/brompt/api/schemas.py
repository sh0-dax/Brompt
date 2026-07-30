"""Pydantic v2 request/response schemas for the REST API."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class GeneratePromptRequest(BaseModel):
    """Request to generate a prompt through the Brompt engine."""
    template_id: str = Field(..., min_length=1, max_length=100)
    user_input: str = Field(..., min_length=1, max_length=5000)
    model_name: Optional[str] = None
    temperature: Optional[float] = Field(None, ge=0, le=2)

    @field_validator("user_input")
    @classmethod
    def not_blank(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("user_input cannot be blank")
        return stripped


class RecordFeedbackRequest(BaseModel):
    """Request to record execution feedback."""
    template_id: str = Field(..., min_length=1, max_length=100)
    outcome: str = Field(..., pattern=r"^(success|partial|hallucination|irrelevant|refused|error)$")
    user_feedback: Optional[int] = Field(None, ge=1, le=5)
    latency_ms: float = Field(..., ge=0)
    tokens_used: int = Field(..., ge=0)
    model_name: Optional[str] = None


class ExecutionData(BaseModel):
    """Typed payload returned inside ``GeneratedPromptResponse.data``."""
    llm_response: Optional[str] = None
    processed_input: Optional[str] = None
    tokens_used: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    plain_prompt_tokens: int = 0
    model: Optional[str] = None


class GeneratedPromptResponse(BaseModel):
    """Response returned after generating a prompt."""
    template_id: str
    is_secure: bool
    state_id: str
    data: ExecutionData
    error_message: Optional[str] = None
    latency_ms: Optional[float] = None


class FeedbackResponse(BaseModel):
    """Confirmation that feedback was recorded."""
    status: str = "recorded"
    template_id: str
    timestamp: datetime = Field(default_factory=datetime.now)


class PerformanceReportResponse(BaseModel):
    """Full performance report."""
    status: str
    generated_at: Optional[str] = None
    summary: Optional[dict] = None
    templates_detail: Optional[dict] = None
    best_template: Optional[str] = None
    improvement_suggestions: Optional[list] = None


class TemplateHealthResponse(BaseModel):
    """Health status for a single template."""
    template_id: str
    health: str
    total_uses: int
    success_rate: str
    avg_rating: str
    avg_latency: str
