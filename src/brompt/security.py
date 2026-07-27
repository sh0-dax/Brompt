"""Security pipeline for prompt injection filtering and sanitization."""

import re
import logging
from typing import List

logger = logging.getLogger("brompt.security")


class SecurityEngine:
    BLOCKED_PATTERNS: List[str] = [
        r"\bignore\s+previous\s+instructions\b",
        r"\bsystem\s+prompt\s+override\b",
        r"\bbypass\s+guardrails?\b",
        r"\breveal\s+internal\s+keys\b",
    ]

    @classmethod
    def sanitize(cls, text: str, max_payload_size_kb: int = 64) -> str:
        """Sanitizes query payloads and prevents execution attacks.

        Args:
            text: Input text to validate.
            max_payload_size_kb: Maximum allowed payload size in kilobytes.

        Raises:
            ValueError: If input is empty, exceeds size limit, or matches a blocked pattern.
        """
        if not text or not text.strip():
            raise ValueError("Invalid Input: Payload cannot be empty.")

        payload_bytes = len(text.encode("utf-8"))
        max_bytes = max_payload_size_kb * 1024
        if payload_bytes > max_bytes:
            raise ValueError(
                f"Payload violation: Size {payload_bytes} bytes exceeds limit of {max_bytes} bytes."
            )

        for pattern in cls.BLOCKED_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                logger.warning("Security violation detected: pattern [%s]", pattern)
                raise ValueError(
                    f"\U0001f6e1 Security Violation: Blocked malicious pattern [{pattern}]."
                )
        return text.strip()
