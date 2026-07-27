"""Core Runtime Execution Logic."""

import uuid
import logging
from pathlib import Path
from typing import Any, Dict, Optional
import yaml

from .schema import BromptConfig, ExecutionResult
from .security import SecurityEngine
from .memory import MemoryManager

logger = logging.getLogger("brompt.core")


class BromptEngine:
    """Core runtime engine enforcing deterministic execution and security guardrails."""

    def __init__(self, config_path: str = "agent.brompt.yaml"):
        manifest_file = Path(config_path)
        if not manifest_file.exists():
            raise FileNotFoundError(f"Manifest missing: {config_path}")

        with open(manifest_file, "r", encoding="utf-8") as f:
            raw_manifest = yaml.safe_load(f) or {}

        metadata = raw_manifest.get("metadata", {})
        sec_policy = raw_manifest.get("security_policy", {})
        mem_strategy = raw_manifest.get("memory_strategy", {})

        self.config = BromptConfig(
            name=metadata.get("name", "DefaultAgent"),
            version=metadata.get("version", "1.0.0"),
            environment=metadata.get("environment", "production"),
            security_policy=sec_policy,
            memory_strategy=mem_strategy,
        )
        self.memory = MemoryManager(
            max_turns=self.config.memory_strategy.max_history_turns
        )
        self.state_id = f"state_{uuid.uuid4().hex[:8]}"

    def execute(
        self, user_query: str, context: Optional[Dict[str, Any]] = None
    ) -> ExecutionResult:
        """Executes query payload through security filters and updates state."""
        try:
            # 1. Sanitize payload
            max_kb = self.config.security_policy.max_payload_size_kb
            clean_query = SecurityEngine.sanitize(user_query, max_payload_size_kb=max_kb)

            # 2. Update Virtual Memory
            if context:
                for k, v in context.items():
                    self.memory.update_state(k, v)

            # 3. Formulate Output State
            output_payload = {
                "processed_input": clean_query,
                "engine_status": "ACTIVE",
                "virtual_state": self.memory.get_state(),
                "environment": self.config.environment,
            }

            return ExecutionResult(
                state_id=self.state_id, is_secure=True, data=output_payload
            )
        except ValueError as err:
            return ExecutionResult(
                state_id=self.state_id,
                is_secure=False,
                data={},
                error_message=str(err),
            )
        except Exception as err:
            logger.error("Unexpected engine error: %s", err, exc_info=True)
            return ExecutionResult(
                state_id=self.state_id,
                is_secure=False,
                data={},
                error_message=f"Internal engine error: {type(err).__name__}",
            )
