"""Prompt template optimizer — analyses failures and suggests improvements."""

import re
from collections import Counter
from typing import Optional

from .models import PromptOutcome, TemplateStats


class PromptOptimizer:
    """Analyses underperforming templates and generates actionable suggestions."""

    COMMON_ISSUES = {
        "vague_instructions": [
            r"try to", r"maybe", r"perhaps", r"if possible",
            r"حاول", r"يمكنك", r"ربما", r"إذا أمكن",
        ],
        "missing_examples": [
            r"example", r"few.shot", r"مثال",
        ],
        "overly_complex": [
            r"step \d+", r"first.*second.*third",
            r"خطوة \d+", r"أولاً.*ثانياً.*ثالثاً",
        ],
        "missing_constraints": [
            r"do not", r"avoid", r"refrain from",
            r"لا ت", r"تجنب", r"امتنع عن",
        ],
    }

    def __init__(self, min_samples: int = 10):
        self.min_samples = min_samples

    def analyze_template(
        self,
        template_id: str,
        template_text: str,
        stats: TemplateStats,
        failed_executions: Optional[list[dict]] = None,
    ) -> dict:
        """Analyse a single template and return improvement suggestions."""
        analysis = {
            "template_id": template_id,
            "current_success_rate": f"{stats.success_rate:.1f}%",
            "sample_size": stats.total_uses,
            "issues_found": [],
            "specific_suggestions": [],
        }

        if stats.total_uses < self.min_samples:
            analysis["issues_found"].append("Insufficient sample size for reliable analysis")
            return analysis

        text_issues = self._analyze_text(template_text)
        analysis["issues_found"].extend(text_issues)

        if failed_executions:
            pattern_issues = self._analyze_failures(failed_executions)
            analysis["issues_found"].extend(pattern_issues)

        analysis["specific_suggestions"] = self._generate_suggestions(analysis["issues_found"])
        return analysis

    def _analyze_text(self, text: str) -> list[str]:
        issues = []
        for name, patterns in self.COMMON_ISSUES.items():
            if name == "vague_instructions":
                count = sum(len(re.findall(p, text, re.IGNORECASE)) for p in patterns)
                if count > 2:
                    issues.append(f"Contains {count} vague instructions")
            elif name == "missing_examples":
                if not any(re.search(p, text, re.IGNORECASE) for p in patterns):
                    if len(text) > 200:
                        issues.append("Missing few-shot examples")
            elif name == "overly_complex":
                count = sum(len(re.findall(p, text, re.IGNORECASE)) for p in patterns)
                if count > 5:
                    issues.append(f"Overly complex ({count} steps/instructions)")
            elif name == "missing_constraints":
                if not any(re.search(p, text, re.IGNORECASE) for p in patterns):
                    if len(text) > 100:
                        issues.append("Missing negative constraints (do not, avoid...)")
        return issues

    def _analyze_failures(self, failures: list[dict]) -> list[str]:
        issues = []
        outcomes = Counter(f.get("outcome", "unknown") for f in failures)

        if outcomes.get("hallucination", 0) > len(failures) * 0.3:
            issues.append("Recurring pattern: hallucination")
        if outcomes.get("irrelevant", 0) > len(failures) * 0.3:
            issues.append("Recurring pattern: irrelevant outputs")
        if outcomes.get("refused", 0) > len(failures) * 0.2:
            issues.append("Recurring pattern: model refusal")

        return issues

    def _generate_suggestions(self, issues: list[str]) -> list[str]:
        suggestions = []
        for issue in issues:
            if "vague" in issue.lower():
                suggestions.append("Replace vague language with direct commands")
            if "example" in issue.lower():
                suggestions.append("Add 2-3 few-shot examples at the end of the prompt")
            if "complex" in issue.lower():
                suggestions.append("Decompose into smaller, focused sub-prompts")
            if "constraint" in issue.lower():
                suggestions.append("Add: 'Do not fabricate information' + quality guardrails")
            if "hallucination" in issue.lower():
                suggestions.append("Add: 'If unsure, say you lack sufficient information'")
            if "irrelevant" in issue.lower():
                suggestions.append("Add explicit relevance criteria to the instructions")
            if "refusal" in issue.lower():
                suggestions.append("Review prompt content — it may violate model safety policies")

        if not suggestions:
            suggestions.append("Try a full rewrite with a prompt engineering expert")
            suggestions.append("Test the same prompt across different models to isolate the issue")

        return suggestions
