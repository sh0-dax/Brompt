"""Zero-Trust Security Engine for Prompt Injection Mitigation."""

import re
from typing import List


class SecurityEngine:
    BLOCKED_PATTERNS: List[str] = [
        r"ignore\s+previous\s+instructions",
        r"system\s+prompt\s+override",
        r"bypass\s+guardrails?",
        r"تجاهل\s+التعليمات",
        r"سجل\s+النظام",
    ]

    @classmethod
    def sanitize(cls, text: str) -> str:
        """Sanitizes incoming input and checks for adversarial prompt patterns.

        Raises:
            ValueError: If an untrusted or malicious input pattern is identified.
        """
        if not text or not text.strip():
            raise ValueError("Payload violation: Input text cannot be empty.")

        for pattern in cls.BLOCKED_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                raise ValueError(f"Security Violation: Untrusted adversarial pattern detected matching [{pattern}].")

        return text.strip()
