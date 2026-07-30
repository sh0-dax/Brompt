"""FastAPI routes — wired to BromptEngine for execution and FeedbackLoop for analytics."""

import logging
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from ..core import BromptEngine
from ..feedback import FeedbackLoop, PromptOutcome
from .schemas import (
    FeedbackResponse,
    GeneratedPromptResponse,
    GeneratePromptRequest,
    PerformanceReportResponse,
    RecordFeedbackRequest,
    TemplateHealthResponse,
)

logger = logging.getLogger("brompt.api")

_engine: BromptEngine | None = None
_feedback: FeedbackLoop | None = None


def _get_engine() -> BromptEngine:
    global _engine
    if _engine is None:
        manifest = Path("agent.brompt.yaml")
        if not manifest.exists():
            manifest = Path(__file__).resolve().parent.parent.parent.parent / "agent.brompt.yaml"
        _engine = BromptEngine(config_path=str(manifest))
        logger.info("BromptEngine initialised from %s", manifest)
    return _engine


def _get_feedback() -> FeedbackLoop:
    global _feedback
    if _feedback is None:
        engine = _get_engine()
        _feedback = FeedbackLoop(
            storage_path=engine.config.feedback.storage_path,
            audit_log=engine.audit,
        )
    return _feedback


def _map_outcome(result, latency_ms: float) -> PromptOutcome:
    if result.is_secure and result.data.get("llm_response"):
        return PromptOutcome.SUCCESS
    if result.is_secure and not result.data.get("llm_response"):
        return PromptOutcome.SUCCESS
    err = (result.error_message or "").lower()
    if "security" in err or "violation" in err:
        return PromptOutcome.REFUSED
    if "rate_limit" in err:
        return PromptOutcome.ERROR
    if "provider" in err:
        return PromptOutcome.ERROR
    return PromptOutcome.ERROR


def create_app() -> FastAPI:
    app = FastAPI(
        title="Brompt Engine API",
        description="Prompt generation engine with feedback loop analytics",
        version="0.1.0-alpha",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def add_request_id(request: Request, call_next):
        request_id = str(uuid.uuid4())[:8]
        request.state.request_id = request_id
        start = time.time()
        response = await call_next(request)
        elapsed = time.time() - start
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time"] = f"{elapsed*1000:.0f}ms"
        return response

    @app.post(
        "/api/v1/prompts/generate",
        response_model=GeneratedPromptResponse,
        tags=["Prompts"],
    )
    async def generate_prompt(req: GeneratePromptRequest):
        engine = _get_engine()
        feedback = _get_feedback()
        start = time.time()

        result = await engine.execute_async(
            user_query=req.user_input,
            caller_id=req.template_id,
        )
        latency_ms = (time.time() - start) * 1000

        outcome = _map_outcome(result, latency_ms)
        feedback.record_execution(
            template_id=req.template_id,
            generated_prompt=result.data.get("processed_input", req.user_input),
            model_response=result.data.get("llm_response", ""),
            outcome=outcome,
            latency_ms=latency_ms,
            tokens_used=result.data.get("tokens_used", 0),
            model_name=req.model_name or "unknown",
        )

        return GeneratedPromptResponse(
            template_id=req.template_id,
            is_secure=result.is_secure,
            state_id=result.state_id,
            data=result.data,
            error_message=result.error_message,
            latency_ms=latency_ms,
        )

    @app.post(
        "/api/v1/feedback/record",
        response_model=FeedbackResponse,
        tags=["Feedback"],
    )
    async def record_feedback(fb: RecordFeedbackRequest):
        feedback = _get_feedback()
        try:
            outcome = PromptOutcome.from_string(fb.outcome)
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Invalid outcome: {fb.outcome}")

        feedback.record_execution(
            template_id=fb.template_id,
            generated_prompt="",
            model_response="",
            outcome=outcome,
            latency_ms=fb.latency_ms,
            tokens_used=fb.tokens_used,
            user_feedback=fb.user_feedback,
            model_name=fb.model_name or "unknown",
        )
        return FeedbackResponse(template_id=fb.template_id)

    @app.get(
        "/api/v1/reports/performance",
        response_model=PerformanceReportResponse,
        tags=["Reports"],
    )
    async def performance_report():
        return _get_feedback().get_performance_report()

    @app.get(
        "/api/v1/reports/templates",
        tags=["Reports"],
    )
    async def templates_summary():
        feedback = _get_feedback()
        return [
            {
                "template_id": tid,
                "total_uses": s.total_uses,
                "success_rate": f"{s.success_rate:.1f}%",
                "avg_rating": f"{s.avg_rating:.1f}/5",
                "avg_latency": f"{s.avg_latency:.0f}ms",
                "health": feedback.get_template_health(tid).get("health"),
            }
            for tid, s in feedback.template_stats.items()
        ]

    @app.get(
        "/api/v1/reports/templates/{template_id}",
        response_model=TemplateHealthResponse,
        tags=["Reports"],
    )
    async def template_health(template_id: str):
        health = _get_feedback().get_template_health(template_id)
        if health.get("status") == "unknown":
            raise HTTPException(status_code=404, detail="Template not found")
        return TemplateHealthResponse(
            template_id=template_id,
            health=health["health"],
            total_uses=health["total_uses"],
            success_rate=health["success_rate"],
            avg_rating=health["avg_rating"],
            avg_latency=health["avg_latency"],
        )

    @app.get(
        "/api/v1/reports/suggestions",
        tags=["Reports"],
    )
    async def improvement_suggestions():
        return _get_feedback().generate_improvement_suggestions()

    @app.get(
        "/api/v1/reports/best-template",
        tags=["Reports"],
    )
    async def best_template():
        best = _get_feedback().get_best_template()
        if best is None:
            raise HTTPException(status_code=404, detail="Insufficient data for recommendation")
        stats = _get_feedback().template_stats.get(best)
        return {
            "best_template": best,
            "success_rate": f"{stats.success_rate:.1f}%" if stats else "N/A",
            "avg_rating": f"{stats.avg_rating:.1f}/5" if stats else "N/A",
        }

    @app.get("/health", tags=["System"])
    async def health_check():
        feedback = _get_feedback()
        return {
            "status": "healthy",
            "version": "0.1.0-alpha",
            "templates_count": len(feedback.template_stats),
            "total_executions": len(feedback.executions),
        }

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error("Unhandled exception on %s: %s", request.url, exc, exc_info=exc)
        return JSONResponse(
            status_code=500,
            content={
                "error": "internal_server_error",
                "message": str(exc),
                "request_id": getattr(request.state, "request_id", "unknown"),
            },
        )

    return app


app = create_app()
