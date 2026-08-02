"""Unified entry point for the Brompt library."""

import hashlib
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from threading import Lock
from typing import AsyncIterator, Optional

from .agents import MedicAgent, WardenAgent
from .audit import AuditLog
from .config import BudgetConfig, ComplianceConfig, PolicyConfig, ProviderConfig, WidgetConfig
from .optimizer import TokenOptimizer
from .policy import PolicyEngine, PolicyRule, PolicyViolationError
from .pricing import _normalize_provider, estimate_cost
from .providers import LLMProvider, ProviderFactory
from .router import ModelRouter
from .security import SecurityEngine, SecurityViolationError
from .session import Session, SessionManager

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


class ComplianceError(Exception):
    """Base class for all compliance-related errors."""


class TamperDetectedError(ComplianceError):
    """Raised when the audit chain or a recorded entry has been tampered with."""


class BudgetExceededError(ComplianceError):
    """Raised when a request would exceed the configured cost budget."""


class HumanApprovalRequired(ComplianceError):  # noqa: N818 - documented public API name
    """Raised when a request requires human approval (human-in-the-loop)."""


def _task_type_str(task_type) -> Optional[str]:
    """Convert a TaskType enum (or string) to its string value."""
    if task_type is None:
        return None
    if hasattr(task_type, 'value'):
        return task_type.value
    return str(task_type)

logger = logging.getLogger(__name__)

# Map normalized provider families onto ModelRouter's default profile names.
_ROUTER_PROFILE_NAMES = {
    "gemini": "google",
}


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
    execution_id: Optional[str] = None
    audit_hash: Optional[str] = None
    audit_chain_id: Optional[str] = None
    tamper_check: Optional[bool] = None
    policy_id: Optional[str] = None
    compliance_mode: Optional[str] = None
    data_residency: Optional[str] = None
    needs_approval: bool = False
    approval_id: Optional[str] = None
    error_message: Optional[str] = None
    signed_at: Optional[datetime] = None
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
            "execution_id": self.execution_id,
            "audit_hash": self.audit_hash,
            "audit_chain_id": self.audit_chain_id,
            "tamper_check": self.tamper_check,
            "policy_id": self.policy_id,
            "compliance_mode": self.compliance_mode,
            "data_residency": self.data_residency,
            "needs_approval": self.needs_approval,
            "approval_id": self.approval_id,
            "error_message": self.error_message,
            "signed_at": self.signed_at.isoformat() if self.signed_at else None,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
        }

    def to_audit_dict(self) -> dict:
        """Audit-relevant subset for external attestation/receipts."""
        return {
            "execution_id": self.execution_id,
            "audit_hash": self.audit_hash,
            "audit_chain_id": self.audit_chain_id,
            "tamper_check": self.tamper_check,
            "policy_id": self.policy_id,
            "compliance_mode": self.compliance_mode,
            "data_residency": self.data_residency,
            "needs_approval": self.needs_approval,
            "approval_id": self.approval_id,
            "model": self.model,
            "tokens_used": self.tokens_used,
            "cost": round(self.cost, 6),
            "signed_at": self.signed_at.isoformat() if self.signed_at else None,
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


@dataclass
class SignedExecutionResult(PromptResult):
    """A :class:`PromptResult` that carries audit proof.

    Produced by :class:`CompliantPromptClient` — same fields as
    ``PromptResult`` plus the ``audit_hash`` / ``audit_chain_id`` /
    ``tamper_check`` / ``signed_at`` proof stamped by ``_attach_proof``.
    """

    @property
    def verified(self) -> bool:
        """``True`` when the proof is present and the chain verified clean."""
        return self.tamper_check is True

    @property
    def receipt(self) -> Optional[str]:
        """Alias for the audit hash, for receipt-style callers."""
        return self.audit_hash


class LRUCache:
    def __init__(self, max_entries: int = 1000, ttl_seconds: int = 3600):
        self._max_entries = max_entries
        self._ttl = ttl_seconds
        self._cache: dict[str, tuple[PromptResult, float]] = {}
        self._lock = Lock()

    def _make_key(self, user_input: str, template: str, context: Optional[dict]) -> str:
        data = f"{user_input}|{template}|{json.dumps(context or {}, sort_keys=True)}"
        return hashlib.md5(data.encode(), usedforsecurity=False).hexdigest()

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
        audit_secret_key: Optional[str] = None,
        compliance: Optional[ComplianceConfig] = None,
        enable_pii_scan: bool = True,
    ):
        self.config = config or WidgetConfig()
        self._compliance = compliance or self.config.compliance
        self._audit: Optional[AuditLog] = None
        # Output-side PII scan (credit cards, SSN, email, phone, system-prompt
        # leaks) via WardenAgent/MedicAgent in agents.py. Independent of
        # SecurityEngine.redact_with_metadata, which only covers secrets/keys.
        self._pii_scan_enabled = enable_pii_scan
        self._warden = WardenAgent() if enable_pii_scan else None
        self._medic = MedicAgent() if enable_pii_scan else None
        self._audit_key = (
            audit_secret_key
            or self._compliance.signing_key
            or os.getenv("BROMPT_AUDIT_SECRET")
        )
        if audit_log_path:
            self._audit = AuditLog(audit_log_path, secret_key=self._audit_key)
        elif self._compliance.enabled:
            self._audit = AuditLog("brompt_audit.log", secret_key=self._audit_key)

        self._policy: Optional[PolicyEngine] = None
        if self._compliance.enabled and (
            self._compliance.policy_rules or self._compliance.policy_path
        ):
            rules = list(self._compliance.policy_rules)
            if self._compliance.policy_path:
                import yaml
                with open(self._compliance.policy_path) as _f:
                    _data = yaml.safe_load(_f) or {}
                rules += _data.get("security_policy", {}).get("rules", [])
            self._policy = PolicyEngine(rules=[PolicyRule.from_dict(r) for r in rules])

        self._budget = self._compliance.budget if self._compliance.enabled else None
        self._pending_approvals: dict[str, dict] = {}
        self._air_gapped = self._compliance.enabled and self._compliance.mode == "air_gapped"

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
            router_name = _ROUTER_PROFILE_NAMES.get(
                _normalize_provider(self._provider.__class__.__name__),
                _normalize_provider(self._provider.__class__.__name__),
            )
            self._router.register_provider(router_name, self._provider)

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
        caller_id: str = "default",
        _skip_approval: bool = False,
        **generation_kwargs,
    ) -> PromptResult:
        if not user_input or not user_input.strip():
            raise ValueError("user_input cannot be empty")
        template = template or self.config.default_template
        start_time = time.time()
        execution_id = uuid.uuid4().hex[:16]
        try:
            user_input = SecurityEngine.sanitize(user_input)
        except SecurityViolationError as exc:
            self._record_event("security_denied", execution_id, False, user_input, detail=str(exc))
            self._stats["errors"] += 1
            raise

        if self._policy is not None:
            try:
                self._policy.check(caller_id)
            except PolicyViolationError as exc:
                self._record_event("policy_denied", execution_id, False, user_input, detail=str(exc))
                raise

        if self._air_gapped:
            try:
                self._verify_air_gapped()
            except RuntimeError as exc:
                self._record_event("air_gapped_violation", execution_id, False, user_input, detail=str(exc))
                raise

        if self._budget is not None and self._budget.enabled:
            self._check_budget_preflight(user_input)

        if not _skip_approval and self._is_sensitive(user_input):
            pending = self._request_human_approval(
                user_input, template, session_id, context, system_prompt,
                caller_id, execution_id, generation_kwargs,
            )
            if self._compliance.human_review_action == "raise":
                raise HumanApprovalRequired(
                    f"Human approval required (ID: {pending.approval_id})"
                )
            return pending

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
            provider_result.text = await self._sanitize_output(provider_result.text)
            latency_ms = (time.time() - start_time) * 1000
            prompt_tokens = provider_result.prompt_tokens or len(generated_prompt) // 4
            completion_tokens = provider_result.completion_tokens or provider_result.tokens_used
            plain_prompt_tokens = len(user_input) // 4
            cost = estimate_cost(self._provider.__class__.__name__, prompt_tokens, completion_tokens)
            plain_cost = estimate_cost(self._provider.__class__.__name__, plain_prompt_tokens, completion_tokens)
            result = self._make_result(
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
            result.execution_id = execution_id
            result.compliance_mode = self._compliance.mode
            result.data_residency = self._compliance.data_residency
            if self._policy is not None:
                result.policy_id = caller_id
            self._attach_proof(
                result, execution_id,
                "execute" if provider_result.is_success else "provider_error",
                latency_ms, provider_result.tokens_used, generated_prompt, cost,
                is_secure=provider_result.is_success,
            )
            if self._budget is not None and self._budget.enabled:
                self._update_budget(cost, execution_id, generated_prompt)
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
            self._record_event("provider_error", execution_id, False, user_input, detail=str(e))
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
        caller_id: str = "default",
        **generation_kwargs,
    ) -> AsyncIterator[str]:
        if not self._streaming_enabled:
            raise RuntimeError("Streaming is not enabled")
        template = template or self.config.default_template
        execution_id = uuid.uuid4().hex[:16]
        try:
            user_input = SecurityEngine.sanitize(user_input)
        except SecurityViolationError as exc:
            self._record_event("security_denied", execution_id, False, user_input, detail=str(exc))
            raise
        if self._policy is not None:
            self._policy.check(caller_id)
        generated_prompt = self._build_prompt(
            user_input, template, context=context, system_prompt=system_prompt,
        )
        full_response = []
        async for chunk in self._provider.stream(generated_prompt, **generation_kwargs):
            full_response.append(chunk)
            yield chunk
        redacted_response = await self._sanitize_output("".join(full_response))
        self._record_event("stream", execution_id, True, generated_prompt,
                           detail=redacted_response)
        if session_id:
            session = self._sessions.get_session(session_id)
            if session:
                session.add_message("user", user_input)
                session.add_message("assistant", redacted_response)

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
        from .feedback import PromptOutcome
        outcome_map = {
            "success": PromptOutcome.SUCCESS, "partial": PromptOutcome.PARTIAL,
            "hallucination": PromptOutcome.HALLUCINATION,
            "irrelevant": PromptOutcome.IRRELEVANT, "error": PromptOutcome.ERROR,
        }
        self._feedback.record_execution(
            template_id=result.template_id,
            generated_prompt=result.generated_prompt,
            model_response=result.response,
            outcome=outcome_map.get(outcome, PromptOutcome.SUCCESS),
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

    async def replay(
        self,
        execution_id: str,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        caller_id: str = "default",
    ) -> PromptResult:
        """Re-run a previously recorded execution from the audit trail.

        Verifies the whole chain and the specific entry first; raises
        :class:`TamperDetectedError` if either fails. The re-run is itself
        recorded as a new chained entry with its own proof fields.

        Parameters
        ----------
        execution_id :
            The ``PromptResult.execution_id`` (or audit ``state_id``) to replay.
        model :
            Model for the re-run (e.g. ``"gpt-4o"``). Defaults to the
            current provider's model — use a different one to detect drift.
        system_prompt :
            Optional system prompt forwarded to the provider.
        caller_id :
            Identity attributed to the replay in policy checks and audit.
        """
        if self._audit is None:
            raise RuntimeError("Replay requires an audit log (pass audit_log_path= or enable compliance)")
        if not self._audit.verify():
            raise TamperDetectedError("Audit chain integrity compromised")
        entry = self._audit.find_by_state(execution_id)
        if entry is None:
            raise KeyError(f"No audit entry for execution: {execution_id}")
        entry_hash = entry.get("entry_hash")
        if not isinstance(entry_hash, str):
            raise KeyError(f"Audit entry {execution_id} has no entry_hash")
        if not self._audit.verify_entry(entry_hash):
            raise TamperDetectedError(f"Audit entry {execution_id} has been tampered")

        if self._policy is not None:
            self._policy.check(caller_id)

        provider = self._provider
        if model and model != self.config.provider.model:
            cfg = ProviderConfig(type=self.config.provider.type, model=model)
            provider = ProviderFactory.from_config(cfg)

        msgs = entry.get("messages") or [{"role": "user", "content": entry.get("detail") or ""}]
        prompt_text = "\n".join(
            m.get("content", "") for m in msgs if m.get("role") != "system"
        ) or (msgs[0].get("content", "") if msgs else "")

        start_time = time.time()
        provider_result = await provider.generate(prompt_text, system=system_prompt)
        provider_result.text = await self._sanitize_output(provider_result.text)
        latency_ms = (time.time() - start_time) * 1000
        new_execution_id = uuid.uuid4().hex[:16]
        result = self._make_result(
            user_input=prompt_text,
            generated_prompt=prompt_text,
            response=provider_result.text,
            template_id="replay",
            model=provider_result.model,
            execution_id=new_execution_id,
            tokens_used=provider_result.tokens_used,
            prompt_tokens=provider_result.prompt_tokens or len(prompt_text) // 4,
            completion_tokens=provider_result.completion_tokens or provider_result.tokens_used,
            plain_prompt_tokens=len(prompt_text) // 4,
            latency_ms=latency_ms,
            finish_reason=provider_result.finish_reason,
            cached=False,
            compliance_mode=self._compliance.mode,
        )
        if self._policy is not None:
            result.policy_id = caller_id
        result.data_residency = self._compliance.data_residency
        self._attach_proof(result, new_execution_id, "replay", latency_ms,
                           provider_result.tokens_used, prompt_text, 0.0)
        return result

    def verify_execution(self, result) -> bool:
        """Return ``True`` when the whole audit chain is intact AND the
        specific entry behind *result* verifies (hash + optional HMAC)."""
        if self._audit is None or result is None or result.audit_hash is None:
            return False
        return self._audit.verify() and self._audit.verify_entry(result.audit_hash)

    def export_audit_trail(self) -> list[dict]:
        """Export the full audit trail for external review."""
        if self._audit is None:
            return []
        exported = []
        for e in self._audit.read_all():
            entry_hash = e.get("entry_hash")
            exported.append({
                "id": entry_hash,
                "state_id": e.get("state_id"),
                "event": e.get("event"),
                "timestamp": e.get("timestamp"),
                "prev_hash": e.get("prev_hash"),
                "signed": self._audit.is_signed,
                "chain_verified": self._audit.verify_entry(entry_hash)
                if isinstance(entry_hash, str) else False,
            })
        return exported

    def get_compliance_report(self) -> dict:
        """High-level compliance snapshot for dashboards / external auditors."""
        return {
            "compliance_enabled": self._compliance.enabled,
            "mode": self._compliance.mode,
            "data_residency": self._compliance.data_residency or "global",
            "chain_integrity": self._audit.verify() if self._audit else None,
            "signed_entries": self._audit.is_signed if self._audit else False,
            "total_entries": len(self._audit.read_all()) if self._audit else 0,
            "budget": self._budget.to_dict() if self._budget is not None else None,
            "pending_approvals": len(self._pending_approvals),
            "policy_rules": len(self._compliance.policy_rules),
            "human_review_action": self._compliance.human_review_action,
        }

    async def approve(self, approval_id: str, approver: str = "admin") -> PromptResult:
        """Approve a pending sensitive request and execute it.

        The approval itself is recorded in the audit trail before the
        original request is re-run.
        """
        if approval_id not in self._pending_approvals:
            raise ValueError(f"Approval {approval_id} not found")
        pending = self._pending_approvals.pop(approval_id)
        self._record_event("human_approved", uuid.uuid4().hex[:16], True,
                           pending["message"], detail=f"approver={approver}")
        return await self.prompt(
            pending["message"],
            template=pending.get("template"),
            session_id=pending.get("session_id"),
            context=pending.get("context"),
            system_prompt=pending.get("system_prompt"),
            caller_id=pending.get("caller_id", "default"),
            _skip_approval=True,
            **pending.get("generation_kwargs", {}),
        )

    def reject(self, approval_id: str, reason: str = "") -> None:
        """Reject a pending sensitive request and record the rejection."""
        pending = self._pending_approvals.pop(approval_id, None)
        self._record_event("human_rejected", uuid.uuid4().hex[:16], False,
                           pending["message"] if pending else "",
                           detail=f"reason={reason or 'no reason given'}")

    # -- compliance helpers ------------------------------------------------

    async def _sanitize_output(self, text: str) -> str:
        """Redact secrets and PII from provider output and record what was hidden.

        Two independent layers, each recorded separately so the audit trail
        shows exactly why a redaction happened:
        1. SecurityEngine.redact_with_metadata — secrets/API keys/tokens.
        2. WardenAgent + MedicAgent (agents.py) — PII (credit cards, SSN,
           email, phone) and system-prompt leaks, which SecurityEngine's
           output patterns intentionally do not cover.

        Async because the PII layer (step 2) is async; all call sites are
        already inside ``prompt()``/``prompt_stream()``/``replay()``, which
        are async, so this is a plain ``await``, not a new event loop.
        """
        redacted, redactions = SecurityEngine.redact_with_metadata(text)
        if redactions and self._audit is not None:
            self._audit.record(
                "output_redacted", uuid.uuid4().hex[:16], True,
                detail=", ".join(redactions),
            )

        if self._pii_scan_enabled and redacted:
            healed, concerns = await self._pii_heal_async(redacted)
            if concerns and self._audit is not None:
                self._audit.record(
                    "pii_redacted", uuid.uuid4().hex[:16], True,
                    detail=", ".join(concerns),
                )
            redacted = healed

        return redacted

    async def _pii_heal_async(self, text: str) -> tuple[str, list]:
        """Run WardenAgent (detect) + MedicAgent (targeted heal) on *text*.

        Returns ``(healed_text, concerns)``. Mirrors
        ``BromptEngine._pii_heal_async`` in core/engine.py so the CLI/API and
        widget paths behave identically.
        """
        if not text:
            return text, []
        event = await self._warden.analyze(text)
        concerns = event.metadata.get("concerns", [])
        if not concerns:
            return text, []
        healed = await self._medic.act(event, text)
        return healed, concerns

    def _record_event(self, event: str, state_id: str, is_secure: bool,
                      content: str, detail: Optional[str] = None,
                      latency_ms: Optional[float] = None,
                      tokens_used: int = 0) -> Optional[str]:
        """Record an audit entry and return its ``entry_hash`` (or ``None``)."""
        if self._audit is None:
            return None
        record = self._audit.record(
            event, state_id, is_secure, detail=detail,
            latency_ms=latency_ms, tokens_used=tokens_used,
            messages=[{"role": "user", "content": content}],
        )
        return record.get("entry_hash")

    def _attach_proof(self, result: PromptResult, execution_id: str, event: str,
                      latency_ms: float, tokens_used: int, content: str,
                      cost: float, is_secure: bool = True) -> None:
        """Record the execution in the audit trail and stamp proof onto *result*."""
        entry_hash = self._record_event(
            event, execution_id, is_secure, content,
            latency_ms=latency_ms, tokens_used=tokens_used,
        )
        if entry_hash is None:
            return
        entry = self._audit.find_entry(entry_hash)
        result.audit_hash = entry_hash
        result.audit_chain_id = entry.get("prev_hash") if entry else None
        result.tamper_check = self._audit.verify()
        result.signed_at = datetime.now()

    def _is_sensitive(self, text: str) -> bool:
        if not self._compliance.human_review_patterns:
            return False
        lowered = text.lower()
        return any(p.lower() in lowered for p in self._compliance.human_review_patterns)

    def _request_human_approval(
        self, user_input: str, template: Optional[str], session_id: Optional[str],
        context: Optional[dict], system_prompt: Optional[str], caller_id: str,
        execution_id: str, generation_kwargs: dict,
    ) -> PromptResult:
        approval_id = hashlib.sha256(
            f"{execution_id}:{user_input}".encode()
        ).hexdigest()[:16]
        self._pending_approvals[approval_id] = {
            "message": user_input,
            "template": template,
            "session_id": session_id,
            "context": context,
            "system_prompt": system_prompt,
            "caller_id": caller_id,
            "generation_kwargs": generation_kwargs,
        }
        self._record_event("human_approval_required", execution_id, False,
                           user_input, detail=f"approval_id={approval_id}")
        return self._make_result(
            user_input=user_input,
            generated_prompt="",
            response="",
            template_id=template or self.config.default_template,
            model=self.config.provider.model,
            execution_id=execution_id,
            cached=False,
            needs_approval=True,
            approval_id=approval_id,
            error_message=f"Human approval required (ID: {approval_id})",
            compliance_mode=self._compliance.mode,
            data_residency=self._compliance.data_residency,
        )

    def _check_budget_preflight(self, user_input: str) -> None:
        if self._budget.daily_spent >= self._budget.max_daily_cost:
            self._record_event("budget_exceeded", uuid.uuid4().hex[:16], False,
                               user_input,
                               detail=f"daily_spent={self._budget.daily_spent:.4f}")
            raise BudgetExceededError(
                f"Daily budget exceeded: ${self._budget.daily_spent:.4f} >= ${self._budget.max_daily_cost}"
            )
        estimate = estimate_cost(
            self._provider.__class__.__name__,
            len(user_input) // 4, self.config.generation.max_tokens,
        )
        if estimate > self._budget.max_per_request:
            self._record_event("budget_exceeded", uuid.uuid4().hex[:16], False,
                               user_input, detail=f"estimate={estimate:.4f}")
            raise BudgetExceededError(
                f"Request exceeds per-request budget: est ${estimate:.4f} > ${self._budget.max_per_request}"
            )

    def _update_budget(self, cost: float, execution_id: str, content: str) -> None:
        self._budget.add_cost(cost)
        if self._budget.get_alert_level() == "warning":
            self._record_event(
                "budget_warning", execution_id, True, content,
                detail=f"daily_spent={self._budget.daily_spent:.4f}",
            )

    def _verify_air_gapped(self) -> None:
        """Best-effort air-gap check: raise if the network appears reachable."""
        try:
            import socket
            socket.create_connection(("8.8.8.8", 53), timeout=1)
        except OSError:
            return  # no connectivity — expected
        raise RuntimeError(
            "Air-gapped mode violated: outbound network access detected"
        )

    @property
    def audit_log(self) -> Optional[AuditLog]:
        """The bound audit log (``None`` when compliance is disabled)."""
        return self._audit

    @property
    def _daily_spent(self) -> float:
        """Backward-compatible accessor for the in-process budget ledger."""
        return self._budget.daily_spent if self._budget is not None else 0.0

    @_daily_spent.setter
    def _daily_spent(self, value: float) -> None:
        if self._budget is not None:
            self._budget.daily_spent = value

    @property
    def _request_count(self) -> int:
        """Backward-compatible accessor for the in-process request counter."""
        return self._budget.request_count if self._budget is not None else 0

    @_request_count.setter
    def _request_count(self, value: int) -> None:
        if self._budget is not None:
            self._budget.request_count = value

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

    def _make_result(self, **kwargs) -> PromptResult:
        """Construct the result object for this client.

        Subclasses may override to return a richer result type (e.g.
        :class:`SignedExecutionResult`).
        """
        return PromptResult(**kwargs)

    def __repr__(self) -> str:
        return (
            f"PromptClient(model='{self.config.provider.model}', "
            f"sessions={self._sessions.get_total_sessions()}, "
            f"cache={len(self._cache) if self._cache else 0}, "
            f"saved_tokens={self._total_saved_tokens}, "
            f"opt={self._token_optimization_enabled})"
        )


class CompliantPromptClient(PromptClient):
    """Policy-driven :class:`PromptClient` returning :class:`SignedExecutionResult`.

    Wraps :class:`~brompt.config.PolicyConfig` (per-tenant YAML/JSON policy)
    into the engine-level ``ComplianceConfig`` and returns proof-carrying
    ``SignedExecutionResult`` objects from ``prompt()`` / ``replay()``.
    """

    def __init__(
        self,
        config: Optional[WidgetConfig] = None,
        policy: Optional[PolicyConfig] = None,
        enable_token_optimization: bool = True,
        enable_cache: bool = True,
        enable_auto_detect: bool = False,
        enable_streaming: bool = True,
        audit_log_path: Optional[str] = None,
        enable_pii_scan: bool = True,
    ):
        self.policy = policy
        compliance = policy.to_compliance_config() if policy is not None else None
        audit_secret = policy.get_signing_key() if policy is not None else None
        policy_override = policy.enable_pii_scan if policy is not None else None
        if policy_override is not None:
            enable_pii_scan = policy_override
        super().__init__(
            config=config,
            enable_token_optimization=enable_token_optimization,
            enable_cache=enable_cache,
            enable_auto_detect=enable_auto_detect,
            enable_streaming=enable_streaming,
            audit_log_path=audit_log_path,
            audit_secret_key=audit_secret,
            compliance=compliance,
            enable_pii_scan=enable_pii_scan,
        )

    @property
    def mode(self) -> str:
        """Effective compliance mode (``"standard"``/``"air_gapped"``/``"strict"``)."""
        return self._compliance.mode

    @property
    def budget(self) -> Optional[BudgetConfig]:
        """The active in-process budget ledger, if compliance is enabled."""
        return self._budget

    @property
    def audit(self) -> Optional[AuditLog]:
        """The bound audit log (alias of :attr:`audit_log`)."""
        return self._audit

    def _make_result(self, **kwargs) -> SignedExecutionResult:
        return SignedExecutionResult(**kwargs)

    def __repr__(self) -> str:
        tenant = self.policy.tenant_id if self.policy is not None else "default"
        return (
            f"CompliantPromptClient(tenant='{tenant}', mode='{self._compliance.mode}', "
            f"entries={len(self._audit.read_all()) if self._audit else 0})"
        )


# ---------------------------------------------------------------------------
# Backward-compatible alias
# ---------------------------------------------------------------------------
BromptWidget = PromptClient
