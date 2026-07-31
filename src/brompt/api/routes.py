"""FastAPI routes — wired to BromptEngine for execution and FeedbackLoop for analytics.

Uses ``app.state`` to hold shared dependencies instead of module-level
globals, making the app testable with ``TestClient``.
"""

import hmac
import logging
import os
import time
import uuid
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from ..config import WidgetConfig
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


def _api_key() -> str:
    """Read ``BROMPT_API_KEY`` per-request so rotation takes effect immediately."""
    return os.getenv("BROMPT_API_KEY", "")


def _cors_origins() -> list[str]:
    """Allowed CORS origins from ``BROMPT_CORS_ORIGINS`` (comma-separated).

    Defaults to local Streamlit/dev origins.  ``"*"`` is permitted only when
    credentials are disabled — see ``create_app``.
    """
    raw = os.getenv("BROMPT_CORS_ORIGINS", "").strip()
    if raw:
        return [o.strip() for o in raw.split(",") if o.strip()]
    return ["http://localhost:8501", "http://127.0.0.1:8501"]


def _load_engine_config() -> WidgetConfig:
    """Load config from YAML manifest, falling back to env vars."""
    manifest = Path("agent.brompt.yaml")
    if not manifest.exists():
        manifest = Path(__file__).resolve().parent.parent.parent.parent / "agent.brompt.yaml"
    if manifest.exists():
        return WidgetConfig.from_yaml(str(manifest))
    return WidgetConfig.from_env()


def verify_api_key(request: Request) -> None:
    """Dependency: reject requests missing or with invalid API key.

    Skipped when ``BROMPT_API_KEY`` is not set (development mode).  The key
    is compared in constant time to avoid timing attacks.
    """
    key = _api_key()
    if not key:
        return
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer ") and hmac.compare_digest(auth[7:], key):
        return
    raise HTTPException(status_code=401, detail="Invalid or missing API key")


async def get_engine(request: Request) -> BromptEngine:
    """Dependency: return the shared BromptEngine from app.state."""
    engine: BromptEngine | None = getattr(request.app.state, "engine", None)
    if engine is None:
        raise HTTPException(status_code=503, detail="Engine not initialised")
    return engine


async def get_feedback(request: Request) -> FeedbackLoop:
    """Dependency: return the shared FeedbackLoop from app.state."""
    feedback: FeedbackLoop | None = getattr(request.app.state, "feedback", None)
    if feedback is None:
        raise HTTPException(status_code=503, detail="Feedback not initialised")
    return feedback


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

    origins = _cors_origins()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials="*" not in origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    async def init_dependencies():
        config = _load_engine_config()
        manifest = Path("agent.brompt.yaml")
        if not manifest.exists():
            manifest = Path(__file__).resolve().parent.parent.parent.parent / "agent.brompt.yaml"
        engine = BromptEngine(config_path=str(manifest) if manifest.exists() else None)
        app.state.engine = engine
        app.state.feedback = FeedbackLoop(
            storage_path=config.feedback.storage_path,
            audit_log=engine.audit,
        )
        logger.info("BromptEngine initialised from %s", manifest if manifest.exists() else "env")

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
        dependencies=[Depends(verify_api_key)],
    )
    async def generate_prompt(
        req: GeneratePromptRequest,
        engine: BromptEngine = Depends(get_engine),
        feedback: FeedbackLoop = Depends(get_feedback),
    ):
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
        dependencies=[Depends(verify_api_key)],
    )
    async def record_feedback(
        fb: RecordFeedbackRequest,
        feedback: FeedbackLoop = Depends(get_feedback),
    ):
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
        dependencies=[Depends(verify_api_key)],
    )
    async def performance_report(
        feedback: FeedbackLoop = Depends(get_feedback),
    ):
        return feedback.get_performance_report()

    @app.get(
        "/api/v1/reports/templates",
        tags=["Reports"],
        dependencies=[Depends(verify_api_key)],
    )
    async def templates_summary(
        feedback: FeedbackLoop = Depends(get_feedback),
    ):
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
        dependencies=[Depends(verify_api_key)],
    )
    async def template_health(
        template_id: str,
        feedback: FeedbackLoop = Depends(get_feedback),
    ):
        health = feedback.get_template_health(template_id)
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
        dependencies=[Depends(verify_api_key)],
    )
    async def improvement_suggestions(
        feedback: FeedbackLoop = Depends(get_feedback),
    ):
        return feedback.generate_improvement_suggestions()

    @app.get(
        "/api/v1/reports/best-template",
        tags=["Reports"],
        dependencies=[Depends(verify_api_key)],
    )
    async def best_template(
        feedback: FeedbackLoop = Depends(get_feedback),
    ):
        best = feedback.get_best_template()
        if best is None:
            raise HTTPException(status_code=404, detail="Insufficient data for recommendation")
        stats = feedback.template_stats.get(best)
        return {
            "best_template": best,
            "success_rate": f"{stats.success_rate:.1f}%" if stats else "N/A",
            "avg_rating": f"{stats.avg_rating:.1f}/5" if stats else "N/A",
        }

    @app.get("/health", tags=["System"])
    async def health_check(
        feedback: FeedbackLoop = Depends(get_feedback),
    ):
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
