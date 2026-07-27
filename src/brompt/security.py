"""Security pipeline for prompt injection filtering and sanitization."""

import re
import logging
from typing import List, Tuple

logger = logging.getLogger("brompt.security")


class SecurityViolationError(ValueError):
    """Custom exception raised when a security inspection fails."""
    pass


class SecurityEngine:
    INJECTION_PATTERNS: List[Tuple[str, str]] = [
        # Direct Injection
        (r"\bignore\s+(all\s+)?previous\s+instructions\b", "Direct Injection: Instruction Override"),
        (r"\bsystem\s+prompt\s+override\b", "Direct Injection: System Override"),
        (r"\bbypass\s+guardrails?\b", "Guardrail Bypass Attempt"),
        (r"\breveal\s+(your\s+)?(system\s+)?prompt\b", "System Leakage Attempt"),
        (r"\breveal\s+internal\s+keys\b", "Credential Leakage Attempt"),
        # Jailbreak
        (r"you\s+are\s+now\s+in\s+(developer|dan|god)\s+mode", "Jailbreak: Persona Switch"),
        # Arabic Attacks
        (r"تجاهل\s+(جميع\s+)?التعليمات\s+السابقة", "Hijri: Instruction Override Attempt"),
        (r"أنت\s+(الآن\s+)?في\s+وضع\s+المطور", "Hijri: Developer Mode Bypass"),
    ]

    @classmethod
    def sanitize(cls, text: str, max_payload_size_kb: int = 64) -> str:
        """Sanitizes user input and enforces strict safety rules.

        Args:
            text: Input text to validate.
            max_payload_size_kb: Maximum allowed payload size in kilobytes.

        Raises:
            SecurityViolationError: If input matches a blocked pattern.
            ValueError: If input is empty or exceeds size limit.
        """
        if not text or not text.strip():
            raise ValueError("Invalid Input: Payload cannot be empty.")

        payload_bytes = len(text.encode("utf-8"))
        max_bytes = max_payload_size_kb * 1024
        if payload_bytes > max_bytes:
            raise ValueError(
                f"Payload violation: Size {payload_bytes} bytes exceeds limit of {max_bytes} bytes."
            )

        for pattern, reason in cls.INJECTION_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                logger.warning("Security violation: %s | pattern [%s]", reason, pattern)
                raise SecurityViolationError(
                    f"Security Violation: [{reason}]"
                )
        return text.strip()
