"""Unified entry point for the Brompt library."""

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from threading import Lock
from typing import Optional, AsyncIterator

from .audit import AuditLog
from .config import WidgetConfig, ProviderConfig, GenerationConfig, ProviderType, RoutingConfig
from .providers import ProviderFactory, LLMProvider, ProviderResult
from .router import ModelRouter, RoutingStrategy
from .session import Session, SessionManager, Message
from .pricing import estimate_cost
from .optimizer import TokenOptimizer

try:
    from .feedback import FeedbackLoop, PromptOutcome
    FEEDBACK_AVAILABLE = True
except ImportError:
    FEEDBACK_AVAILABLE = False
    FeedbackLoop = None
    PromptOutcome = None

try:
    import auto_detect as _auto_detect_module
    AUTO_DETECT_AVAILABLE = True
except ImportError:
    AUTO_DETECT_AVAILABLE = False
    _auto_detect_module = None


def _task_type_str(task_type) -> Optional[str]:
    """Convert a TaskType enum (or string) to its string value."""
    if task_type is None:
        return None
    if hasattr(task_type, 'value'):
        return task_type.value
    return str(task_type)

logger = logging.getLogger(__name__)


@dataclass
class PromptResult:
    user_input: str
    generated_prompt: str
    response: str
    template_id: str
    model: str
    session_id: Optional[str] = None
    tokens_used: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    plain_prompt_tokens: int = 0
    cost: float = 0.0
    plain_cost: float = 0.0
    latency_ms: float = 0.0
    finish_reason: Optional[str] = None
    feedback_id: Optional[str] = None
    tokens_saved: int = 0
    cost_saved: float = 0.0
    savings_percent: float = 0.0
    auto_detected: bool = False
    detected_task: Optional[str] = None
    detection_confidence: float = 0.0
    cached: bool = False
    metadata: dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "user_input": self.user_input,
            "generated_prompt": self.generated_prompt,
            "response": self.response,
            "template_id": self.template_id,
            "model": self.model,
            "session_id": self.session_id,
            "tokens_used": self.tokens_used,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "plain_prompt_tokens": self.plain_prompt_tokens,
            "cost": self.cost,
            "plain_cost": self.plain_cost,
            "overhead_cost": round(self.cost - self.plain_cost, 6),
            "latency_ms": self.latency_ms,
            "finish_reason": self.finish_reason,
            "feedback_id": self.feedback_id,
            "tokens_saved": self.tokens_saved,
            "cost_saved": self.cost_saved,
            "savings_percent": self.savings_percent,
            "auto_detected": self.auto_detected,
            "detected_task": self.detected_task,
            "detection_confidence": self.detection_confidence,
            "cached": self.cached,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PromptResult":
        valid_fields = cls.__dataclass_fields__
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered)

    @property
    def cost_breakdown(self) -> dict:
        return {
            "total": round(self.cost, 6),
            "prompt": round(self.plain_cost, 6),
            "overhead": round(self.cost - self.plain_cost, 6),
            "overhead_pct": round((self.cost - self.plain_cost) / self.cost * 100, 1) if self.cost > 0 else 0.0,
        }

    def __str__(self) -> str:
        return self.response

    def __repr__(self) -> str:
        overhead = self.cost - self.plain_cost
        tag = " [CACHED]" if self.cached else ""
        saved_tag = f" saved={self.tokens_saved}tok({self.savings_percent:.0f}%)" if self.tokens_saved else ""
        return (
            f"PromptResult(response={self.response[:50]}...{tag}, "
            f"cost=${self.cost:.6f} [prompt=${self.plain_cost:.6f}+overhead=${overhead:.6f}], "
            f"tokens={self.prompt_tokens}in/{self.completion_tokens}out, "
            f"latency={self.latency_ms:.0f}ms{saved_tag})"
        )


class LRUCache:
    def __init__(self, max_entries: int = 1000, ttl_seconds: int = 3600):
        self._max_entries = max_entries
        self._ttl = ttl_seconds
        self._cache: dict[str, tuple[PromptResult, float]] = {}
        self._lock = Lock()

    def _make_key(self, user_input: str, template: str, context: Optional[dict]) -> str:
        data = f"{user_input}|{template}|{json.dumps(context or {}, sort_keys=True)}"
        return hashlib.md5(data.encode()).hexdigest()

    def get(self, user_input: str, template: str, context: Optional[dict] = None) -> Optional[PromptResult]:
        key = self._make_key(user_input, template, context)
        with self._lock:
            if key in self._cache:
                result, timestamp = self._cache[key]
                if time.time() - timestamp < self._ttl:
                    del self._cache[key]
                    self._cache[key] = (result, timestamp)
                    return result
                else:
                    del self._cache[key]
        return None

    def set(self, user_input: str, template: str, context: Optional[dict], result: PromptResult):
        key = self._make_key(user_input, template, context)
        with self._lock:
            if len(self._cache) >= self._max_entries:
                oldest_key = next(iter(self._cache))
                del self._cache[oldest_key]
            self._cache[key] = (result, time.time())

    def clear(self):
        with self._lock:
            self._cache.clear()

    def __len__(self) -> int:
        return len(self._cache)


class SmartCache:
    """LRU cache with variable TTL based on task type."""

    def __init__(self, max_entries: int = 1000, default_ttl: int = 3600):
        self._max_entries = max_entries
        self._default_ttl = default_ttl
        self._cache: dict[str, tuple[PromptResult, float, int]] = {}
        self._hits = 0
        self._misses = 0
        self._ttl_map = {
            "translation": 86400,
            "summarization": 7200,
            "code_generation": 1800,
            "code_review": 1800,
            "debugging": 900,
            "qa": 300,
            "explanation": 3600,
            "analysis": 3600,
            "comparison": 3600,
            "brainstorming": 600,
            "content_writing": 1800,
        }

    def _make_key(self, user_input: str, template: str, model: str, context: Optional[dict] = None) -> str:
        data = f"{user_input}|{template}|{model}|{json.dumps(context or {}, sort_keys=True)}"
        return hashlib.sha256(data.encode()).hexdigest()

    def get(self, user_input: str, template: str, model: str, context: Optional[dict] = None) -> Optional[PromptResult]:
        key = self._make_key(user_input, template, model, context)
        if key in self._cache:
            result, timestamp, ttl = self._cache[key]
            if time.time() - timestamp < ttl:
                self._hits += 1
                result.cached = True
                return result
            del self._cache[key]
        self._misses += 1
        return None

    def set(self, user_input: str, template: str, model: str, context: Optional[dict], result: PromptResult):
        key = self._make_key(user_input, template, model, context)
        if len(self._cache) >= self._max_entries:
            oldest_key = min(self._cache, key=lambda k: self._cache[k][1])
            del self._cache[oldest_key]
        ttl = self._ttl_map.get(template, self._default_ttl)
        self._cache[key] = (result, time.time(), ttl)

    def invalidate(self, template: Optional[str] = None):
        if template:
            keys = [k for k, (r, _, _) in self._cache.items() if r.template_id == template]
            for k in keys:
                del self._cache[k]
        else:
            self._cache.clear()

    def clear(self):
        self._cache.clear()

    @property
    def hit_rate(self) -> float:
        total = self._hits + self._misses
        return self._hits / total if total > 0 else 0.0

    @property
    def size(self) -> int:
        return len(self._cache)

    def __len__(self) -> int:
        return len(self._cache)


class RedisCache:
    """Distributed cache backed by Redis, falling back to in-process on failure.

    Uses the existing ``redis`` optional dependency (same as ``RedisRateLimiter``).
    Key format: ``brompt:cache:<SHA256 hash>`` with configurable TTL.
    """

    def __init__(self, redis_client, key_prefix: str = "brompt:cache:", default_ttl: int = 3600):
        self._redis = redis_client
        self._prefix = key_prefix
        self._default_ttl = default_ttl
        self._hits = 0
        self._misses = 0
        self._local: dict[str, tuple[PromptResult, float, int]] = {}

    def _make_key(self, user_input: str, template: str, model: str, context: Optional[dict] = None) -> str:
        data = f"{user_input}|{template}|{model}|{json.dumps(context or {}, sort_keys=True)}"
        return hashlib.sha256(data.encode()).hexdigest()

    def get(self, user_input: str, template: str, model: str, context: Optional[dict] = None) -> Optional[PromptResult]:
        key = self._make_key(user_input, template, model, context)
        try:
            raw = self._redis.get(f"{self._prefix}{key}")
            if raw is not None:
                data = json.loads(raw)
                if "timestamp" in data and isinstance(data["timestamp"], str):
                    data["timestamp"] = datetime.fromisoformat(data["timestamp"])
                result = PromptResult.from_dict(data)
                result.cached = True
                self._hits += 1
                return result
        except Exception:
            pass
        self._misses += 1
        return None

    def set(self, user_input: str, template: str, model: str, context: Optional[dict], result: PromptResult):
        key = self._make_key(user_input, template, model, context)
        try:
            self._redis.setex(
                f"{self._prefix}{key}",
                self._default_ttl,
                json.dumps(result.to_dict(), default=str),
            )
        except Exception:
            pass

    def clear(self):
        try:
            cursor = 0
            while True:
                cursor, keys = self._redis.scan(cursor, match=f"{self._prefix}*")
                if keys:
                    self._redis.delete(*keys)
                if cursor == 0:
                    break
        except Exception:
            pass

    @property
    def hit_rate(self) -> float:
        total = self._hits + self._misses
        return self._hits / total if total > 0 else 0.0

    @property
    def size(self) -> int:
        return len(self._local)

    def __len__(self) -> int:
        return len(self._local)


class PromptClient:
    def __init__(
        self,
        config: Optional[WidgetConfig] = None,
        enable_token_optimization: bool = True,
        enable_cache: bool = True,
        enable_auto_detect: bool = False,
        enable_streaming: bool = True,
        audit_log_path: Optional[str] = None,
    ):
        self.config = config or WidgetConfig()
        self._audit: Optional[AuditLog] = None
        if audit_log_path:
            self._audit = AuditLog(audit_log_path)
        errors = self.config.validate()
        if errors:
            raise ValueError("Invalid config:\n" + "\n".join(f"  - {e}" for e in errors))
        self._token_optimization_enabled = enable_token_optimization
        self._cache_enabled = enable_cache
        self._auto_detect_enabled = enable_auto_detect and AUTO_DETECT_AVAILABLE
        self._streaming_enabled = enable_streaming
        self._setup_logging()
        self._provider: LLMProvider = ProviderFactory.from_config(self.config.provider)
        logger.info(f"Provider: {self._provider.__class__.__name__} ({self.config.provider.model})")
        self._sessions = SessionManager(
            max_sessions=self.config.session.max_sessions,
            max_messages_per_session=self.config.session.max_messages_per_session,
            session_ttl_minutes=self.config.session.session_ttl_minutes,
            auto_cleanup=self.config.session.auto_cleanup,
        )
        self._router: Optional[ModelRouter] = None
        if self.config.routing.enabled:
            self._router = ModelRouter()

        if self._cache_enabled and self.config.cache.enabled:
            redis_url = self.config.cache.redis_url or os.getenv("BROMPT_REDIS_URL")
            self._cache = None
            if redis_url:
                try:
                    import redis as _redis_lib
                    rc = _redis_lib.from_url(redis_url, decode_responses=True)
                    self._cache = RedisCache(
                        rc, default_ttl=self.config.cache.ttl_seconds,
                    )
                    logger.info("Redis cache initialised at %s", redis_url)
                except Exception as exc:
                    logger.warning("Redis unavailable, falling back to in-process cache: %s", exc)
                    self._cache = None
            if self._cache is None:
                if hasattr(self.config.cache, 'strategy') and self.config.cache.strategy == "smart":
                    self._cache = SmartCache(
                        max_entries=self.config.cache.max_entries,
                        default_ttl=self.config.cache.ttl_seconds,
                    )
                else:
                    self._cache = LRUCache(
                        max_entries=self.config.cache.max_entries,
                        ttl_seconds=self.config.cache.ttl_seconds,
                    )
        else:
            self._cache = None
        self._feedback = None
        if self.config.feedback.enabled and FEEDBACK_AVAILABLE:
            self._feedback = FeedbackLoop(storage_path=self.config.feedback.storage_path)
            logger.info("Feedback system initialised")
        elif self.config.feedback.enabled and not FEEDBACK_AVAILABLE:
            logger.warning("Feedback system unavailable — install brompt[feedback]")
        self._optimizer = TokenOptimizer() if self._token_optimization_enabled else None
        self._detector = None
        self._is_first_message = True
        self._total_saved_tokens = 0
        self._last_savings = {}
        self._stats = {"total_prompts": 0, "total_tokens": 0, "total_latency_ms": 0.0, "total_cost": 0.0, "errors": 0}
        self._event_handlers = {
            "before_prompt": [],
            "after_prompt": [],
            "on_error": [],
            "on_cache_hit": [],
            "on_auto_detect": [],
        }
        logger.info(f"PromptClient initialised — model: {self.config.provider.model}")

    def _setup_logging(self):
        logging.basicConfig(
            level=getattr(logging, self.config.logging.level.value),
            format=self.config.logging.format,
            filename=self.config.logging.file_path,
        )

    async def prompt(
        self,
        user_input: str,
        template: Optional[str] = None,
        session_id: Optional[str] = None,
        context: Optional[dict] = None,
        system_prompt: Optional[str] = None,
        **generation_kwargs,
    ) -> PromptResult:
        if not user_input or not user_input.strip():
            raise ValueError("user_input cannot be empty")
        template = template or self.config.default_template
        start_time = time.time()
        detection = None
        try:
            # Auto-detect task type if enabled
            if self._auto_detect_enabled:
                if self._detector is None:
                    try:
                        from auto_detect import auto_detect_agent
                        self._detector = auto_detect_agent
                    except ImportError:
                        self._auto_detect_enabled = False
                if self._detector:
                    detection = self._detector.detect(user_input)
                    if not template:
                        template = getattr(detection, 'suggested_template', None) or template
                    self._emit("on_auto_detect", detection)

            # Cache check
            cached = None
            if self._cache:
                if isinstance(self._cache, (SmartCache, RedisCache)):
                    cached = self._cache.get(user_input, template, self.config.provider.model, context)
                else:
                    cached = self._cache.get(user_input, template, context)
                if cached:
                    logger.debug(f"Cache hit: {template}")
                    self._emit("on_cache_hit", cached)
                    return cached

            session = None
            conversation_context = []
            if session_id:
                session = self._sessions.get_session(session_id)
                if session is None:
                    logger.warning(f"Session not found: {session_id}, creating new")
                    session = self._sessions.create_session(template_id=template)
                    session_id = session.id
                else:
                    conversation_context = session.get_context(
                        last_n=self.config.session.context_window_size,
                    )

            self._emit("before_prompt", {"input": user_input, "template": template})

            generated_prompt = self._build_prompt(
                user_input=user_input, template=template, context=context,
                conversation_context=conversation_context, system_prompt=system_prompt,
            )
            savings = self._last_savings
            self._total_saved_tokens += savings.get("saved_tokens", 0)
            gen_params = {
                "temperature": self.config.generation.temperature,
                "max_tokens": self.config.generation.max_tokens,
                "top_p": self.config.generation.top_p,
                "frequency_penalty": self.config.generation.frequency_penalty,
                "presence_penalty": self.config.generation.presence_penalty,
                "stop_sequences": self.config.generation.stop_sequences,
                **generation_kwargs,
            }
            provider_result = await self._provider.generate(generated_prompt, **gen_params)
            latency_ms = (time.time() - start_time) * 1000
            prompt_tokens = provider_result.prompt_tokens or len(generated_prompt) // 4
            completion_tokens = provider_result.completion_tokens or provider_result.tokens_used
            plain_prompt_tokens = len(user_input) // 4
            cost = estimate_cost(self._provider.__class__.__name__, prompt_tokens, completion_tokens)
            plain_cost = estimate_cost(self._provider.__class__.__name__, plain_prompt_tokens, completion_tokens)
            result = PromptResult(
                user_input=user_input,
                generated_prompt=generated_prompt,
                response=provider_result.text,
                template_id=template,
                model=provider_result.model,
                session_id=session_id,
                tokens_used=provider_result.tokens_used,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                plain_prompt_tokens=plain_prompt_tokens,
                cost=cost,
                plain_cost=plain_cost,
                latency_ms=latency_ms,
                finish_reason=provider_result.finish_reason,
                tokens_saved=savings.get("saved_tokens", 0),
                cost_saved=savings.get("cost_saved", 0),
                savings_percent=savings.get("savings_percent", 0),
                auto_detected=detection is not None,
                detected_task=_task_type_str(getattr(detection, 'task_type', None)) if detection else None,
                detection_confidence=getattr(detection, 'confidence', 0.0) if detection else 0.0,
                cached=False,
                metadata={
                    "provider_outcome": provider_result.outcome.value,
                    "conversation_turns": len(conversation_context),
                    "saved_tokens": savings.get("saved_tokens", 0),
                    "savings_percent": round(savings.get("savings_percent", 0), 1),
                },
            )
            if session:
                session.add_message("user", user_input, tokens_used=0)
                session.add_message(
                    "assistant", provider_result.text,
                    tokens_used=provider_result.tokens_used, latency_ms=latency_ms,
                    metadata={"cost": cost, "prompt_tokens": prompt_tokens,
                              "completion_tokens": completion_tokens},
                )
            if self._cache and provider_result.is_success:
                if isinstance(self._cache, (SmartCache, RedisCache)):
                    self._cache.set(user_input, template, self.config.provider.model, context, result)
                else:
                    self._cache.set(user_input, template, context, result)
            self._stats["total_prompts"] += 1
            self._stats["total_tokens"] += provider_result.tokens_used
            self._stats["total_latency_ms"] += latency_ms
            self._stats["total_cost"] += cost
            self._stats.setdefault("total_plain_cost", 0.0)
            self._stats["total_plain_cost"] += plain_cost
            if not provider_result.is_success:
                self._stats["errors"] += 1
            overhead = cost - plain_cost
            saved = savings.get("saved_tokens", 0)
            spct = savings.get("savings_percent", 0)
            self._emit("after_prompt", result)
            logger.info(
                f"Executed: {template} | "
                f"cost=${cost:.6f} (prompt=${plain_cost:.6f}+overhead=${overhead:.6f}) | "
                f"tokens={prompt_tokens}in/{completion_tokens}out | "
                f"saved={saved}tok({spct:.0f}%) | {latency_ms:.0f}ms"
            )
            return result
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            self._stats["errors"] += 1
            self._emit("on_error", {"error": e, "user_input": user_input})
            logger.error(f"Execution failed: {e}")
            raise RuntimeError(f"Model call failed: {e}") from e

    async def prompt_stream(
        self,
        user_input: str,
        template: Optional[str] = None,
        session_id: Optional[str] = None,
        system_prompt: Optional[str] = None,
        context: Optional[dict] = None,
        **generation_kwargs,
    ) -> AsyncIterator[str]:
        if not self._streaming_enabled:
            raise RuntimeError("Streaming is not enabled")
        template = template or self.config.default_template
        generated_prompt = self._build_prompt(
            user_input, template, context=context, system_prompt=system_prompt,
        )
        full_response = []
        async for chunk in self._provider.stream(generated_prompt, **generation_kwargs):
            full_response.append(chunk)
            yield chunk
        if session_id:
            session = self._sessions.get_session(session_id)
            if session:
                session.add_message("user", user_input)
                session.add_message("assistant", "".join(full_response))

    def create_session(
        self, template_id: Optional[str] = None, system_prompt: Optional[str] = None, **metadata,
    ) -> Session:
        return self._sessions.create_session(
            template_id=template_id, system_prompt=system_prompt, **metadata,
        )

    def get_session(self, session_id: str) -> Optional[Session]:
        return self._sessions.get_session(session_id)

    def list_sessions(self) -> list[dict]:
        return self._sessions.list_sessions()

    def delete_session(self, session_id: str) -> bool:
        return self._sessions.delete_session(session_id)

    def record_feedback(
        self, result: PromptResult, rating: Optional[int] = None, outcome: str = "success",
    ):
        if not self._feedback:
            logger.warning("Feedback system not enabled")
            return
        from .feedback import PromptOutcome as PO
        outcome_map = {
            "success": PO.SUCCESS, "partial": PO.PARTIAL,
            "hallucination": PO.HALLUCINATION, "irrelevant": PO.IRRELEVANT, "error": PO.ERROR,
        }
        self._feedback.record_execution(
            template_id=result.template_id,
            generated_prompt=result.generated_prompt,
            model_response=result.response,
            outcome=outcome_map.get(outcome, PO.SUCCESS),
            latency_ms=result.latency_ms, tokens_used=result.tokens_used,
            user_feedback=rating, model_name=result.model,
        )
        logger.info(f"Feedback recorded: {result.template_id} -> {outcome}")

    def get_best_template(self) -> Optional[str]:
        if self._feedback:
            return self._feedback.get_best_template()
        return None

    def on(self, event: str, handler):
        """Register an event handler."""
        if event in self._event_handlers:
            self._event_handlers[event].append(handler)

    def _emit(self, event: str, data):
        """Emit an event to all registered handlers."""
        for handler in self._event_handlers.get(event, []):
            try:
                handler(data)
            except Exception as e:
                logger.error(f"Event handler error ({event}): {e}")

    def reset_conversation(self):
        self._is_first_message = True

    def get_analytics(self) -> dict:
        cache_hit_rate = 0.0
        if self._cache:
            if hasattr(self._cache, 'hit_rate'):
                cache_hit_rate = self._cache.hit_rate
        report = {
            "stats": self._stats,
            "avg_latency_ms": (
                self._stats["total_latency_ms"] / self._stats["total_prompts"]
                if self._stats["total_prompts"] > 0 else 0
            ),
            "total_cost": round(self._stats["total_cost"], 6),
            "total_plain_cost": round(self._stats.get("total_plain_cost", 0.0), 6),
            "overhead_pct": (
                round((self._stats["total_cost"] - self._stats.get("total_plain_cost", 0.0))
                      / self._stats["total_cost"] * 100, 1)
                if self._stats["total_cost"] > 0 else 0.0
            ),
            "total_saved_tokens": self._total_saved_tokens,
            "active_sessions": self._sessions.get_total_sessions(),
            "cache_entries": len(self._cache) if self._cache else 0,
            "cache_hit_rate": round(cache_hit_rate, 4),
        }
        if self._feedback:
            report["feedback"] = self._feedback.get_performance_report()
        return report

    def replay(self, entry_hash: str, model: Optional[str] = None, system_prompt: Optional[str] = None) -> dict:
        """Re-run a previous audit entry on a (possibly different) model.

        Requires ``audit_log_path`` to have been passed at construction.

        Parameters
        ----------
        entry_hash :
            The ``entry_hash`` of the audit entry to replay.
        model :
            Model name for the re-run (e.g. ``"gpt-4o"``).
            Defaults to the current provider's model.
        system_prompt :
            Optional system prompt forwarded to the provider.

        Returns
        -------
        A dict with keys ``original`` (audit entry) and ``replayed``
        (:class:`PromptResult`) for comparison.
        """
        if self._audit is None:
            raise RuntimeError("Replay requires audit_log_path to be set at construction")

        provider = self._provider
        if model and model != self.config.provider.model:
            cfg = ProviderConfig(type=self.config.provider.type, model=model)
            provider = ProviderFactory.from_config(cfg)

        result = self._audit.replay(entry_hash, provider, system=system_prompt)
        if "replayed" in result:
            pr = result["replayed"]
            from .providers_core import ProviderResult
            if isinstance(pr, ProviderResult):
                result["replayed"] = {"text": pr.text, "model": pr.model}
        return result

    def _build_prompt(
        self, user_input: str, template: str, context: Optional[dict] = None,
        conversation_context: Optional[list] = None, system_prompt: Optional[str] = None,
    ) -> str:
        template_content = self._apply_template(template, user_input, context)
        if context:
            template_content += "\n\n" + json.dumps(context, ensure_ascii=False, indent=2)

        if self._token_optimization_enabled and self._optimizer:
            optimized, savings = self._optimizer.build_optimized_prompt(
                system_prompt=system_prompt or "",
                user_input=user_input,
                template_content=template_content,
                messages_history=conversation_context,
                is_first_message=self._is_first_message,
            )
        else:
            parts = []
            if system_prompt and self._is_first_message:
                parts.append(system_prompt)
            parts.append(template_content)
            optimized = "\n\n".join(p for p in parts if p)
            savings = {"saved_tokens": 0, "savings_percent": 0, "cost_saved": 0}
        self._is_first_message = False
        self._last_savings = savings
        return optimized

    def _get_system_prompt(self, template: str) -> str:
        try:
            from templates import get_system_prompt
            return get_system_prompt(template)
        except ImportError:
            return ""

    def _apply_template(self, template_id: str, user_input: str, context: Optional[dict] = None) -> str:
        try:
            from templates import format_prompt
            return format_prompt(template_id, user_input)
        except ImportError:
            pass
        builtin_templates = {
            "default": "Process the following input and provide the best possible response.",
            "code": "You are an expert programmer. Write code based on the request below. Provide clear explanation.",
            "article": "You are a professional writer. Write a comprehensive article about the following topic.",
            "analysis": "Analyse the following input in depth. Provide clear insights and conclusions.",
            "summary": "Summarise the following input. Focus only on the key points.",
        }
        return builtin_templates.get(template_id, builtin_templates["default"])

    def __repr__(self) -> str:
        cache_hit = self._cache.hit_rate if hasattr(self._cache, 'hit_rate') and self._cache else 0
        return (
            f"PromptClient(model='{self.config.provider.model}', "
            f"sessions={self._sessions.get_total_sessions()}, "
            f"cache={len(self._cache) if self._cache else 0}, "
            f"saved_tokens={self._total_saved_tokens}, "
            f"opt={self._token_optimization_enabled})"
        )


# ---------------------------------------------------------------------------
# Backward-compatible alias
# ---------------------------------------------------------------------------
BromptWidget = PromptClient
