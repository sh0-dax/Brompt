"""Main Engine Runtime Execution Logic."""

import uuid
from pathlib import Path
from typing import Any, Dict, Optional
import yaml

from .schema import BromptConfig, ExecutionResult
from .security import SecurityEngine


class BromptEngine:
    """Core runtime engine driving deterministic execution and guardrail security."""

    def __init__(self, config_path: str = "agent.brompt.yaml"):
        manifest_file = Path(config_path)
        if not manifest_file.exists():
            raise FileNotFoundError(f"Configuration file not found at: {config_path}")

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
        self.state_id = f"state_{uuid.uuid4().hex[:8]}"

    def execute(self, user_query: str, context: Optional[Dict[str, Any]] = None) -> ExecutionResult:
        """Executes a input query through the sanitization and state mapping pipeline."""
        try:
            clean_query = SecurityEngine.sanitize(user_query)

            payload = {
                "processed_input": clean_query,
                "engine_status": "ACTIVE",
                "virtual_state": "PAGED_OK",
                "environment": self.config.environment,
                "context": context or {},
            }

            return ExecutionResult(
                state_id=self.state_id,
                is_secure=True,
                data=payload,
            )
        except Exception as err:
            return ExecutionResult(
                state_id=self.state_id,
                is_secure=False,
                data={},
                error_message=str(err),
            )
