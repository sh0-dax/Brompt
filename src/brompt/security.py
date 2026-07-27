"""Security pipeline for prompt injection filtering and sanitization."""

import re
from typing import List


class SecurityEngine:
    BLOCKED_PATTERNS: List[str] = [
        r"ignore\s+previous\s+instructions",
        r"system\s+prompt\s+override",
        r"bypass\s+guardrails?",
        r"reveal\s+internal\s+keys",
    ]

    @classmethod
    def sanitize(cls, text: str) -> str:
        """Sanitizes query payloads and prevents execution attacks.

        Raises:
            ValueError: If an untrusted pattern matches input string.
        """
        if not text or not text.strip():
            raise ValueError("Invalid Input: Payload cannot be empty.")

        for pattern in cls.BLOCKED_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                raise ValueError(
                    f"\U0001f6e1 Security Violation: Blocked malicious pattern [{pattern}]."
                )
        return text.strip()
