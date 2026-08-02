"""Security pipeline for prompt injection filtering and sanitization.

Two-layer defence:
1. Fast regex-based pattern matching (always on).
2. Optional LLM-based semantic classification (opt-in) via
   ``LLMInjectionClassifier`` — detects paraphrases, translations,
   and novel injection patterns that regexes miss.
"""

import base64
import logging
import re
import unicodedata
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from .classifier import LLMInjectionClassifier

logger = logging.getLogger("brompt.security")


class SecurityViolationError(ValueError):
    """Custom exception raised when a security inspection fails."""


_ZERO_WIDTH_CHARS = str.maketrans({c: None for c in "\u200b\u200c\u200d\u2060\ufeff\u00ad\u034f\u061c\u115f\u1160\u17b4\u17b5\u180e\u2028\u2029\u2061\u2062\u2063\u2064\u2066\u2067\u2068\u2069"})  # noqa: E501


class SecurityEngine:
    """Security pipeline — regex fast-path with optional LLM deep scan.

    Usage with classifier::

        from .classifier import LLMInjectionClassifier

        engine = SecurityEngine()
        engine.set_classifier(LLMInjectionClassifier(provider))
        sanitized = engine.sanitize(user_input)
    """

    INJECTION_PATTERNS: ClassVar[list[tuple[str, str]]] = [
        (r"\bignore\s+(all\s+)?previous\s+instructions\b", "Direct Injection: Instruction Override"),
        (r"\bsystem\s+prompt\s+override\b", "Direct Injection: System Override"),
        (r"\bbypass\s+guardrails?\b", "Guardrail Bypass Attempt"),
        (r"\breveal\s+(your\s+)?(system\s+)?prompt\b", "System Leakage Attempt"),
        (r"\breveal\s+internal\s+keys\b", "Credential Leakage Attempt"),
        (r"you\s+are\s+now\s+in\s+(developer|dan|god)\s+mode", "Jailbreak: Persona Switch"),
        (r"\bdisregard\s+(all\s+|any\s+)?(prior|previous)\s+(instructions|directives|guidelines)\b", "Direct Injection: Instruction Override (variant)"),  # noqa: E501
        (r"\boverride\s+(your\s+)?((core|safety|security|ethical)\s+){1,3}(protocols?|guidelines?|instructions)\b", "Direct Injection: Safety Override"),  # noqa: E501
        (r"\boutput\s+(your\s+)?(system\s+)?(prompt|instructions)\s+(verbatim|text|as.is|exactly)\b", "System Leakage Attempt (variant)"),  # noqa: E501
        (r"\byou\s+(are|will)\s+(now\s+)?(act\s+as|simulate|pretend\s+to\s+be)\b", "Jailbreak: Role-Play Bypass"),
        (r"\bact\s+as\s+(an?\s+)?(dan)\b", "Jailbreak: DAN Roleplay"),
        (r"\bremove\s+(all\s+)?(restrictions?|limitations?|filtering|content.policy)\b", "Jailbreak: Restriction Removal"),  # noqa: E501
        (r"تجاهل\s+(جميع\s+)?التعليمات\s+السابقة", "Arabic: Instruction Override Attempt"),
        (r"أنت\s+(الآن\s+)?في\s+وضع\s+المطور", "Arabic: Developer Mode Bypass"),
        (r"ignora\s+(tutte\s+)?le\s+istruzioni\s+precedenti", "Italian: Instruction Override Attempt"),
        # NOTE: previously `r"ignore\s+(alle\s+)?(bisherigen\s+)?anweisungen"` — that matched
        # the *English* word "ignore" glued to German words, so it silently passed real German
        # phrasing ("Ignoriere alle bisherigen Anweisungen"). Fixed to match the actual German verb.
        (r"ignorier(e|en|t)?\s+(alle\s+)?(bisherigen\s+)?anweisungen", "German: Instruction Override Attempt"),
    ]

    OUTPUT_LEAK_PATTERNS: ClassVar[list[tuple[str, str]]] = [
        (r"sk-ant-[A-Za-z0-9_-]{20,}", "Anthropic API key"),
        (r"sk-[A-Za-z0-9]{20,}", "Generic OpenAI-style API key"),
        (r"AKIA[0-9A-Z]{16}", "AWS access key ID"),
        (r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "Private key block"),
        (r"ghp_[A-Za-z0-9]{36}", "GitHub personal access token"),
        (r"gho_[A-Za-z0-9]{36}", "GitHub OAuth access token"),
        (r"xox[baprs]-[0-9A-Za-z-]{10,}", "Slack token"),
    ]

    @classmethod
    def _canonicalize(cls, text: str) -> str:
        """Normalize text: NFKC Unicode normalization + strip zero-width chars."""
        text = unicodedata.normalize("NFKC", text)
        text = text.translate(_ZERO_WIDTH_CHARS)
        return text

    @classmethod
    def _detect_base64(cls, text: str) -> bool:
        """Heuristic detection of base64-encoded payloads."""
        cleaned = text.strip()
        if len(cleaned) < 40:
            return False
        base64_chars = 0
        has_upper = has_lower = has_digit = has_symbol = False
        for c in cleaned:
            if c.isalnum() or c in "+/=":
                base64_chars += 1
            if c.isupper():
                has_upper = True
            if c.islower():
                has_lower = True
            if c.isdigit():
                has_digit = True
            if c in "+/=":
                has_symbol = True
        char_class_count = sum([has_upper, has_lower, has_digit, has_symbol])
        if char_class_count < 2:
            return False
        ratio = base64_chars / len(cleaned)
        if ratio < 0.85:
            return False
        padding_ratio = cleaned.count("=") / len(cleaned)
        if padding_ratio > 0.02:
            return True
        try:
            decoded = base64.b64decode(cleaned, validate=True)
            return 32 <= len(decoded) <= 4096
        except Exception:
            return False

    @classmethod
    def _normalize_for_regex(cls, text: str) -> str:
        """Normalize text to catch obfuscated injections before regex matching."""
        # Replace common leetspeak substitutions
        subs = {
            "0": "o", "1": "i", "3": "e", "4": "a", "5": "s",
            "7": "t", "@": "a", "$": "s", "!": "i",
        }
        for old, new in subs.items():
            text = text.replace(old, new)
        return text

    _classifier: "LLMInjectionClassifier | None" = None

    @classmethod
    def set_classifier(cls, classifier: "LLMInjectionClassifier | None") -> None:
        """Opt-in to LLM-based semantic injection detection.

        When set, each call to ``sanitize()`` falls through to the
        classifier *after* passing the regex fast-path.  The classifier
        costs one extra LLM call per request.
        """
        cls._classifier = classifier

    @classmethod
    def sanitize(cls, text: str, max_payload_size_kb: int = 64) -> str:
        """Sanitizes user input and enforces strict safety rules.

        Applies Unicode canonicalization, zero-width char stripping,
        leetspeak normalization, base64 detection, and regex pattern matching.
        If an ``LLMInjectionClassifier`` is registered, passes the text
        through semantic classification as a second line of defence.

        Raises:
            SecurityViolationError: If input matches a blocked pattern.
            ValueError: If input is empty or exceeds size limit.
        """
        clean, _metadata = cls.sanitize_with_metadata(text, max_payload_size_kb)
        return clean

    @classmethod
    def sanitize_with_metadata(cls, text: str, max_payload_size_kb: int = 64) -> tuple[str, list[str]]:
        """Like :meth:`sanitize` but returns ``(clean_text, metadata)``.

        *metadata* lists the non-blocking normalizations that were applied
        (``canonicalized``, ``zero_width_stripped``, ``leetspeak_normalized``)
        so callers can record forensic detail in the audit log.  Blocking
        violations still raise :class:`SecurityViolationError` (the reason is
        embedded in the message).
        """
        if not text or not text.strip():
            raise ValueError("Invalid Input: Payload cannot be empty.")

        payload_bytes = len(text.encode("utf-8"))
        max_bytes = max_payload_size_kb * 1024
        if payload_bytes > max_bytes:
            raise ValueError(
                f"Payload violation: Size {payload_bytes} bytes exceeds limit of {max_bytes} bytes."
            )

        metadata: list[str] = []
        normalized = cls._canonicalize(text)
        if normalized != text:
            metadata.append("canonicalized")
        if any(chr(c) in text for c in _ZERO_WIDTH_CHARS):
            metadata.append("zero_width_stripped")

        if cls._detect_base64(normalized):
            logger.warning("Security violation: Base64-encoded payload detected")
            raise SecurityViolationError("Security Violation: [Base64-encoded payload detected]")

        normalized_for_regex = cls._normalize_for_regex(normalized)
        if normalized_for_regex != normalized:
            metadata.append("leetspeak_normalized")

        for pattern, reason in cls.INJECTION_PATTERNS:
            if re.search(pattern, normalized_for_regex, re.IGNORECASE):
                logger.warning("Security violation: %s | pattern [%s]", reason, pattern)
                raise SecurityViolationError(
                    f"Security Violation: [{reason}]"
                )

        if cls._classifier is not None:
            result = cls._classifier.classify(text)
            if result.tier.name == "BLOCK":
                logger.warning("Security violation: LLM classifier blocked input (confidence=%.2f)", result.confidence)
                raise SecurityViolationError(
                    f"Security Violation: [LLM classifier — {result.reasoning}]"
                )

        return normalized.strip(), metadata

    @classmethod
    def sanitize_output(cls, text: str) -> str:
        """Redacts secret-like content from model output before it reaches the caller."""
        redacted, _redactions = cls.redact_with_metadata(text)
        return redacted

    @classmethod
    def redact_with_metadata(cls, text: str) -> tuple[str, list[str]]:
        """Like :meth:`sanitize_output` but returns ``(redacted, redactions)``.

        *redactions* lists the type of each secret-like pattern that was
        replaced (e.g. ``"Anthropic API key"``), so callers can record
        exactly what was hidden in the audit log.
        """
        if not text:
            return text, []
        redacted = text
        redactions: list[str] = []
        for pattern, reason in cls.OUTPUT_LEAK_PATTERNS:
            if re.search(pattern, redacted):
                redactions.append(reason)
                redacted = re.sub(pattern, "[REDACTED]", redacted)
        if redactions:
            logger.warning("Output redaction: %s", ", ".join(redactions))
        return redacted, redactions
