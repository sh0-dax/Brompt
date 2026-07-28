"""Security pipeline for prompt injection filtering and sanitization."""

import logging
import re
from typing import ClassVar

logger = logging.getLogger("brompt.security")


class SecurityViolationError(ValueError):
    """Custom exception raised when a security inspection fails."""


class SecurityEngine:
    INJECTION_PATTERNS: ClassVar[list[tuple[str, str]]] = [
        (r"\bignore\s+(all\s+)?previous\s+instructions\b", "Direct Injection: Instruction Override"),
        (r"\bsystem\s+prompt\s+override\b", "Direct Injection: System Override"),
        (r"\bbypass\s+guardrails?\b", "Guardrail Bypass Attempt"),
        (r"\breveal\s+(your\s+)?(system\s+)?prompt\b", "System Leakage Attempt"),
        (r"\breveal\s+internal\s+keys\b", "Credential Leakage Attempt"),
        (r"you\s+are\s+now\s+in\s+(developer|dan|god)\s+mode", "Jailbreak: Persona Switch"),
        (r"تجاهل\s+(جميع\s+)?التعليمات\s+السابقة", "Arabic: Instruction Override Attempt"),
        (r"أنت\s+(الآن\s+)?في\s+وضع\s+المطور", "Arabic: Developer Mode Bypass"),
    ]

    OUTPUT_LEAK_PATTERNS: ClassVar[list[tuple[str, str]]] = [
        (r"sk-ant-[A-Za-z0-9_-]{20,}", "Anthropic API key"),
        (r"sk-[A-Za-z0-9]{20,}", "Generic OpenAI-style API key"),
        (r"AKIA[0-9A-Z]{16}", "AWS access key ID"),
        (r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "Private key block"),
        (r"ghp_[A-Za-z0-9]{36}", "GitHub personal access token"),
    ]

    @classmethod
    def sanitize(cls, text: str, max_payload_size_kb: int = 64) -> str:
        """Sanitizes user input and enforces strict safety rules.

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

    @classmethod
    def sanitize_output(cls, text: str) -> str:
        """Redacts secret-like content from model output before it reaches the caller."""
        if not text:
            return text
        redacted = text
        for pattern, reason in cls.OUTPUT_LEAK_PATTERNS:
            if re.search(pattern, redacted):
                logger.warning("Output redaction: %s", reason)
                redacted = re.sub(pattern, "[REDACTED]", redacted)
        return redacted
