"""Core Runtime Execution Logic."""

import asyncio
import logging
import uuid
from pathlib import Path
from typing import Any

import yaml

from .audit import AuditLog
from .classifier import InjectionClassificationError, InjectionClassifier
from .memory import MemoryManager
from .providers import LLMProvider, ProviderError, build_provider_from_env
from .ratelimit import RateLimiter, RateLimiterBackend, RateLimitExceededError
from .schema import BromptConfig, ExecutionResult
from .security import SecurityEngine, SecurityViolationError

logger = logging.getLogger("brompt.core")


class BromptEngine:
    """Core runtime engine enforcing deterministic execution and security guardrails."""

    def __init__(
        self,
        config_path: str = "agent.brompt.yaml",
        provider: LLMProvider | None = None,
        async_provider: LLMProvider | None = None,
        audit_log_path: str | None = None,
        rate_limiter: RateLimiterBackend | None = None,
        injection_classifier: InjectionClassifier | None = None,
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
        # Explicit rate_limiter (e.g. RedisRateLimiter for multi-instance
        # deployments) takes precedence; otherwise fall back to the
        # in-process, single-instance limiter built from the manifest.
        self.rate_limiter: RateLimiterBackend = rate_limiter or RateLimiter(
            max_requests=rate_policy.get("max_requests", 30),
            window_seconds=rate_policy.get("window_seconds", 60.0),
        )
        # Explicit provider > env-configured provider > None (dry-run mode).
        self.provider: LLMProvider | None = provider if provider is not None else build_provider_from_env()
        # Separate slot for an async-capable provider (execute_async).
        self.async_provider: LLMProvider | None = async_provider
        # Optional semantic second pass beyond the regex blocklist. Off by
        # default (extra latency/cost per request) -- pass e.g.
        # LLMInjectionClassifier(some_provider) to enable it.
        self.injection_classifier: InjectionClassifier | None = injection_classifier
        self.audit = AuditLog(
            audit_log_path or str(manifest_file.parent / f"{manifest_file.stem}.audit.log")
        )
        self.state_id = f"state_{uuid.uuid4().hex[:8]}"

    # -- shared pipeline steps -------------------------------------------------

    def _pre_process(
        self, user_query: str, context: dict[str, Any] | None, caller_id: str
    ) -> tuple[str, dict[str, Any]]:
        """Rate limit, sanitize, classify, update state, and record the user turn."""
        self.rate_limiter.check(caller_id)

        max_kb = self.config.security_policy.max_payload_size_kb
        clean_query = SecurityEngine.sanitize(user_query, max_payload_size_kb=max_kb)

        # Second, semantic pass: catches paraphrased/obfuscated attempts the
        # regex blocklist misses. Fails *open* on classifier errors -- the
        # regex layer still applies either way.
        if self.injection_classifier is not None:
            try:
                blocked = self.injection_classifier.is_blocked(clean_query)
            except InjectionClassificationError as exc:
                logger.warning("Injection classifier unavailable, failing open: %s", exc)
                blocked = None
            if blocked is not None:
                raise SecurityViolationError(
                    f"Security Violation: [Semantic Injection: {blocked.reasoning}]"
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
        if isinstance(err, RateLimitExceededError):
            event, msg = "rate_limited", str(err)
        elif isinstance(err, SecurityViolationError):
            event, msg = "security_violation", str(err)
        elif isinstance(err, ValueError):
            event, msg = "value_error", str(err)
        else:
            logger.error("Unexpected engine error: %s", err, exc_info=err)
            event, msg = "internal_error", f"Internal engine error: {type(err).__name__}"
        if event in ("rate_limited", "security_violation"):
            logger.warning("%s blocked execution: %s", event, err)
        self.audit.record(event, self.state_id, False, str(err))
        return ExecutionResult(state_id=self.state_id, is_secure=False, data={}, error_message=msg)

    # -- synchronous path -------------------------------------------------------

    def execute(
        self,
        user_query: str,
        context: dict[str, Any] | None = None,
        caller_id: str = "default",
        system_prompt: str | None = None,
    ) -> ExecutionResult:
        """Executes query payload through security filters, rate limiting,
        bounded memory, and (if configured) the upstream LLM provider."""
        try:
            _, output_payload = self._pre_process(user_query, context, caller_id)
        except Exception as err:
            return self._handle_rejection(err)

        if self.provider is not None:
            try:
                reply = self.provider.generate(self.memory.get_history(), system=system_prompt)
                reply = SecurityEngine.sanitize_output(reply)
                self.memory.add_turn("assistant", reply)
                output_payload["llm_response"] = reply
                output_payload["provider_used"] = True
            except ProviderError as err:
                logger.error("Provider call failed: %s", err)
                self.audit.record("provider_error", self.state_id, False, str(err))
                return ExecutionResult(
                    state_id=self.state_id,
                    is_secure=False,
                    data=output_payload,
                    error_message=f"Provider error: {err}",
                )

        self.audit.record("execute", self.state_id, True)
        return ExecutionResult(state_id=self.state_id, is_secure=True, data=output_payload)

    # -- asynchronous path --------------------------------------------------

    async def execute_async(
        self,
        user_query: str,
        context: dict[str, Any] | None = None,
        caller_id: str = "default",
        system_prompt: str | None = None,
    ) -> ExecutionResult:
        try:
            _, output_payload = self._pre_process(user_query, context, caller_id)
        except Exception as err:
            return self._handle_rejection(err)

        history = self.memory.get_history()
        try:
            if self.async_provider is not None:
                reply = await self.async_provider.agenerate(history, system=system_prompt)
            elif self.provider is not None:
                reply = await asyncio.to_thread(self.provider.generate, history, system_prompt)
            else:
                reply = None
        except ProviderError as err:
            logger.error("Provider call failed: %s", err)
            self.audit.record("provider_error", self.state_id, False, str(err))
            return ExecutionResult(
                state_id=self.state_id,
                is_secure=False,
                data=output_payload,
                error_message=f"Provider error: {err}",
            )

        if reply is not None:
            reply = SecurityEngine.sanitize_output(reply)
            self.memory.add_turn("assistant", reply)
            output_payload["llm_response"] = reply
            output_payload["provider_used"] = True

        self.audit.record("execute", self.state_id, True)
        return ExecutionResult(state_id=self.state_id, is_secure=True, data=output_payload)
