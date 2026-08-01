"""Core Runtime Execution Logic."""

import asyncio
import hashlib
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any

import yaml

from ..audit import AuditLog
from ..circuit_breaker import CircuitBreaker, CircuitBreakerOpenError
from ..classifier import InjectionClassificationError, InjectionClassifier, PendingReviewError, Tier
from ..memory import MemoryManager
from ..policy import PolicyEngine, PolicyViolationError
from ..providers_core import LLMProvider, ProviderError, build_provider_from_env
from ..ratelimit import RateLimiter, RateLimiterBackend, RateLimitExceededError
from ..schema import BromptConfig, ExecutionResult
from ..security import SecurityEngine, SecurityViolationError

logger = logging.getLogger("brompt.core.engine")

_UNSET = object()


class BromptEngine:
    """Core runtime engine enforcing deterministic execution and security guardrails."""

    def __init__(
        self,
        config_path: str = "agent.brompt.yaml",
        provider: LLMProvider | object | None = _UNSET,
        async_provider: LLMProvider | None = None,
        audit_log_path: str | None = None,
        audit_secret_key: str | None = None,
        audit_signing_key: str | None = None,
        rate_limiter: RateLimiterBackend | None = None,
        injection_classifier: InjectionClassifier | None = None,
        circuit_breaker: CircuitBreaker | None = None,
    ):
        manifest_file = Path(config_path)
        if not manifest_file.exists():
            raise FileNotFoundError(f"Manifest missing: {config_path}")

        with open(manifest_file, "r", encoding="utf-8") as f:
            raw_manifest = yaml.safe_load(f) or {}

        metadata = raw_manifest.get("metadata", {})
        sec_policy = raw_manifest.get("security_policy", {})
        mem_strategy = raw_manifest.get("memory_strategy", {})
        rate_policy = raw_manifest.get("rate_limit", {})

        self.config = BromptConfig(
            name=metadata.get("name", "DefaultAgent"),
            version=metadata.get("version", "0.1.0-alpha"),
            environment=metadata.get("environment", "production"),
            security_policy=sec_policy,
            memory_strategy=mem_strategy,
        )
        self.memory = MemoryManager(
            max_turns=self.config.memory_strategy.max_history_turns
        )
        self.rate_limiter: RateLimiterBackend = rate_limiter or RateLimiter(
            max_requests=rate_policy.get("max_requests", 30),
            window_seconds=rate_policy.get("window_seconds", 60.0),
        )
        if provider is _UNSET:
            self.provider: LLMProvider | None = build_provider_from_env()
        else:
            self.provider: LLMProvider | None = provider
        self.async_provider: LLMProvider | None = async_provider
        self.injection_classifier: InjectionClassifier | None = injection_classifier
        self.circuit_breaker: CircuitBreaker | None = circuit_breaker
        self.policy: PolicyEngine = PolicyEngine.from_manifest(raw_manifest)
        self.audit = AuditLog(
            audit_log_path or str(manifest_file.parent / f"{manifest_file.stem}.audit.log"),
            secret_key=audit_secret_key or os.getenv("BROMPT_AUDIT_SECRET"),
            signing_key=audit_signing_key or os.getenv("BROMPT_AUDIT_SIGNING_KEY"),
        )
        self.state_id = f"state_{uuid.uuid4().hex[:8]}"
        self._last_latency_ms = 0.0
        self._last_tokens_used = 0
        self._last_prompt_tokens = 0
        self._last_completion_tokens = 0

    # -- shared pipeline steps -------------------------------------------------

    def _pre_process(
        self, user_query: str, context: dict[str, Any] | None, caller_id: str
    ) -> tuple[str, dict[str, Any]]:
        """Policy check → rate limit → sanitize → tiered classifier → state."""
        self.policy.check(caller_id)

        self.rate_limiter.check(caller_id)

        max_kb = self.config.security_policy.max_payload_size_kb
        clean_query = SecurityEngine.sanitize(user_query, max_payload_size_kb=max_kb)

        if self.injection_classifier is not None:
            try:
                result = self.injection_classifier.classify_tiered(clean_query)
            except InjectionClassificationError as exc:
                logger.warning("Injection classifier unavailable, failing open: %s", exc)
                result = None
            if result is not None:
                if result.tier == Tier.BLOCK:
                    raise SecurityViolationError(
                        f"Security Violation: [Semantic Injection: {result.reasoning}]"
                    )
                if result.tier == Tier.HOLD:
                    raise PendingReviewError(
                        f"Pending Review: [confidence={result.confidence:.2f}, "
                        f"reasoning={result.reasoning}]"
                    )

        if context:
            for k, v in context.items():
                self.memory.update_state(k, v)

        self.memory.add_turn("user", clean_query)

        output_payload: dict[str, Any] = {
            "processed_input": clean_query,
            "engine_status": "ACTIVE",
            "virtual_state": self.memory.get_state(),
            "environment": self.config.environment,
            "llm_response": None,
            "provider_used": False,
        }
        return clean_query, output_payload

    def _handle_rejection(self, err: Exception) -> ExecutionResult:
        """Maps a pipeline exception to an ExecutionResult and audits it."""
        is_policy = isinstance(err, PolicyViolationError)
        is_pending = isinstance(err, PendingReviewError)
        if isinstance(err, RateLimitExceededError):
            event, msg = "rate_limited", str(err)
        elif is_policy:
            event, msg = "policy_denied", str(err)
        elif isinstance(err, SecurityViolationError):
            event, msg = "security_violation", str(err)
        elif is_pending:
            event, msg = "pending_review", str(err)
        elif isinstance(err, CircuitBreakerOpenError):
            event, msg = "circuit_open", str(err)
        elif isinstance(err, ValueError):
            event, msg = "value_error", str(err)
        else:
            logger.error("Unexpected engine error: %s", err, exc_info=err)
            event, msg = "internal_error", f"Internal engine error: {type(err).__name__}"
        if event in ("rate_limited", "security_violation", "policy_denied"):
            logger.warning("%s blocked execution: %s", event, err)
        audit_record = self.audit.record(event, self.state_id, is_pending,
                                         str(err), latency_ms=0.0, tokens_used=0)
        return ExecutionResult(state_id=self.state_id, is_secure=is_pending,
                               data={}, error_message=msg,
                               receipt_hash=audit_record.get("entry_hash"),
                               audit_hash=audit_record.get("entry_hash"),
                               audit_chain_id=audit_record.get("prev_hash"),
                               tamper_check=self.audit.verify())

    # -- synchronous path -------------------------------------------------------

    def execute(
        self,
        user_query: str,
        context: dict[str, Any] | None = None,
        caller_id: str = "default",
        system_prompt: str | None = None,
        override_messages: list[dict[str, str]] | None = None,
    ) -> ExecutionResult:
        """Executes query payload through security filters, rate limiting,
        bounded memory, and (if configured) the upstream LLM provider.

        Parameters
        ----------
        override_messages :
            If set, these messages are sent to the provider INSTEAD of
            ``self.memory.get_history()``.  The original ``user_query``
            is still sanitised, memory-tracked, and stored in chat history
            so the UI always shows what the user actually typed.
        """
        try:
            _, output_payload = self._pre_process(user_query, context, caller_id)
        except Exception as err:
            return self._handle_rejection(err)

        reply = None
        self._last_prompt_tokens = 0
        self._last_completion_tokens = 0
        if self.provider is not None:
            try:
                messages_to_send = (
                    override_messages
                    if override_messages is not None
                    else self.memory.get_history()
                )
                self._last_prompt_tokens = sum(
                    len(m.get("content", "")) // 4 for m in messages_to_send
                ) if messages_to_send else 0
                t0 = time.time()
                if self.circuit_breaker is not None:
                    reply = self.circuit_breaker.call_sync(
                        self.provider.generate,
                        args=(messages_to_send,),
                        kwargs={"system": system_prompt},
                    )
                else:
                    reply = self.provider.generate(messages_to_send, system=system_prompt)
                self._last_latency_ms = (time.time() - t0) * 1000
                reply, redactions = SecurityEngine.redact_with_metadata(reply)
                if redactions:
                    self.audit.record(
                        "output_redacted", self.state_id, True,
                        detail=", ".join(redactions),
                        latency_ms=self._last_latency_ms, tokens_used=self._last_tokens_used,
                    )
                self.memory.add_turn("assistant", reply)
                output_payload["llm_response"] = reply
                output_payload["provider_used"] = True
            except (ProviderError, CircuitBreakerOpenError) as err:
                logger.error("Provider call failed: %s", err)
                ar = self.audit.record("provider_error", self.state_id, False, str(err),
                                       latency_ms=self._last_latency_ms, tokens_used=self._last_tokens_used)
                return ExecutionResult(
                    state_id=self.state_id,
                    is_secure=False,
                    data=output_payload,
                    error_message=f"Provider error: {err}",
                    receipt_hash=ar.get("entry_hash"),
                    audit_hash=ar.get("entry_hash"),
                    audit_chain_id=ar.get("prev_hash"),
                    tamper_check=self.audit.verify(),
                )

        self._last_completion_tokens = len(reply) // 4 if reply else 0
        self._last_tokens_used = self._last_prompt_tokens + self._last_completion_tokens
        messages_sent = override_messages if override_messages is not None else self.memory.get_history()
        ar = self.audit.record("execute", self.state_id, True,
                               latency_ms=self._last_latency_ms, tokens_used=self._last_tokens_used,
                               messages=messages_sent)
        return ExecutionResult(state_id=self.state_id, is_secure=True, data=output_payload,
                               receipt_hash=ar.get("entry_hash"),
                               audit_hash=ar.get("entry_hash"),
                               audit_chain_id=ar.get("prev_hash"),
                               tamper_check=self.audit.verify())


    # -- asynchronous path --------------------------------------------------

    async def execute_async(
        self,
        user_query: str,
        context: dict[str, Any] | None = None,
        caller_id: str = "default",
        system_prompt: str | None = None,
        override_messages: list[dict[str, str]] | None = None,
    ) -> ExecutionResult:
        try:
            _, output_payload = self._pre_process(user_query, context, caller_id)
        except Exception as err:
            return self._handle_rejection(err)

        history = override_messages if override_messages is not None else self.memory.get_history()
        reply = None
        self._last_prompt_tokens = sum(
            len(m.get("content", "")) // 4 for m in (history or [])
        )
        self._last_completion_tokens = 0
        try:
            t0 = time.time()
            if self.async_provider is not None:
                coro = self.async_provider.agenerate(history, system=system_prompt)
                if self.circuit_breaker is not None:
                    reply = await self.circuit_breaker.call(coro)
                else:
                    reply = await coro
            elif self.provider is not None:
                if self.circuit_breaker is not None:
                    reply = self.circuit_breaker.call_sync(
                        self.provider.generate,
                        args=(history,),
                        kwargs={"system": system_prompt},
                    )
                else:
                    reply = await asyncio.to_thread(self.provider.generate, history, system_prompt)
            self._last_latency_ms = (time.time() - t0) * 1000 if reply else 0.0
        except (ProviderError, CircuitBreakerOpenError) as err:
            logger.error("Provider call failed: %s", err)
            ar = self.audit.record("provider_error", self.state_id, False, str(err),
                                   latency_ms=self._last_latency_ms, tokens_used=self._last_tokens_used)
            return ExecutionResult(
                state_id=self.state_id,
                is_secure=False,
                data=output_payload,
                error_message=f"Provider error: {err}",
                receipt_hash=ar.get("entry_hash"),
                audit_hash=ar.get("entry_hash"),
                audit_chain_id=ar.get("prev_hash"),
                tamper_check=self.audit.verify(),
            )

        if reply is not None:
            reply, redactions = SecurityEngine.redact_with_metadata(reply)
            if redactions:
                self.audit.record(
                    "output_redacted", self.state_id, True,
                    detail=", ".join(redactions),
                    latency_ms=self._last_latency_ms, tokens_used=self._last_tokens_used,
                )
            self.memory.add_turn("assistant", reply)
            output_payload["llm_response"] = reply
            output_payload["provider_used"] = True

        self._last_completion_tokens = len(reply) // 4 if reply else 0
        self._last_tokens_used = self._last_prompt_tokens + self._last_completion_tokens
        ar = self.audit.record("execute", self.state_id, True,
                               latency_ms=self._last_latency_ms, tokens_used=self._last_tokens_used,
                               messages=history)
        return ExecutionResult(state_id=self.state_id, is_secure=True, data=output_payload,
                               receipt_hash=ar.get("entry_hash"),
                               audit_hash=ar.get("entry_hash"),
                               audit_chain_id=ar.get("prev_hash"),
                               tamper_check=self.audit.verify())

    # -- replay ----------------------------------------------------------------

    def replay(self, entry_hash: str, provider=None, system: str | None = None) -> dict:
        """Re-run a previous audit entry on a (possibly different) provider.

        Parameters
        ----------
        entry_hash :
            The ``entry_hash`` of the audit entry to replay.
        provider :
            Provider to use for the re-run. Falls back to ``self.provider``.
        system :
            Optional system prompt forwarded to the provider.

        Returns
        -------
        A dict with keys ``original`` and ``replayed``.
        """
        result = self.audit.replay(entry_hash, provider or self.provider, system=system)
        if "error" in result:
            return result
        replayed = result["replayed"]
        text = getattr(replayed, "text", "")
        self.audit.record(
            "replay_executed", self.state_id, True,
            detail=f"original_hash={entry_hash} "
                   f"replayed_hash={hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]}",
            latency_ms=getattr(replayed, "latency_ms", None),
            tokens_used=getattr(replayed, "tokens_used", 0),
            messages=result["original"].get("messages"),
        )
        return result
